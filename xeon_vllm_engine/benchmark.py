from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
from tqdm import tqdm

from .config import BenchmarkConfig
from .workload import synthetic_prompt


@dataclass
class RequestResult:
    scenario: str
    request_id: int
    ok: bool
    latency_s: float
    prompt_tokens: int
    output_tokens: int
    error: str = ""


@dataclass
class ScenarioStats:
    scenario: str
    concurrency: int
    context_len: int
    total_requests: int
    success_rate: float
    mean_latency_s: float
    p50_latency_s: float
    p95_latency_s: float
    p99_latency_s: float
    throughput_req_per_s: float
    throughput_out_tok_per_s: float


class VllmBenchmarker:
    def __init__(self, cfg: BenchmarkConfig) -> None:
        self.cfg = cfg
        self.base_url = cfg.endpoint_base_url.rstrip("/")
        self.completions_url = f"{self.base_url}/completions"

    async def run_matrix(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(self.cfg.output_dir) / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        all_results: list[RequestResult] = []
        scenario_stats: list[ScenarioStats] = []

        scenarios = [(c, ctx) for c in self.cfg.concurrency_values for ctx in self.cfg.context_lengths]
        for concurrency, context_len in scenarios:
            scenario = f"c{concurrency}_ctx{context_len}"
            print(f"[bench] Running scenario={scenario}")
            results, elapsed = await self._run_scenario(concurrency, context_len, scenario)
            all_results.extend(results)
            scenario_stats.append(_compute_stats(scenario, concurrency, context_len, results, elapsed))

        self._write_outputs(out_dir, all_results, scenario_stats)
        return out_dir

    async def _run_scenario(
        self, concurrency: int, context_len: int, scenario: str
    ) -> tuple[list[RequestResult], float]:
        requests = self.cfg.requests_per_scenario
        sem = asyncio.Semaphore(concurrency)
        results: list[RequestResult] = []
        started = time.perf_counter()
        pbar = tqdm(total=requests, desc=scenario, leave=False)

        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            tasks = []
            for rid in range(requests):
                tasks.append(
                    asyncio.create_task(
                        self._bounded_request(client, sem, rid, scenario, context_len, pbar)
                    )
                )

            wave = max(1, self.cfg.stagger_wave_size)
            for i in range(0, len(tasks), wave):
                batch = tasks[i : i + wave]
                await asyncio.gather(*batch)
                if i + wave < len(tasks):
                    await asyncio.sleep(self.cfg.stagger_wave_delay_s)

            for task in tasks:
                results.append(task.result())

        pbar.close()
        elapsed = time.perf_counter() - started
        return results, elapsed

    async def _bounded_request(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        request_id: int,
        scenario: str,
        context_len: int,
        pbar,
    ) -> RequestResult:
        async with sem:
            payload = {
                "model": self.cfg.model,
                "prompt": synthetic_prompt(context_len),
                "max_tokens": self.cfg.max_tokens,
                "temperature": self.cfg.temperature,
            }
            start = time.perf_counter()
            try:
                response = await client.post(self.completions_url, json=payload)
                latency = time.perf_counter() - start
                response.raise_for_status()
                body = response.json()
                usage = body.get("usage", {})
                prompt_tokens = int(usage.get("prompt_tokens", context_len))
                completion_tokens = int(usage.get("completion_tokens", self.cfg.max_tokens))
                result = RequestResult(
                    scenario=scenario,
                    request_id=request_id,
                    ok=True,
                    latency_s=latency,
                    prompt_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                )
            except Exception as exc:
                result = RequestResult(
                    scenario=scenario,
                    request_id=request_id,
                    ok=False,
                    latency_s=time.perf_counter() - start,
                    prompt_tokens=context_len,
                    output_tokens=0,
                    error=str(exc),
                )
            pbar.update(1)
            return result

    def _write_outputs(
        self, out_dir: Path, all_results: list[RequestResult], scenario_stats: list[ScenarioStats]
    ) -> None:
        req_df = pd.DataFrame(asdict(r) for r in all_results)
        stat_df = pd.DataFrame(asdict(s) for s in scenario_stats)
        req_df.to_csv(out_dir / "requests.csv", index=False)
        stat_df.to_csv(out_dir / "scenario_stats.csv", index=False)

        summary = {
            "benchmark_config": asdict(self.cfg),
            "generated_at": datetime.now().isoformat(),
            "scenario_count": len(scenario_stats),
            "scenarios": [asdict(s) for s in scenario_stats],
        }
        with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)


def _compute_percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    rank = (pct / 100.0) * (len(values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[low]
    frac = rank - low
    return values[low] * (1.0 - frac) + values[high] * frac


def _compute_stats(
    scenario: str, concurrency: int, context_len: int, results: list[RequestResult], elapsed_s: float
) -> ScenarioStats:
    latencies = [r.latency_s for r in results if r.ok]
    ok_count = sum(1 for r in results if r.ok)
    total_out_tokens = sum(r.output_tokens for r in results if r.ok)
    mean_latency = statistics.fmean(latencies) if latencies else float("nan")

    return ScenarioStats(
        scenario=scenario,
        concurrency=concurrency,
        context_len=context_len,
        total_requests=len(results),
        success_rate=(ok_count / len(results)) if results else 0.0,
        mean_latency_s=mean_latency,
        p50_latency_s=_compute_percentile(latencies, 50),
        p95_latency_s=_compute_percentile(latencies, 95),
        p99_latency_s=_compute_percentile(latencies, 99),
        throughput_req_per_s=(ok_count / elapsed_s) if elapsed_s > 0 else 0.0,
        throughput_out_tok_per_s=(total_out_tokens / elapsed_s) if elapsed_s > 0 else 0.0,
    )

