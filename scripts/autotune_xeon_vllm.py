from xeon_vllm_engine.cli import autotune_cmd


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Auto-tune Xeon optimized vLLM")
    parser.add_argument("--config", required=True, help="Path to configuration YAML")
    args = parser.parse_args()
    autotune_cmd(args.config)

