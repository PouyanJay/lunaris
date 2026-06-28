// Prod-operations control plane (prod-ops-admin, AD-3).
//
// The production on/off switch STOPS the prod API itself, so the start/stop control cannot live in
// the API — once prod is off, the API can't turn it back on. This module is that always-on control
// plane: a tiny scale-to-zero Container App (min 0 + HTTP ingress, so the toggle request wakes it;
// ~$0 idle) running the SAME API image but serving only as the power-control endpoint, with its OWN
// managed identity holding a LEAST-PRIVILEGE custom role — container-apps read + start + stop only,
// never broad Contributor. The admin SPA points its toggle at this app (VITE_PROD_CONTROL_URL).
//
// Deploy:  az deployment group create -g rg-lunaris-prod -f infra/prod-ops-control.bicep -p ...

targetScope = 'resourceGroup'

@description('Azure region.')
param location string = resourceGroup().location

@description('Short prefix + environment, e.g. lunaris-prod.')
param namePrefix string = 'lunaris-prod'

@description('Resource id of the shared Container Apps managed environment.')
param acaEnvId string

@description('Fully-qualified API image the control app runs (same image as the API).')
param image string

@description('ACR login server (for the registry reference).')
param acrLoginServer string

@description('Resource id of the API managed identity used to pull from ACR.')
param acrPullIdentityId string

@description('Subscription id the control plane governs (for the start/stop calls).')
param subscriptionId string = subscription().subscriptionId

@description('Comma-separated admin email allowlist (the toggle is admin-gated).')
param adminEmails string = ''

@description('Supabase URL — the control app verifies admin tokens via JWKS off this, same as the API (cloud uses ES256/JWKS, not a shared secret).')
param supabaseUrl string

@description('Allowed CORS origin(s) — the admin SPA calls this app cross-origin for the toggle.')
param corsOrigins string = ''

var tags = {
  app: 'lunaris'
  env: 'prod'
  managedBy: 'bicep'
  component: 'prod-ops-control'
}

var controlMiName = '${namePrefix}-control-mi'
var controlAppName = '${namePrefix}-control'

// The control plane's own identity. It needs a LEAST-PRIVILEGE start/stop role on the resource group
// (container-apps read + start/action + stop/action), but RBAC is NOT created here: the CI service
// principal that runs cd-prod intentionally lacks roleDefinitions/roleAssignments write, so creating
// roles in this CI-deployed template fails the whole deploy. The custom role + assignment are applied
// ONCE, out-of-band, by an Owner (see documentation/prod-ops-admin.md) against this MI's principal id
// (surfaced as an output).
resource controlMi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: controlMiName
  location: location
  tags: tags
}

resource control 'Microsoft.App/containerApps@2024-03-01' = {
  name: controlAppName
  location: location
  tags: tags
  identity: {
    // The control MI signs the start/stop calls; the API MI is used only to pull the image.
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${controlMi.id}': {}
      '${acrPullIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: acaEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: acrPullIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'control'
          image: image
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'LUNARIS_ENV', value: 'prod' }
            // Verify admin tokens exactly as the API does in cloud (ES256/JWKS off SUPABASE_URL).
            { name: 'SUPABASE_URL', value: supabaseUrl }
            { name: 'LUNARIS_ADMIN_EMAILS', value: adminEmails }
            { name: 'LUNARIS_CORS_ORIGINS', value: corsOrigins }
            // Lean startup — this app only serves the prod-ops power route, never builds courses.
            { name: 'LUNARIS_PIPELINE', value: 'stub' }
            { name: 'LUNARIS_VIDEO_INPROC_WORKER', value: 'false' }
            // Activates the real Azure adapter; the control MI's client id authenticates start/stop.
            { name: 'PROD_OPS_SUBSCRIPTION_ID', value: subscriptionId }
            { name: 'PROD_OPS_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'PROD_OPS_MI_CLIENT_ID', value: controlMi.properties.clientId }
          ]
        }
      ]
      scale: {
        // Scale-to-zero: ~$0 idle; the toggle's HTTP request wakes a replica (cold start is fine for
        // an occasional admin action). Capped at one — this is a control plane, not a workload.
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

output controlFqdn string = control.properties.configuration.ingress.fqdn
output controlMiClientId string = controlMi.properties.clientId
output controlMiPrincipalId string = controlMi.properties.principalId
