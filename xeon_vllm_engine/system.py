from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass
class NumaNode:
    node_id: int
    cpus: list[int]


@dataclass
class SystemTopology:
    sockets: int
    cores_per_socket: int
    threads_per_core: int
    numa_nodes: list[NumaNode]
    cpu_flags: set[str]

    @property
    def total_logical_cpus(self) -> int:
        return sum(len(node.cpus) for node in self.numa_nodes)


def _parse_cpu_list(value: str) -> list[int]:
    cpus: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", maxsplit=1)
            start, end = int(start_s), int(end_s)
            cpus.extend(range(start, end + 1))
        else:
            cpus.append(int(part))
    return sorted(set(cpus))


def _linux_topology() -> SystemTopology:
    out = subprocess.check_output(["lscpu"], text=True)
    sockets = _extract_int(out, r"Socket\(s\):\s+(\d+)", 1)
    cores_per_socket = _extract_int(out, r"Core\(s\) per socket:\s+(\d+)", os.cpu_count() or 1)
    threads_per_core = _extract_int(out, r"Thread\(s\) per core:\s+(\d+)", 1)
    numa_nodes_count = _extract_int(out, r"NUMA node\(s\):\s+(\d+)", 1)

    nodes: list[NumaNode] = []
    for idx in range(numa_nodes_count):
        match = re.search(rf"NUMA node{idx} CPU\(s\):\s+(.+)", out)
        if match:
            cpus = _parse_cpu_list(match.group(1))
        else:
            cpus = []
        nodes.append(NumaNode(node_id=idx, cpus=cpus))

    if not any(node.cpus for node in nodes):
        cpus = list(range(os.cpu_count() or 1))
        nodes = [NumaNode(node_id=0, cpus=cpus)]

    return SystemTopology(
        sockets=sockets,
        cores_per_socket=cores_per_socket,
        threads_per_core=threads_per_core,
        numa_nodes=nodes,
        cpu_flags=_extract_cpu_flags_linux(),
    )


def _extract_int(text: str, pattern: str, default: int) -> int:
    match = re.search(pattern, text)
    if not match:
        return default
    return int(match.group(1))


def detect_topology() -> SystemTopology:
    system = platform.system().lower()
    if system == "linux":
        return _linux_topology()

    cpus = list(range(os.cpu_count() or 1))
    return SystemTopology(
        sockets=1,
        cores_per_socket=len(cpus),
        threads_per_core=1,
        numa_nodes=[NumaNode(node_id=0, cpus=cpus)],
        cpu_flags=set(),
    )


def filtered_cpus_for_node(cpus: list[int], threads_per_core: int, disable_hyperthreading_use: bool) -> list[int]:
    if not disable_hyperthreading_use or threads_per_core <= 1:
        return cpus
    physical_count = max(1, len(cpus) // threads_per_core)
    return cpus[:physical_count]


def _extract_cpu_flags_linux() -> set[str]:
    try:
        out = subprocess.check_output(["lscpu"], text=True)
    except Exception:
        return set()

    for line in out.splitlines():
        if line.lower().startswith("flags:"):
            _, raw = line.split(":", maxsplit=1)
            return set(raw.strip().split())
    return set()


def detect_best_isa(cpu_flags: set[str]) -> str:
    has_amx = {"amx_tile", "amx_bf16"} <= cpu_flags
    if has_amx:
        return "AVX512_CORE_AMX"
    if {"avx512f", "avx512bw", "avx512vl"} <= cpu_flags:
        return "AVX512_CORE"
    if "avx2" in cpu_flags:
        return "AVX2"
    return "DEFAULT"
