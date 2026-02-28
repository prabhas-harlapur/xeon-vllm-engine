from __future__ import annotations

from typing import Tuple

from .config import XeonTuningConfig


def detect_ipex() -> bool:
    try:
        import intel_extension_for_pytorch  # noqa: F401

        return True
    except Exception:
        return False


def ipex_env(tune: XeonTuningConfig) -> Tuple[dict[str, str], list[str]]:
    env: dict[str, str] = {}
    notes: list[str] = []
    if not tune.use_ipex:
        return env, notes

    has_ipex = detect_ipex()
    if not has_ipex:
        notes.append("IPEX requested but not installed. Continuing without IPEX module.")
        return env, notes

    env["IPEX_ONEDNN_LAYOUT"] = "1" if tune.ipex_onednn_layout else "0"
    env["IPEX_WEIGHT_PREPACK"] = "1" if tune.ipex_weight_prepack else "0"
    env["IPEX_JIT_LINEAR_REPACK"] = "1" if tune.ipex_jit_linear_repack else "0"
    if tune.bf16_enabled:
        env["TORCH_CPU_ACCELERATOR"] = "bf16"
    notes.append("IPEX optimizations enabled.")
    return env, notes

