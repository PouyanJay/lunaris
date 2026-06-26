# Prod operations (admin)

An admin-only **Prod operations** section in the Admin Portal: a cost-per-day chart, a compute
usage + cost dual-axis chart, and a full production on/off switch. Admin-gated by the
`LUNARIS_ADMIN_EMAILS` allowlist (the same gate as user management).

## What it shows / does

- **Cost per day** — daily Azure spend for `rg-lunaris-prod` (default 7 days, selectable 7/14/30).
  The most recent day is flagged *partial* — Azure Cost Management lags ~8–24h.
- **Compute per hour** — hourly replicas / CPU / memory usage (selectable) as bars, with the
  amortized hourly cost overlaid as a line.
- **Production power** — **off** stops the prod container apps (`az containerapp stop`), zeroing the
  always-on cost; only the ~$0.25/day container-registry floor remains. **on** starts them again.
  Stopping is a self-inflicted outage, so the toggle requires an explicit confirmation and is
  audit-logged. **Out of scope:** Supabase (billed separately, not Azure) is untouched.

## How the data is sourced

The API reads Azure through its managed identity (`lunaris-prod-api-mi`) — no `azure-*` SDK, just
httpx against ARM, with the bearer token from the ACA-injected `IDENTITY_ENDPOINT`/`IDENTITY_HEADER`.
Locally / in CI (no Azure) an in-memory fake provides deterministic data, so the API and web are
fully testable; the real `AzureProdOpsProvider` activates only when `PROD_OPS_SUBSCRIPTION_ID` and
the MSI env are present.

## Deploy / configuration

1. **RBAC (in `infra/main.bicep`)** — the API identity gets, resource-group-scoped:
   - **Cost Management Reader** (the cost *query* action),
   - **Monitoring Reader** (metrics),
   - **Reader** (container-apps run-state for the power read).
   These ship with the platform deployment; no manual step.

2. **API env (set on the prod API container app, via app.bicep / cd-prod):**
   - `PROD_OPS_SUBSCRIPTION_ID` — the subscription holding `rg-lunaris-prod`.
   - `PROD_OPS_RESOURCE_GROUP` — defaults to `rg-lunaris-prod`.
   - (`IDENTITY_ENDPOINT`/`IDENTITY_HEADER` are auto-injected by ACA; `AZURE_CLIENT_ID` is the API MI.)
   With these set, the cost/compute/power-state **reads** go live.

3. **Control plane (`infra/prod-ops-control.bicep`, AD-3)** — the on/off **toggle** stops the API
   itself, so it cannot be served by the API. This module deploys a tiny scale-to-zero Container App
   (`lunaris-prod-control`, min 0 + ingress, ~$0 idle) running the same API image, with its **own**
   managed identity holding a **least-privilege custom role** (container-apps read + start + stop
   only — never Contributor). Point the SPA at it with `VITE_PROD_CONTROL_URL`; it falls back to the
   API base for dev where the same route is served in-process.

4. **Admin access** — add the operator's email (e.g. `pj.autech@gmail.com`) to `LUNARIS_ADMIN_EMAILS`
   on both the API and the control app.

The reads (1–2) and the toggle's control plane (3) validate at deploy against live Azure; everything
below the Azure boundary is covered by unit/contract/integration tests.
