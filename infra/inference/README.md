# Keyless inference (serverless GPU) — deploy guide

This is the self-hosted model server that makes **keyless ("Draft") builds** actually work in prod.
An unkeyed account falls back to a local, no-API-key model; that model has to run *somewhere*, and
this is it: a [llama.cpp](https://github.com/ggml-org/llama.cpp) server on an **Azure Container Apps
serverless GPU** (scale-to-zero), so you pay for GPU **only while a build runs**.

> **Status: scaffolded, NOT verified on Azure.** Serverless-GPU workload profiles are region- and
> quota-gated and their names change. Treat the Dockerfile + `infra/inference.bicep` as a vetted
> starting point and confirm the GPU profile, the CUDA base image, and the model GGUF URL against
> current docs for your region before relying on them.

## What runs

| Service | Model | Compute | Endpoint env var (on the API) |
|---|---|---|---|
| Chat | Bonsai 8B (1-bit GGUF) | **GPU**, scale-to-zero | `LUNARIS_FALLBACK_LLM_BASE_URL` |
| Embeddings | voyage-4-nano | CPU (light) | `LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL` |

They're **two services** because llama.cpp's `--embeddings` mode is exclusive with generation. The
chat server is the heavy/GPU one; embeddings is small enough for a cheap CPU container app (run a
second `llama-server --embeddings` from a similar Dockerfile, internal ingress, on `:8080/v1`).

Bonsai being 1-bit (~1.2–1.5 GB) is what makes this cheap: the image and VRAM load are small, so a
cold start is dominated by **GPU provisioning**, not model loading.

## How the app uses it

- The agent's keyless model (`build_keyless_chat_model`) and the keyless embedder point at those two
  base URLs (defaults are `http://localhost:8080/v1` for local dev).
- `GET /api/keyless/readiness` probes the chat server's `/health` (200 = ready, 503 = loading, a
  short-probe timeout = a scaling-from-zero replica) and the web shows a **"Provisioning GPU…"**
  state so the first-build cold start isn't a silent wait.
- The operator switch `LUNARIS_DRAFT_TIER_ENABLED` gates the whole keyless tier (T6).

## Rollout sequence (safe, no mid-build failures)

1. **Ship the app with the Draft tier OFF** (`draftTierEnabled = false`, the default in `app.bicep`).
   An unkeyed user then gets a clean *"Draft builds are disabled — add a provider key"* `403`,
   instead of a build that starts and dies at the first model call because no GPU is wired yet.
2. **Build + push the inference image(s)** to ACR (CD, like the API):
   `docker build -f infra/inference/Dockerfile -t <acr>/lunaris-inference:<sha> .`
3. **Deploy `infra/inference.bicep`** with a serverless GPU workload profile available in your region:
   ```
   az deployment group create -g rg-lunaris-<env> -f infra/inference.bicep \
     -p env=<env> image=<acr>/lunaris-inference:<sha> \
        managedEnvironmentId=<…> managedIdentityResourceId=<…> acrLoginServer=<…> \
        gpuWorkloadProfileName=<your-consumption-GPU-profile>
   ```
   It outputs `internalChatBaseUrl` (the internal `…/v1` URL).
4. **Point the API at it and flip the tier on** — redeploy `app.bicep` with:
   `draftTierEnabled = true`, `keylessLlmBaseUrl = <internalChatBaseUrl>`,
   `keylessEmbeddingsBaseUrl = <embeddings service …/v1>`.
5. **Verify** with the pre-flight smoke check (it also warms the GPU):
   `python -m lunaris_runtime.resilience.smoke_check` → expect `ok`.

## Honest caveats

- **It's not free.** Scale-to-zero means ~no cost while idle, but a build pays per-second of GPU; a
  warm/pinned replica pays continuously. At low volume, a provider API key is usually cheaper — the
  keyless path wins on *no third-party key / data stays in your infra*, or at sustained volume.
- **Cold start** is ~30–90s on the first build after idle (GPU provisioning + a few seconds of model
  load). The readiness endpoint + provisioning UI exist precisely to make that honest, not hidden.
- **Draft quality is degraded** vs a keyed build (lighter depth + weaker verification); the 1-bit
  model's tool-calling is repaired but not perfect (see `resilience/tool_call_repair.py`).
