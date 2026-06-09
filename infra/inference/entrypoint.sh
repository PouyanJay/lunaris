#!/bin/sh
# Keyless chat inference entrypoint: run on GPU automatically when one is present, else on CPU.
#
# One image, both modes. The CUDA-built llama-server runs on CPU when no GPU is attached, so the only
# decision at boot is how many layers to offload: --n-gpu-layers 99 (all) on a GPU, 0 on CPU. ACA
# mounts the NVIDIA device into the container ONLY when it's scheduled on a GPU workload profile, so
# `/dev/nvidia0` is the reliable, dependency-free signal (no nvidia-smi needed). On a CPU profile the
# device is absent and we run pure CPU — the default, unchanged behaviour.
set -eu

# llama.cpp offloads min(N, model_layers) layers, so any N >= the model's depth means "all layers";
# 999 is the conventional saturate-everything sentinel (safe across model swaps). 0 is pure CPU.
GPU_LAYERS_ALL=999

NGL=0
if [ -e /dev/nvidia0 ]; then
    NGL="${GPU_LAYERS_ALL}"
    echo "lunaris-inference: GPU detected (/dev/nvidia0) -> offloading all layers (--n-gpu-layers ${NGL})"
else
    echo "lunaris-inference: no GPU (/dev/nvidia0 absent) -> CPU (--n-gpu-layers ${NGL})"
fi

# --ctx-size/-fit off/--parallel: the CPU-container memory guards (see Dockerfile); harmless on GPU.
exec /app/llama-server --host 0.0.0.0 --port 8080 \
    --model /models/qwen2.5-3b-instruct-q4_k_m.gguf --alias qwen2.5-3b-instruct \
    --ctx-size 16384 --parallel 1 -fit off --n-gpu-layers "${NGL}"
