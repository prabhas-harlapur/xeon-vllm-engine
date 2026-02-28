from __future__ import annotations

import random


def synthetic_prompt(target_tokens: int) -> str:
    seed_words = [
        "intel",
        "xeon",
        "latency",
        "throughput",
        "numa",
        "scheduler",
        "attention",
        "batching",
        "prefill",
        "decode",
        "pipeline",
        "cache",
        "thread",
        "token",
    ]
    rng = random.Random(target_tokens)
    words = [rng.choice(seed_words) for _ in range(max(16, target_tokens))]
    return " ".join(words)

