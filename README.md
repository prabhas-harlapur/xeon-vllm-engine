# Xeon 6 vLLM Inference Engine

NUMA-aware, Xeon-focused inference orchestration and benchmarking toolkit for vLLM on Intel Xeon 6 class servers.

## What this provides

- NUMA topology discovery and CPU pinning strategy generation
- Xeon-oriented environment tuning (OpenMP, oneDNN/Intel runtime-friendly defaults)
- Automatic ISA path selection (AMX -> AVX-512 -> AVX2 fallback) via CPU flag detection
- Optional IPEX runtime optimization path
- vLLM launch wrapper with per-node pinning and staggered startup
- Async benchmark runner:
  - Concurrency: `1` to `100`
  - Context length: `1k` to `8k`
- Auto-tuning sweep for thread and scheduler settings
- Structured results (JSON + CSV) and HTML dashboard generation
- Prometheus + Grafana monitoring assets
- Kubernetes deployment package

## Quick start

1. Create environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
pip install vllm intel-extension-for-pytorch
```

2. Configure engine:

```powershell
Copy-Item .\configs\xeon6.example.yaml .\configs\xeon6.local.yaml
```

3. Launch vLLM:

```powershell
python .\scripts\launch_xeon_vllm.py --config .\configs\xeon6.local.yaml
```

4. Run benchmark matrix:

```powershell
python .\scripts\benchmark_xeon_vllm.py --config .\configs\xeon6.local.yaml
```

5. Run auto-tuning:

```powershell
python .\scripts\autotune_xeon_vllm.py --config .\configs\xeon6.local.yaml
```

6. Build benchmark dashboard:

```powershell
python .\scripts\build_benchmark_dashboard.py --stats-csv .\artifacts\benchmarks\<timestamp>\scenario_stats.csv --output .\artifacts\benchmarks\<timestamp>\dashboard.html
```

## AVX-512 and AMX behavior

At launch, CPU flags are detected using `lscpu` and the engine sets:

- `ONEDNN_MAX_CPU_ISA`
- `DNNL_MAX_CPU_ISA`
- `ATEN_CPU_CAPABILITY=avx512` when AVX-512 class ISA is selected

Selection order:

1. `AVX512_CORE_AMX` (AMX tile + BF16 present)
2. `AVX512_CORE`
3. `AVX2`
4. `DEFAULT`

Override with `xeon_tuning.force_isa`.

## IPEX integration

Config flags:

- `xeon_tuning.use_ipex`
- `xeon_tuning.ipex_weight_prepack`
- `xeon_tuning.ipex_onednn_layout`
- `xeon_tuning.ipex_jit_linear_repack`
- `xeon_tuning.bf16_enabled`

If IPEX is not installed, launcher logs and falls back safely.

## Monitoring

`deploy/docker-compose.yml` includes:

- `xeon-vllm`
- `prometheus` on `:9090`
- `grafana` on `:3000`

Grafana provisioning files are under `monitoring/grafana`.

## Kubernetes

Apply all manifests:

```bash
kubectl apply -k deploy/k8s
```

## Remote run via jump host

```powershell
.\scripts\remote_benchmark_via_jump.ps1 `
  -JumpHost "<jump_ip>" -JumpPort <jump_port> -JumpUser "<jump_user>" `
  -TargetHost "<xeon_private_ip>" -TargetPort 22 -TargetUser "<xeon_user>" `
  -PpkPath "C:\path\to\key.ppk" `
  -RemoteProjectDir "~/xeon-engine" `
  -RemoteConfigPath "configs/xeon6.local.yaml"
```

Keep credentials out of repo files.
