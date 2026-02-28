from xeon_vllm_engine.cli import benchmark_cmd


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark Xeon optimized vLLM")
    parser.add_argument("--config", required=True, help="Path to configuration YAML")
    args = parser.parse_args()
    benchmark_cmd(args.config)

