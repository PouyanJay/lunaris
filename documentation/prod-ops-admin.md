# Prod operations (admin)

An admin-only **Prod operations** section in the Admin Portal: a cost-per-day chart, a compute
usage + cost dual-axis chart, and a full production on/off switch. Admin-gated by the
`LUNARIS_ADMIN_EMAILS` allowlist (the same gate as user management).

## What it shows / does

- **Cost per day**: daily Azure spend for `rg-lunaris-prod` (default 7 days, selectable 7/14/30).
  The most recent day is flagged *partial*: Azure Cost Management lags ~8 to 24h.
- **Compute per hour**: hourly replicas / CPU / memory usage (selectable) as bars, with the
  amortized hourly cost overlaid as a line.
- **Production power**: **off** stops every prod container app (API, video, cover, inference,
  embeddings workers and the Live copilot runtime) and **deallocates** the simulator supervisor VM
  (`lunaris-prod-sim-worker`). Deallocated, not powered off: a powered-off VM keeps billing for its
  compute. **on** starts them again (VM first, API last). Stopping is a self-inflicted outage, so the
  toggle requires an explicit confirmation and is audit-logged. Azure applies each start/stop in the
  background, so the switch lists every resource's status and follows the change until all of them
  have finished (a VM takes a few minutes). The control plane (`lunaris-prod-control`) is never
  governed: it is what serves the switch. **Out of scope:** Supabase (billed separately, not Azure).

### What still bills while production is off

Only storage: the container registry (~0.33 CAD/day), the VM's OS disk (~0.27 CAD/day) and its
Standard public IP (~0.17 CAD/day), plus a few cents of Key Vault and log retention. Roughly
**0.80 CAD/day**, against ~4.60 CAD/day with everything on (actual Azure costs as of Oct 2026). Removing that
floor means deleting resources, which the switch deliberately does not do.

### When production is off

Every visitor to the site sees a **Lunaris is offline** page (the SPA is a Static Web App, so it
stays up) with an *Email contact@pouyan.ai* action to request access. The page re-checks the API
every 15s and returns to the app by itself once production is back on.

An administrator turns production back on from the same page: **Administrator sign in** (sign-in
only), after which the page confirms admin access with the control plane (`GET /api/me` there, since
the API is stopped) and shows the power switch. The first answer can take up to a minute while the
scale-to-zero control plane wakes.

## How the data is sourced

The API reads Azure through its managed identity (`lunaris-prod-api-mi`), with no `azure-*` SDK: just
httpx against ARM, with the bearer token from the ACA-injected `IDENTITY_ENDPOINT`/`IDENTITY_HEADER`.
Locally / in CI (no Azure) an in-memory fake provides deterministic data, so the API and web are
fully testable; the real `AzureProdOpsProvider` activates only when `PROD_OPS_SUBSCRIPTION_ID` and
the MSI env are present.

## Deploy / configuration

`cd-prod` deploys the apps + env; **RBAC is applied once, out-of-band, by an Owner** (the CI service
principal intentionally lacks `roleDefinitions`/`roleAssignments` write, so role creation cannot live
in a CI-deployed template, where it would fail the promote). The control plane's URL is a one-time
GitHub-var setup after the first deploy (step 3).

