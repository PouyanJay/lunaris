# syntax=docker/dockerfile:1
#
# Keyless inference server for Lunaris (keyless-fallbacks T8): a llama.cpp server that exposes an
# OpenAI-compatible API for the keyless chat model (PrismML Bonsai 8B, native 1-bit) so an unkeyed
# account can build in Draft mode. Built to run on an Azure Container Apps **serverless GPU**
# (scale-to-zero) — see infra/inference.bicep and infra/inference/README.md.
#
# It serves:
#   - POST /v1/chat/completions   (the agent's planner + structured-output subagents)
#   - GET  /health                (200 ready / 503 loading) — what GET /api/keyless/readiness probes
#
# Embeddings (bge-large-en-v1.5) are a SEPARATE, CPU-light service — llama.cpp's --embeddings mode is
# exclusive with generation, so run a second llama-server for it (see README). The app points
# LUNARIS_FALLBACK_LLM_BASE_URL and LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL at the two endpoints.
#
# NOTE (unverified on Azure): the CUDA base tag, the GGUF URL, and the GPU profile must be confirmed
# against current llama.cpp + Azure ACA serverless-GPU docs for your region. Treat this as a vetted
# starting point, not a tested image.

# Prebuilt llama.cpp server with CUDA. Pin a specific tag in real use (":server-cuda" floats).
FROM ghcr.io/ggml-org/llama.cpp:server-cuda

# The keyless chat model. Bonsai 8B is ~1.2–1.5GB as 1-bit GGUF, so the image/model stays small and
# loads into VRAM in seconds (the cold start is dominated by GPU provisioning, not model load).
# Override at build time to swap the model: --build-arg MODEL_URL=… --build-arg MODEL_FILE=…
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
