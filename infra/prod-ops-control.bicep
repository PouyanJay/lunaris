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
@secure()
param adminEmails string

@description('Supabase JWT secret / JWKS config the control app verifies admin tokens with.')
@secure()
param supabaseJwtSecret string

var tags = {
  app: 'lunaris'
  env: 'prod'
  managedBy: 'bicep'
  component: 'prod-ops-control'
}

var controlMiName = '${namePrefix}-control-mi'
var controlAppName = '${namePrefix}-control'

// LEAST-PRIVILEGE custom role: exactly the container-apps actions the on/off switch needs — read the
// run state, start, and stop. No write/delete, no other resource types. Scoped to this RG only.
resource startStopRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'prod-ops-start-stop')
  properties: {
    roleName: 'Lunaris Prod-Ops Start/Stop (${resourceGroup().name})'
    description: 'Read container-apps run state and start/stop them — nothing else.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [
      {
        actions: [
          'Microsoft.App/containerApps/read'
          'Microsoft.App/containerApps/start/action'
          'Microsoft.App/containerApps/stop/action'
        ]
        notActions: []
      }
    ]
  }
}

resource controlMi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: controlMiName
  location: location
  tags: tags
}

resource startStopAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, controlMi.id, startStopRole.id)
  properties: {
    roleDefinitionId: startStopRole.id
    principalId: controlMi.properties.principalId
    principalType: 'ServicePrincipal'
  }
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
      secrets: [
        { name: 'admin-emails', value: adminEmails }
        { name: 'supabase-jwt-secret', value: supabaseJwtSecret }
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
            { name: 'LUNARIS_ADMIN_EMAILS', secretRef: 'admin-emails' }
            { name: 'SUPABASE_JWT_SECRET', secretRef: 'supabase-jwt-secret' }
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
