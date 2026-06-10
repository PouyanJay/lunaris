# Keyless inference — deploy guide

This is the self-hosted model server that makes **keyless ("Draft") builds** actually work in prod.
An unkeyed account falls back to a local, no-API-key model; that model has to run *somewhere*, and
this is it: [llama.cpp](https://github.com/ggml-org/llama.cpp) servers on **Azure Container Apps**,
scale-to-zero, so you pay **only while a build runs**.

**CPU by default — no GPU, no GPU quota.** Qwen2.5-3B is small and GQA-light, so both services run on
the built-in Consumption (CPU) profile. A bigger model or GPU is an **optional upgrade** (see below),
not a requirement — which means you can deploy + test today without a quota request.

> **Status: scaffolded, NOT verified on Azure.** Treat the Dockerfiles + bicep as a vetted starting
> point. The model GGUF URLs are verified to exist on Hugging Face; the llama.cpp base tags and ACA
> behaviour should be confirmed for your environment before relying on them.

## What runs

| Service | Model | Compute | Endpoint env var (on the API) | Artifacts |
|---|---|---|---|---|
| Chat | Qwen2.5-3B-Instruct (Q4 GGUF) | CPU now; **auto-GPU** when on a GPU profile (see below) | `LUNARIS_FALLBACK_LLM_BASE_URL` | `Dockerfile` + `inference.bicep` |
| Embeddings | bge-large-en-v1.5 | CPU (Consumption), scale-to-zero | `LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL` | `Dockerfile.embeddings` + `../embeddings.bicep` |

They're **two services** because llama.cpp's `--embeddings` mode is exclusive with generation. Both
run as cheap CPU Container Apps and expose `:8080/v1` + `/health` over internal-only ingress.

Qwen2.5-3B being small (~1.9 GB Q4) with GQA is what makes CPU viable: weights + KV cache fit the 4
GiB ceiling, so a cold start is dominated by the **replica scaling from zero**, not model loading.

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

## GPU rollout (optional speed upgrade)

CPU is enough to run + test the keyless path, but a 3B model takes minutes per build. A GPU makes it
interactive **and** unlocks running a bigger (8B) model for better quality. **The image is already
GPU-ready** — the chat `Dockerfile` uses the CUDA llama.cpp base and `entrypoint.sh` auto-detects a
GPU at boot (`/dev/nvidia0` → `--n-gpu-layers 999`, else CPU). So the same image you run today on CPU
will use a GPU the moment it's scheduled onto one — no rebuild. What's left is the **infra**:

**Gate — GPU quota.** Serverless GPU is region-limited and starts at **0** quota; request it via an
Azure support ticket (*Help + support → Service and subscription limits (quotas) → Container Apps*),
e.g. `Consumption-GPU-NC8as-T4` in **West US 3**. Everything below waits on that approval.

**Gotcha — one environment.** The current platform env is **Consumption-Only** and can't host a GPU;
a GPU needs a **workload-profiles** environment, and you can't convert in place. And ACA internal
ingress is **per-environment** — the API reaches the inference over the env's private network — so the
**API + embeddings + chat must all live in the GPU env**. Practically, GPU = moving the keyless stack
onto a new workload-profiles environment (a platform move, like a region change; cd-prod already
re-binds the API custom domain on redeploy).

**Steps (after quota is approved):**

1. **Stand up the GPU environment** — `infra/gpu-env.bicep` (a workload-profiles env with a
   `Consumption` profile + a `gpu` profile):
   ```
   az deployment group create -g rg-lunaris-<env> -f infra/gpu-env.bicep \
     -p env=<env> location=westus3 \
        logAnalyticsCustomerId=<ws customerId> logAnalyticsSharedKey=<ws key> \
        gpuWorkloadProfileType=Consumption-GPU-NC8as-T4
   # → outputs managedEnvironmentId + gpuWorkloadProfileName (= "gpu")
   ```
2. **Deploy the apps into it** — re-run `inference.bicep` (chat) with `gpuWorkloadProfileName=gpu`
   and the new `managedEnvironmentId`; re-run `embeddings.bicep` + `app.bicep` against the same
   `managedEnvironmentId` (they stay on the Consumption profile). *(Optional: bump the chat model to
   an 8B GGUF via the Dockerfile `MODEL_URL`/`MODEL_FILE` build args — the GPU's VRAM is the point.)*
3. **Flip the badge** — set the per-env GitHub var **`LUNARIS_KEYLESS_COMPUTE=gpu`** and repoint the
   API's `LUNARIS_FALLBACK_LLM_BASE_URL` to the new chat app's internal URL, then redeploy the API.
4. **Verify** — a keyless build's chat container log should show `ggml_cuda_init: found N CUDA
   devices` + `offloaded N/N layers to GPU` (vs. today's `no usable GPU found … CPU`), and the Draft
   banner should read **GPU**.

## Honest caveats

- **It's not free.** Scale-to-zero means ~no cost while idle, but a build pays per-second while the
  replica is up; a warm/pinned replica pays continuously. At low volume a provider API key is usually
  cheaper — the keyless path wins on *no third-party key / data stays in your infra*, or at scale.
- **CPU is slow.** A 3B model on CPU produces a Draft course in minutes, not seconds. Fine for
  testing and low volume; use a bigger box / GPU for interactive speed.
- **Cold start** is ~30–90s on the first build after idle (replica scale-from-zero + model load). The
  readiness endpoint + provisioning UI exist precisely to make that honest, not hidden.
- **Draft quality is degraded** vs a keyed build (lighter depth + weaker verification); the small
  model's tool-calling is repaired but not perfect (see `resilience/tool_call_repair.py`).
