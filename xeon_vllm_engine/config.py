from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    model: str
    host: str = "0.0.0.0"
    port: int = 8000
    device: str = "cpu"
    max_model_len: int = 8192
    dtype: str = "bfloat16"
    max_num_seqs: int = 256
    gpu_memory_utilization: float = 0.9
    extra_args: list[str] = field(default_factory=list)


@dataclass
class XeonTuningConfig:
    omp_num_threads: int | None = None
    kmp_blocktime: int = 1
    kmp_affinity: str = "granularity=fine,compact,1,0"
    numactl_interleave: bool = False
    stagger_start_seconds: float = 2.0
    instances_per_numa: int = 1
    disable_hyperthreading_use: bool = True
    force_isa: str | None = None
    use_ipex: bool = True
    ipex_weight_prepack: bool = True
    ipex_onednn_layout: bool = True
    ipex_jit_linear_repack: bool = True
    bf16_enabled: bool = True


@dataclass
class AutoTuneConfig:
    enabled: bool = False
    warmup_seconds: float = 20.0
    healthcheck_timeout_s: float = 300.0
    candidate_omp_threads: list[int] = field(default_factory=lambda: [16, 24, 32, 48, 64])
    candidate_instances_per_numa: list[int] = field(default_factory=lambda: [1, 2])
    candidate_max_num_seqs: list[int] = field(default_factory=lambda: [128, 192, 256])
    candidate_stagger_start_seconds: list[float] = field(default_factory=lambda: [1.0, 2.0])
    benchmark_requests_per_scenario: int = 40
    benchmark_concurrency_values: list[int] = field(default_factory=lambda: [8, 16, 32, 64])
    benchmark_context_lengths: list[int] = field(default_factory=lambda: [1024, 2048, 3072, 4096, 6144, 8192])
    output_dir: str = "artifacts/autotune"


@dataclass
class BenchmarkConfig:
    endpoint_base_url: str = "http://127.0.0.1:8000/v1"
    model: str = ""
    timeout_s: float = 180.0
    concurrency_values: list[int] = field(default_factory=lambda: list(range(1, 101)))
    context_lengths: list[int] = field(default_factory=lambda: [1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192])
    max_tokens: int = 256
    temperature: float = 0.0
    requests_per_scenario: int = 100
    stagger_wave_size: int = 8
    stagger_wave_delay_s: float = 0.25
    output_dir: str = "artifacts/benchmarks"


@dataclass
class EngineConfig:
    model: ModelConfig
    xeon_tuning: XeonTuningConfig = field(default_factory=XeonTuningConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    autotune: AutoTuneConfig = field(default_factory=AutoTuneConfig)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "EngineConfig":
        model = ModelConfig(**data["model"])
        xeon = XeonTuningConfig(**data.get("xeon_tuning", {}))
        benchmark = BenchmarkConfig(**data.get("benchmark", {}))
        autotune = AutoTuneConfig(**data.get("autotune", {}))
        if not benchmark.model:
            benchmark.model = model.model
        return EngineConfig(model=model, xeon_tuning=xeon, benchmark=benchmark, autotune=autotune)


def load_config(path: str | Path) -> EngineConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError("Configuration root must be a mapping")
    return EngineConfig.from_dict(raw)
