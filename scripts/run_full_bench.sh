#!/bin/bash
set -e

# Configuration
CONFIG="configs/xeon6.local.yaml"
if [ ! -f "$CONFIG" ]; then
    echo "[remote] Setting up configuration..."
    mkdir -p configs
    if [ -f "configs/xeon6.example.yaml" ]; then
        cp configs/xeon6.example.yaml configs/xeon6.local.yaml
        echo "[remote] Created local config from example."
    elif [ -f "xeon6.example.yaml" ]; then
        cp xeon6.example.yaml configs/xeon6.local.yaml
        echo "[remote] Found example in root, moving to configs."
    else
        echo "[remote] ERROR: Could not find configs/xeon6.example.yaml"
        ls -R configs/ 2>/dev/null || echo "configs/ missing"
        exit 1
    fi
fi

# Setup Virtual Env
if [ ! -d ".venv" ]; then
    echo "[remote] Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "[remote] Installing lean CPU dependencies..."
export PIP_NO_CACHE_DIR=1
pip install -U pip
pip install -r requirements.txt
# Install vLLM specifically for CPU to avoid massive CUDA dependencies
pip install vllm-cpu intel-extension-for-pytorch

# Launch vLLM Engine
echo "[remote] Launching Xeon 6 vLLM Engine..."
python3 scripts/launch_xeon_vllm.py --config "$CONFIG" > artifacts/launch.log 2>&1 &
LAUNCH_PID=$!

# Wait for health
echo "[remote] Waiting for engine to be healthy..."
python3 -c "
import time, httpx
start = time.time()
while time.time() - start < 300:
    try:
        if httpx.get('http://127.0.0.1:8000/health').status_code < 500:
            print('Healthy!')
            exit(0)
    except:
        pass
    time.sleep(2)
exit(1)
"

# Run Benchmark
echo "[remote] Running benchmark matrix (Concurrency 1-100, Context 1k-8k)..."
python3 scripts/benchmark_xeon_vllm.py --config "$CONFIG"

# Get the latest benchmark directory
LATEST_BENCH=$(ls -td artifacts/benchmarks/*/ | head -1)

# Generate Dashboard
if [ -n "$LATEST_BENCH" ]; then
    echo "[remote] Generating dashboard for $LATEST_BENCH..."
    python3 scripts/build_benchmark_dashboard.py \
        --stats-csv "${LATEST_BENCH}scenario_stats.csv" \
        --output "${LATEST_BENCH}dashboard.html"
    echo "[remote] Dashboard generated: ${LATEST_BENCH}dashboard.html"
fi

# Cleanup
echo "[remote] Cleaning up..."
kill $LAUNCH_PID || true
echo "[remote] Done."
