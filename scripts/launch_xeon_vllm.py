from xeon_vllm_engine.cli import launch_cmd


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Launch Xeon optimized vLLM")
    parser.add_argument("--config", required=True, help="Path to configuration YAML")
    args = parser.parse_args()
    launch_cmd(args.config)

