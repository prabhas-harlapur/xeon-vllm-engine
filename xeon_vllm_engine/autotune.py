from __future__ import annotations

import asyncio
import json
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx

from .benchmark import ScenarioStats, VllmBenchmarker
from .config import BenchmarkConfig, EngineConfig
from .launcher import launch


@dataclass
class CandidateResult:
    candidate_id: int
    omp_threads: int
    instances_per_numa: int
    max_num_seqs: int
    stagger_start_seconds: float
    score: float
    throughput_req_per_s: float
    p95_latency_s: float
    success_rate: float
    detail_dir: str


class AutoTuner:
    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg

    def run(self) -> Path:
        out_root = Path(self.cfg.autotune.output_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
        out_root.mkdir(parents=True, exist_ok=True)

        results: list[CandidateResult] = []
        for idx, candidate in enumerate(self._candidates(), start=1):
            print(f"[autotune] candidate={idx} {candidate}")
            result = self._evaluate_candidate(idx, candidate, out_root)
            results.append(result)

        results_sorted = sorted(results, key=lambda x: x.score, reverse=True)
        best = results_sorted[0]
        report = {
            "generated_at": datetime.now().isoformat(),
            "best": asdict(best),
            "all_candidates": [asdict(r) for r in results_sorted],
        }
        with (out_root / "autotune_summary.json").open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[autotune] best candidate: {best}")
        return out_root

    def _candidates(self) -> Iterable[dict]:
        a = self.cfg.autotune
        for omp in a.candidate_omp_threads:
            for inst in a.candidate_instances_per_numa:
                for seqs in a.candidate_max_num_seqs:
                    for stagger in a.candidate_stagger_start_seconds:
                        yield {
                            "omp_threads": omp,
                            "instances_per_numa": inst,
                            "max_num_seqs": seqs,
                            "stagger_start_seconds": stagger,
                        }

    def _evaluate_candidate(self, candidate_id: int, candidate: dict, out_root: Path) -> CandidateResult:
        local_cfg = deepcopy(self.cfg)
        local_cfg.xeon_tuning.omp_num_threads = candidate["omp_threads"]
        local_cfg.xeon_tuning.instances_per_numa = candidate["instances_per_numa"]
        local_cfg.xeon_tuning.stagger_start_seconds = candidate["stagger_start_seconds"]
        local_cfg.model.max_num_seqs = candidate["max_num_seqs"]

        bench_cfg = BenchmarkConfig(
            endpoint_base_url=self.cfg.benchmark.endpoint_base_url,
            model=self.cfg.benchmark.model,
            timeout_s=self.cfg.benchmark.timeout_s,
            concurrency_values=self.cfg.autotune.benchmark_concurrency_values,
            context_lengths=self.cfg.autotune.benchmark_context_lengths,
            max_tokens=self.cfg.benchmark.max_tokens,
            temperature=self.cfg.benchmark.temperature,
            requests_per_scenario=self.cfg.autotune.benchmark_requests_per_scenario,
            stagger_wave_size=self.cfg.benchmark.stagger_wave_size,
            stagger_wave_delay_s=self.cfg.benchmark.stagger_wave_delay_s,
            output_dir=str(out_root / f"candidate_{candidate_id}"),
        )

        procs = launch(local_cfg)
        detail_dir: Path | None = None
        try:
            self._wait_until_healthy(local_cfg)
            time.sleep(max(0.0, self.cfg.autotune.warmup_seconds))
            bench = VllmBenchmarker(bench_cfg)
            detail_dir = asyncio.run(bench.run_matrix())
        finally:
            for p in procs:
                if p.poll() is None:
                    p.terminate()
            for p in procs:
                try:
                    p.wait(timeout=20)
                except Exception:
                    p.kill()

        if detail_dir is None:
            raise RuntimeError("Benchmark directory was not generated for candidate.")

        stats = self._load_stats(detail_dir / "scenario_stats.csv")
        throughput = sum(s.throughput_req_per_s for s in stats) / max(1, len(stats))
        p95 = sum(s.p95_latency_s for s in stats) / max(1, len(stats))
        success = sum(s.success_rate for s in stats) / max(1, len(stats))
        score = throughput * success / max(0.001, p95)
        return CandidateResult(
            candidate_id=candidate_id,
            omp_threads=candidate["omp_threads"],
            instances_per_numa=candidate["instances_per_numa"],
            max_num_seqs=candidate["max_num_seqs"],
            stagger_start_seconds=candidate["stagger_start_seconds"],
            score=score,
            throughput_req_per_s=throughput,
            p95_latency_s=p95,
            success_rate=success,
            detail_dir=str(detail_dir),
        )

    def _wait_until_healthy(self, cfg: EngineConfig) -> None:
        a = cfg.autotune
        deadline = time.time() + a.healthcheck_timeout_s
        base = cfg.benchmark.endpoint_base_url
        if base.endswith("/v1"):
            base = base[:-3]
        health_url = f"{base.rstrip('/')}/health"
        while time.time() < deadline:
            try:
                resp = httpx.get(health_url, timeout=3.0)
                if resp.status_code < 500:
                    return
            except Exception:
                pass
            time.sleep(2)
        raise TimeoutError(f"Timed out waiting for health endpoint: {health_url}")

    def _load_stats(self, csv_path: Path) -> list[ScenarioStats]:
        import csv

        stats: list[ScenarioStats] = []
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats.append(
                    ScenarioStats(
                        scenario=row["scenario"],
                        concurrency=int(row["concurrency"]),
                        context_len=int(row["context_len"]),
                        total_requests=int(row["total_requests"]),
                        success_rate=float(row["success_rate"]),
                        mean_latency_s=float(row["mean_latency_s"]),
                        p50_latency_s=float(row["p50_latency_s"]),
                        p95_latency_s=float(row["p95_latency_s"]),
                        p95_ttft_s=float(row["p95_ttft_s"]),
                        p95_tpot_s=float(row["p95_tpot_s"]),
                        throughput_req_per_s=float(row["throughput_req_per_s"]),
                        throughput_out_tok_per_s=float(row["throughput_out_tok_per_s"]),
                    )
                )
        return stats
