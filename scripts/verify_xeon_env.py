#!/usr/bin/env python3
import os
import platform
import subprocess
import json
import socket
from pathlib import Path

def get_cpu_info():
    info = {
        "model_name": "Unknown",
        "flags": [],
        "amx_detected": False,
        "avx512_detected": False,
        "numa_nodes": 0
    }
    
    if platform.system().lower() != "linux":
        info["model_name"] = platform.processor()
        return info

    try:
        lscpu = subprocess.check_output(["lscpu"], text=True)
        for line in lscpu.splitlines():
            if "Model name:" in line:
                info["model_name"] = line.split(":", 1)[1].strip()
            if "flags:" in line.lower() or "Flags:" in line:
                flags = line.split(":", 1)[1].strip().split()
                info["flags"] = flags
                info["amx_detected"] = any("amx" in f.lower() for f in flags)
                info["avx512_detected"] = any("avx512" in f.lower() for f in flags)
            if "NUMA node(s):" in line:
                info["numa_nodes"] = int(line.split(":", 1)[1].strip())
    except Exception as e:
        info["error"] = str(e)
    
    return info

def get_software_env():
    env = {
        "pytorch_version": "Not Found",
        "ipex_version": "Not Found",
        "ipex_available": False,
        "vllm_version": "Not Found"
    }
    
    try:
        import torch
        env["pytorch_version"] = torch.__version__
    except ImportError:
        pass
        
    try:
        import intel_extension_for_pytorch as ipex
        env["ipex_version"] = ipex.__version__
        env["ipex_available"] = True
    except ImportError:
        pass

    try:
        import vllm
        # vllm doesn't always have __version__ in a simple place, try to get from package
        import importlib.metadata
        env["vllm_version"] = importlib.metadata.version("vllm")
    except Exception:
        pass
        
    return env

def main():
    print("="*60)
    print("      XEON 6 INFERENCE ENVIRONMENT VERIFICATION")
    print("="*60)
    
    host = socket.gethostname()
    print(f"Hostname: {host}")
    print(f"OS:       {platform.system()} {platform.release()}")
    
    cpu = get_cpu_info()
    print(f"\n[CPU INFO]")
    print(f"Model:      {cpu['model_name']}")
    print(f"NUMA Nodes: {cpu['numa_nodes']}")
    print(f"AMX Support: {'YES' if cpu['amx_detected'] else 'NO'}")
    print(f"AVX512:     {'YES' if cpu['avx512_detected'] else 'NO'}")
    
    sw = get_software_env()
    print(f"\n[SOFTWARE ENV]")
    print(f"PyTorch:    {sw['pytorch_version']}")
    print(f"IPEX:       {sw['ipex_version']} (Available: {sw['ipex_available']})")
    print(f"vLLM:       {sw['vllm_version']}")
    
    print("\n[OPTIMIZATION CHECK]")
    if cpu['amx_detected']:
        print("PASS: AMX ISA detected - ready for high-performance BF16 inference.")
    else:
        print("WARN: AMX ISA not detected. Performance might be limited to AVX-512.")
        
    if sw['ipex_available']:
        print("PASS: Intel Extension for PyTorch detected.")
    else:
        print("INFO: IPEX not detected. vLLM will use stock PyTorch paths.")

    print("\n" + "="*60)

if __name__ == "__main__":
    main()
