# Keyless inference — deploy guide

This is the self-hosted model server that makes **keyless ("Draft") builds** actually work in prod.
An unkeyed account falls back to a local, no-API-key model; that model has to run *somewhere*, and
this is it: [llama.cpp](https://github.com/ggml-org/llama.cpp) servers on **Azure Container Apps**,
scale-to-zero, so you pay **only while a build runs**.

**CPU by default — no GPU, no GPU quota.** Bonsai 8B is 1-bit and CPU-runnable, so both services run
on the built-in Consumption (CPU) profile. A GPU is an **optional speed upgrade** (see below), not a
requirement — which means you can deploy + test today without a quota request.

> **Status: scaffolded, NOT verified on Azure.** Treat the Dockerfiles + bicep as a vetted starting
> point. The model GGUF URLs are verified to exist on Hugging Face; the llama.cpp base tags and ACA
> behaviour should be confirmed for your environment before relying on them.

## What runs

| Service | Model | Compute | Endpoint env var (on the API) | Artifacts |
|---|---|---|---|---|
| Chat | Bonsai 8B (1-bit GGUF) | CPU (Consumption), scale-to-zero | `LUNARIS_FALLBACK_LLM_BASE_URL` | `Dockerfile` + `inference.bicep` |
| Embeddings | bge-large-en-v1.5 | CPU (Consumption), scale-to-zero | `LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL` | `Dockerfile.embeddings` + `../embeddings.bicep` |

They're **two services** because llama.cpp's `--embeddings` mode is exclusive with generation. Both
run as cheap CPU Container Apps and expose `:8080/v1` + `/health` over internal-only ingress.

Bonsai being 1-bit (~1.2–1.5 GB) is what makes CPU viable: the image and model load are small, so a
cold start is dominated by the **replica scaling from zero**, not model loading.

## How the app uses it

- The agent's keyless model (`build_keyless_chat_model`) and the keyless embedder point at those two
  base URLs (defaults are `http://localhost:8080/v1` for local dev).
- `GET /api/keyless/readiness` probes the chat server's `/health` (200 = ready, 503 = loading, a
  short-probe timeout = a scaling-from-zero replica) and the web shows a **"Provisioning…"** state so
  the first-build cold start isn't a silent wait.
- The operator switch `LUNARIS_DRAFT_TIER_ENABLED` gates the whole keyless tier (T6).

## Rollout sequence (safe, no mid-build failures)

1. **Ship the app with the Draft tier OFF** (`draftTierEnabled = false`, the default in `app.bicep`).
   An unkeyed user then gets a clean *"Draft builds are disabled — add a provider key"* `403`,
   instead of a build that starts and dies at the first model call because no server is wired yet.
2. **Build + push both inference images** to ACR — run the **`CD (inference images)`** workflow
   (`.github/workflows/cd-inference.yml`, manual `workflow_dispatch`). It builds the chat + embeddings
   images, SHA-tagged, and prints the two image refs in its summary.
3. **Deploy the two Container Apps** with those image refs (both CPU — no GPU profile, no quota):
   ```
   # Chat:
   az deployment group create -g rg-lunaris-<env> -f infra/inference.bicep \
     -p env=<env> image=<acr>/lunaris-inference:<sha> \
        managedEnvironmentId=<…> managedIdentityResourceId=<…> acrLoginServer=<…>
        # → outputs internalChatBaseUrl

   # Embeddings:
   az deployment group create -g rg-lunaris-<env> -f infra/embeddings.bicep \
     -p env=<env> image=<acr>/lunaris-embeddings:<sha> \
        managedEnvironmentId=<…> managedIdentityResourceId=<…> acrLoginServer=<…>
        # → outputs internalEmbeddingsBaseUrl
   ```
4. **Point the API at them and flip the tier on** — redeploy `app.bicep` with:
   `draftTierEnabled = true`, `keylessLlmBaseUrl = <internalChatBaseUrl>`,
   `keylessEmbeddingsBaseUrl = <internalEmbeddingsBaseUrl>`.
5. **Verify** with the pre-flight smoke check (it also warms the model):
   `python -m lunaris_runtime.resilience.smoke_check` → expect `ok`.

## GPU (optional speed upgrade)

CPU is enough to run + test the keyless path, but a build takes minutes. For interactive speed, move
the **chat** server to a GPU:

1. Build the chat image from the CUDA base — change `FROM …:server` to `…:server-cuda` in
   `infra/inference/Dockerfile`.
2. Get a serverless-GPU workload profile with quota in your region (e.g. `Consumption-GPU-NC8as-T4`),
   add it to the managed environment, and deploy `inference.bicep` with `gpuWorkloadProfileName=<it>`.
   (Serverless-GPU quota is often 0 by default and needs a request — that's the wait the CPU path
   avoids.) Embeddings stay on CPU.

## Honest caveats

- **It's not free.** Scale-to-zero means ~no cost while idle, but a build pays per-second while the
  replica is up; a warm/pinned replica pays continuously. At low volume a provider API key is usually
  cheaper — the keyless path wins on *no third-party key / data stays in your infra*, or at scale.
- **CPU is slow.** A 1-bit 8B on CPU produces a Draft course in minutes, not seconds. Fine for
  testing and low volume; use the GPU upgrade for interactive speed.
- **Cold start** is ~30–90s on the first build after idle (replica scale-from-zero + model load). The
  readiness endpoint + provisioning UI exist precisely to make that honest, not hidden.
- **Draft quality is degraded** vs a keyed build (lighter depth + weaker verification); the 1-bit
  model's tool-calling is repaired but not perfect (see `resilience/tool_call_repair.py`).
