# syntax=docker/dockerfile:1
#
# Keyless inference server for Lunaris (keyless-fallbacks T8): a llama.cpp server that exposes an
# OpenAI-compatible API for the keyless chat model (PrismML Bonsai 8B, native 1-bit) so an unkeyed
# account can build in Draft mode. Runs on an Azure Container Apps **serverless CPU** (the default
# Consumption profile, scale-to-zero) — no GPU and no GPU quota needed, because Bonsai is 1-bit and
# CPU-runnable. A GPU is an optional speed upgrade (see the note below). See infra/inference.bicep.
#
# It serves:
#   - POST /v1/chat/completions   (the agent's planner + structured-output subagents)
#   - GET  /health                (200 ready / 503 loading) — what GET /api/keyless/readiness probes
#
# Embeddings (bge-large-en-v1.5) are a SEPARATE, CPU-light service — llama.cpp's --embeddings mode is
# exclusive with generation, so run a second llama-server for it (see README). The app points
# LUNARIS_FALLBACK_LLM_BASE_URL and LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL at the two endpoints.
#
# GPU (optional, for speed): swap the base image to ``:server-cuda`` and deploy inference.bicep with
# a GPU workload profile (gpuWorkloadProfileName) — that path needs serverless-GPU quota. CPU is
# slower (a build takes minutes) but needs no quota and is enough to run + test the keyless path.

# Prebuilt CPU llama.cpp server. Pin a specific tag in real use (":server" floats).
FROM ghcr.io/ggml-org/llama.cpp:server

# The keyless chat model. Bonsai 8B is ~1.2–1.5GB as a 1-bit GGUF, so the image/model stays small and
# loads in seconds (the cold start is dominated by the replica scaling from zero, not model load).
# The real 1-bit GGUF in the prism-ml/Bonsai-8B-gguf repo (verified to exist). Override at build
# time to swap: --build-arg MODEL_URL=… --build-arg MODEL_FILE=…
ARG MODEL_URL="https://huggingface.co/prism-ml/Bonsai-8B-gguf/resolve/main/Bonsai-8B-Q1_0.gguf"
ARG MODEL_FILE="Bonsai-8B-Q1_0.gguf"
ENV MODEL_PATH="/models/${MODEL_FILE}"

RUN mkdir -p /models && \
    curl -fSL "${MODEL_URL}" -o "${MODEL_PATH}"

EXPOSE 8080

# --host 0.0.0.0 so ACA ingress can reach it; --port 8080 matches the app's default base URL; the
# served model id "bonsai-8b" matches LUNARIS_FALLBACK_LLM_MODEL. --alias names it for /v1.
ENTRYPOINT ["/app/llama-server", "--host", "0.0.0.0", "--port", "8080", \
            "--model", "/models/Bonsai-8B-Q1_0.gguf", "--alias", "bonsai-8b"]
