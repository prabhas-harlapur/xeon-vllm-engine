#!/bin/bash
set -e

echo "[remote] Working directory: $(pwd)"
echo "[remote] Checking for zip file..."
if [ ! -f "xeon_engine.zip" ]; then
    echo "[remote] ERROR: xeon_engine.zip not found!"
    ls -la
    exit 1
fi

echo "[remote] Extracting codebase using Python..."
python3 -m zipfile -e xeon_engine.zip .

echo "[remote] Full directory structure (ls -R):"
ls -R

if [ ! -d "configs" ]; then
    echo "[remote] WARNING: configs directory missing, checking contents of current dir:"
    ls -F
fi

if [ ! -d "scripts" ]; then
    echo "[remote] ERROR: scripts directory not found after extraction!"
    exit 1
fi

chmod +x scripts/*.sh

echo "[remote] Running benchmark..."
bash scripts/run_full_bench.sh

echo "[remote] Zipping results..."
python3 -c 'import zipfile, os; z = zipfile.ZipFile("benchmark_results.zip", "w", zipfile.ZIP_DEFLATED); [z.write(os.path.join(r, f), os.path.relpath(os.path.join(r, f), os.getcwd())) for r, d, files in os.walk("artifacts") for f in files]'
echo "[remote] Done!"
