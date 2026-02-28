from __future__ import annotations

import argparse
import asyncio
import signal
import time

from .autotune import AutoTuner
from .benchmark import VllmBenchmarker
from .config import load_config
from .launcher import launch


def launch_cmd(config_path: str) -> None:
    cfg = load_config(config_path)
    procs = launch(cfg)
    print(f"[launcher] started {len(procs)} process(es)")

    terminated = False

    def _signal_handler(signum, frame):  # noqa: ARG001
        nonlocal terminated
        if terminated:
            return
        terminated = True
        print(f"[launcher] received signal {signum}. terminating...")
        for p in procs:
            p.terminate()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"[launcher] process exited with code={p.returncode}")
                    terminated = True
            if terminated:
                break
            time.sleep(1)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except Exception:
                p.kill()


def benchmark_cmd(config_path: str) -> None:
    cfg = load_config(config_path)
    bench = VllmBenchmarker(cfg.benchmark)
    out_dir = asyncio.run(bench.run_matrix())
    print(f"[bench] outputs at: {out_dir}")


def autotune_cmd(config_path: str) -> None:
    cfg = load_config(config_path)
    tuner = AutoTuner(cfg)
    out_dir = tuner.run()
    print(f"[autotune] outputs at: {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xeon vLLM engine toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    launch_parser = sub.add_parser("launch", help="Launch vLLM with Xeon tuning")
    launch_parser.add_argument("--config", required=True, help="Path to yaml config")

    bench_parser = sub.add_parser("benchmark", help="Run benchmark matrix")
    bench_parser.add_argument("--config", required=True, help="Path to yaml config")

    tune_parser = sub.add_parser("autotune", help="Run auto-tuning benchmark sweep")
    tune_parser.add_argument("--config", required=True, help="Path to yaml config")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "launch":
        launch_cmd(args.config)
    elif args.command == "benchmark":
        benchmark_cmd(args.config)
    elif args.command == "autotune":
        autotune_cmd(args.config)
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
