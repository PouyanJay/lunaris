# syntax=docker/dockerfile:1
#
# Keyless inference server for Lunaris (keyless-fallbacks T8): a llama.cpp server that exposes an
# OpenAI-compatible API for the keyless chat model (Qwen2.5-3B-Instruct) so an unkeyed account can
# build in Draft mode. Runs on an Azure Container Apps **serverless CPU** (the default Consumption
# profile, scale-to-zero) — no GPU and no GPU quota needed. Qwen2.5-3B is small + GQA-light, so it
# fits the Consumption ceiling of 2 vCPU / 4 GiB with a usable context. See infra/inference.bicep.
#
# It serves:
#   - POST /v1/chat/completions   (the agent's planner + structured-output subagents)
#   - GET  /health                (200 ready / 503 loading) — what GET /api/keyless/readiness probes
#
# Embeddings (bge-large-en-v1.5) are a SEPARATE, CPU-light service — llama.cpp's --embeddings mode is
# exclusive with generation, so run a second llama-server for it (see README). The app points
# LUNARIS_FALLBACK_LLM_BASE_URL and LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL at the two endpoints.
#
# Bigger model / GPU (optional, for quality or speed): a larger model (e.g. an 8B) needs more RAM
# than the 4 GiB Consumption ceiling — move to a workload-profiles environment with a memory-heavy
# or GPU profile (deploy inference.bicep with gpuWorkloadProfileName), which needs the matching quota.

# Prebuilt CPU llama.cpp server (mainline — no fork needed for a standard model). Pin a tag in real use.
FROM ghcr.io/ggml-org/llama.cpp:server

# The keyless chat model: Qwen2.5-3B-Instruct, Q4_K_M (~1.9GB, the official Qwen GGUF, verified to
# exist). Override at build time to swap: --build-arg MODEL_URL=… --build-arg MODEL_FILE=…
ARG MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
ARG MODEL_FILE="qwen2.5-3b-instruct-q4_k_m.gguf"
ENV MODEL_PATH="/models/${MODEL_FILE}"

RUN mkdir -p /models && \
    curl -fSL "${MODEL_URL}" -o "${MODEL_PATH}"

EXPOSE 8080

# --host 0.0.0.0 so ACA ingress can reach it; --port 8080 matches the app's default base URL; the
# served model id "qwen2.5-3b-instruct" matches LUNARIS_FALLBACK_LLM_MODEL. The memory caps matter on
# the 4 GiB Consumption container: --parallel 1 bounds the KV cache and -fit off stops llama.cpp's
# auto-fit from sizing to the NODE's RAM (which OOM-kills the smaller container).
#
# --ctx-size 16384: a full deep-agent build accumulates planner context (todo list + tool results)
# that overflowed an 8192 window mid-build (400 exceed_context_size_error). Qwen2.5-3B is GQA-light
# (2 KV heads, head_dim 128, 36 layers) → its KV cache at 16384 is only ~0.6 GiB, so model (~1.9 GiB)
# + KV + buffers fits the 4 GiB container with headroom (still well under n_ctx_train = 32768). The
# app also bounds prompts to this window via the keyless model profile (see build_keyless_chat_model),
# so summarization keeps the planner under the limit regardless.
ENTRYPOINT ["/app/llama-server", "--host", "0.0.0.0", "--port", "8080", \
            "--model", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", "--alias", "qwen2.5-3b-instruct", \
            "--ctx-size", "16384", "--parallel", "1", "-fit", "off"]
