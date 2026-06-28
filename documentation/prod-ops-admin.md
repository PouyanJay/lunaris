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

All of the below is wired through `cd-prod` — a prod promote deploys it. The control plane's URL is a
one-time GitHub-var setup after the first deploy (see step 3).

1. **RBAC (`infra/main.bicep`)** — the API identity gets, resource-group-scoped: **Cost Management
   Reader** (the cost *query* action), **Monitoring Reader** (metrics), **Reader** (container-apps
   run-state for the power read). Ships with the platform deployment.

2. **API env (`app.bicep`, passed by `cd-prod`)** — `cd-prod` passes `prodOpsSubscriptionId` (=
   `secrets.AZURE_SUBSCRIPTION_ID`) and `prodOpsResourceGroup` (= `vars.RESOURCE_GROUP`); app.bicep
   sets `PROD_OPS_SUBSCRIPTION_ID` / `PROD_OPS_RESOURCE_GROUP` / `PROD_OPS_MI_CLIENT_ID` (the API MI's
   client id) on the API container. (`IDENTITY_ENDPOINT`/`IDENTITY_HEADER` are auto-injected by ACA.)
   This makes the cost/compute/power-state **reads** go live immediately on promote.

3. **Control plane (`infra/prod-ops-control.bicep`, AD-3)** — the on/off **toggle** stops the API
   itself, so it can't be served by the API. `cd-prod` deploys a tiny scale-to-zero Container App
   (`lunaris-prod-control`, min 0 + ingress, ~$0 idle) running the same API image, with its **own**
   managed identity holding a **least-privilege custom role** (container-apps read + start + stop
   only). It verifies admin tokens via JWKS off `SUPABASE_URL` (same as the API in cloud) and allows
   the SPA origin via `corsOrigins`. The promote job **prints the control URL** (and a `::notice::`).
   **One-time:** set the GitHub var `VITE_PROD_CONTROL_URL` to that URL, then re-run the SPA build so
   the switch targets the control plane. Until then, the switch falls back to the API base (reads
   work; the toggle would 403 since the API identity has no start/stop) — so set the var before using
   the switch.

4. **Admin access** — set the GitHub var `LUNARIS_ADMIN_EMAILS` to include the operator's email (e.g.
   `pj.autech@gmail.com`); `cd-prod` passes it to both the API and the control app.

Everything below the Azure boundary is covered by tests; the real adapter, RBAC, and control plane
validate at deploy against live Azure.
