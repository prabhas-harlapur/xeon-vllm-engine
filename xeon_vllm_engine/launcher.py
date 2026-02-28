from __future__ import annotations

import os
import platform
import shlex
import subprocess
import time
from dataclasses import dataclass

from .config import EngineConfig
from .ipex import ipex_env
from .system import detect_best_isa, detect_topology, filtered_cpus_for_node


@dataclass
class LaunchCommand:
    node_id: int
    command: list[str]
    env: dict[str, str]


def _common_vllm_args(config: EngineConfig, node_index: int, total_instances: int) -> list[str]:
    model = config.model
    port = model.port + node_index
    args = [
        "vllm",
        "serve",
        model.model,
        "--host",
        model.host,
        "--port",
        str(port),
        "--device",
        model.device,
        "--dtype",
        model.dtype,
        "--max-model-len",
        str(model.max_model_len),
        "--max-num-seqs",
        str(model.max_num_seqs),
    ]
    if model.device.lower() != "cpu":
        args.extend(["--gpu-memory-utilization", str(model.gpu_memory_utilization)])
    if total_instances > 1:
        args.extend(["--served-model-name", f"{model.model}-n{node_index}"])
    args.extend(model.extra_args)
    return args


def _base_env(config: EngineConfig, threads_for_instance: int, best_isa: str) -> dict[str, str]:
    tune = config.xeon_tuning
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(tune.omp_num_threads or threads_for_instance)
    env["KMP_BLOCKTIME"] = str(tune.kmp_blocktime)
    env["KMP_AFFINITY"] = tune.kmp_affinity
    env.setdefault("MALLOC_CONF", "background_thread:true,metadata_thp:auto")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    env.setdefault("VLLM_LOGGING_LEVEL", "INFO")
    env.setdefault("ONEDNN_MAX_CPU_ISA", best_isa)
    env.setdefault("DNNL_MAX_CPU_ISA", best_isa)
    if best_isa.startswith("AVX512"):
        env.setdefault("ATEN_CPU_CAPABILITY", "avx512")
    ipex_vars, notes = ipex_env(tune)
    env.update(ipex_vars)
    for note in notes:
        print(f"[launcher] {note}")
    return env


def build_launch_plan(config: EngineConfig) -> list[LaunchCommand]:
    topo = detect_topology()
    tune = config.xeon_tuning
    detected_isa = tune.force_isa or detect_best_isa(topo.cpu_flags)
    print(f"[launcher] detected ISA path: {detected_isa}")
    commands: list[LaunchCommand] = []
    is_linux = platform.system().lower() == "linux"
    node_instance = 0

    for node in topo.numa_nodes:
        node_cpus = filtered_cpus_for_node(
            node.cpus,
            threads_per_core=topo.threads_per_core,
            disable_hyperthreading_use=tune.disable_hyperthreading_use,
        )
        if not node_cpus:
            continue

        for _ in range(max(1, tune.instances_per_numa)):
            chunks = _split_evenly(node_cpus, max(1, tune.instances_per_numa))
            cpu_chunk = chunks[min(node_instance % len(chunks), len(chunks) - 1)]
            if not cpu_chunk:
                cpu_chunk = node_cpus

            env = _base_env(config, threads_for_instance=len(cpu_chunk), best_isa=detected_isa)
            cmd = _common_vllm_args(config, node_instance, _num_total_instances(config, topo))

            if is_linux:
                cpu_list = ",".join(str(cpu) for cpu in cpu_chunk)
                prefix = ["numactl", f"--cpunodebind={node.node_id}", f"--physcpubind={cpu_list}"]
                if tune.numactl_interleave:
                    prefix.append("--interleave=all")
                full_cmd = prefix + cmd
            else:
                full_cmd = cmd

            commands.append(LaunchCommand(node_id=node.node_id, command=full_cmd, env=env))
            node_instance += 1

    if not commands:
        env = _base_env(config, threads_for_instance=os.cpu_count() or 1, best_isa=detected_isa)
        commands.append(LaunchCommand(node_id=0, command=_common_vllm_args(config, 0, 1), env=env))
    return commands


def _num_total_instances(config: EngineConfig, topo) -> int:
    return max(1, len(topo.numa_nodes) * max(1, config.xeon_tuning.instances_per_numa))


def _split_evenly(values: list[int], parts: int) -> list[list[int]]:
    if parts <= 1:
        return [values]
    chunks: list[list[int]] = [[] for _ in range(parts)]
    for idx, value in enumerate(values):
        chunks[idx % parts].append(value)
    return chunks


def launch(config: EngineConfig) -> list[subprocess.Popen]:
    plans = build_launch_plan(config)
    processes: list[subprocess.Popen] = []
    delay = max(0.0, config.xeon_tuning.stagger_start_seconds)

    for idx, plan in enumerate(plans):
        printable = " ".join(shlex.quote(item) for item in plan.command)
        print(f"[launcher] node={plan.node_id} instance={idx} command={printable}")
        proc = subprocess.Popen(plan.command, env=plan.env)
        processes.append(proc)
        if idx < len(plans) - 1 and delay > 0:
            time.sleep(delay)

    return processes