0. **One-time RBAC (Owner, out-of-band)**: run once with an account that has Owner / User Access
   Administrator on `rg-lunaris-prod`. `main.bicep` also *declares* the three reader grants (idempotent
   if you ever redeploy it as an Owner), but CI never applies them, so apply them directly:
   ```bash
   RG=/subscriptions/<sub>/resourceGroups/rg-lunaris-prod
   API_MI=<lunaris-prod-api-mi principalId>          # az identity show -g rg-lunaris-prod -n lunaris-prod-api-mi --query principalId
   for R in "Cost Management Reader" "Monitoring Reader" "Reader"; do
     az role assignment create --assignee-object-id "$API_MI" --assignee-principal-type ServicePrincipal --role "$R" --scope "$RG"
   done
   # After the control app first deploys, grant its identity a least-privilege start/stop role:
   CTRL_MI=<lunaris-prod-control-mi principalId>      # az identity show -g rg-lunaris-prod -n lunaris-prod-control-mi --query principalId
   az role definition create --role-definition "$(jq -n --arg rg "$RG" '{Name:"Lunaris Prod-Ops Start/Stop",Description:"Read the run state of prod container apps and VMs and start/stop (deallocate) them; nothing else.",Actions:["Microsoft.App/containerApps/read","Microsoft.App/containerApps/start/action","Microsoft.App/containerApps/stop/action","Microsoft.Compute/virtualMachines/read","Microsoft.Compute/virtualMachines/instanceView/read","Microsoft.Compute/virtualMachines/start/action","Microsoft.Compute/virtualMachines/deallocate/action"],AssignableScopes:[$rg]}')"
   az role assignment create --assignee-object-id "$CTRL_MI" --assignee-principal-type ServicePrincipal --role "Lunaris Prod-Ops Start/Stop" --scope "$RG"
   # Upgrading a role created before the VM was governed (adds the four VM actions in place):
   az role definition update --role-definition "$(az role definition list --custom-role-only true --query "[?roleName=='Lunaris Prod-Ops Start/Stop'] | [0]" -o json | jq '.permissions[0].actions += ["Microsoft.Compute/virtualMachines/read","Microsoft.Compute/virtualMachines/instanceView/read","Microsoft.Compute/virtualMachines/start/action","Microsoft.Compute/virtualMachines/deallocate/action"] | .permissions[0].actions |= unique')"
   ```

1. **RBAC roles**: the API identity needs **Cost Management Reader** (the cost *query* action),
   **Monitoring Reader** (metrics), **Reader** (container-apps run-state for the power read); the
   control identity needs the least-privilege start/stop role above (container apps plus the VM's
   read/start/deallocate). Applied via step 0. Without the VM actions, OFF stops every app but reports
   the VM as refused (a 502 naming it), and the VM keeps running and billing.

2. **API env (`app.bicep`, passed by `cd-prod`)**: `cd-prod` passes `prodOpsSubscriptionId` (=
   `secrets.AZURE_SUBSCRIPTION_ID`) and `prodOpsResourceGroup` (= `vars.RESOURCE_GROUP`); app.bicep
   sets `PROD_OPS_SUBSCRIPTION_ID` / `PROD_OPS_RESOURCE_GROUP` / `PROD_OPS_MI_CLIENT_ID` (the API MI's
   client id) on the API container. (`IDENTITY_ENDPOINT`/`IDENTITY_HEADER` are auto-injected by ACA.)
   This makes the cost/compute/power-state **reads** go live immediately on promote.

3. **Control plane (`infra/prod-ops-control.bicep`, AD-3)**: the on/off **toggle** stops the API
   itself, so it can't be served by the API. `cd-prod` deploys a tiny scale-to-zero Container App
   (`lunaris-prod-control`, min 0 + ingress, ~$0 idle) running the same API image, with its **own**
   managed identity (the **least-privilege start/stop role** on that identity is the out-of-band
   step 0; the bicep creates the app + identity only, never RBAC). It verifies admin tokens via JWKS off
   `SUPABASE_URL` (same as the API in cloud) and allows the SPA origin via `corsOrigins`. The step runs
   **last and non-fatally** in `cd-prod` (it must never block the API promote or the domain restore).
   The promote job **prints the control URL** (and a `::notice::`).
   **One-time:** set the GitHub var `VITE_PROD_CONTROL_URL` to that URL, then re-run the SPA build so
   the switch targets the control plane. Until then, the switch falls back to the API base (reads
   work; the toggle would 403 since the API identity has no start/stop), so set the var before using
   the switch.

4. **Admin access**: set the GitHub var `LUNARIS_ADMIN_EMAILS` to include the operator's email (e.g.
   `pj.autech@gmail.com`); `cd-prod` passes it to both the API and the control app.

Everything below the Azure boundary is covered by tests; the real adapter, RBAC, and control plane
validate at deploy against live Azure.
