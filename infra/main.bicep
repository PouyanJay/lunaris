// Platform infrastructure for one Lunaris environment (dev | prod) on Azure.
//
// Creates the stable resources that rarely change: Log Analytics, the Container Apps managed
// environment, an ACR, a Key Vault, a user-assigned Managed Identity (the API's identity for
// Key Vault + ACR pull), and a Static Web App for the SPA. The Container App itself is deployed
// separately by app.bicep (per image, by CD) — this file owns only the platform.
//
// Deploy:  az deployment group create -g rg-lunaris-dev -f infra/main.bicep -p infra/main.dev.bicepparam

targetScope = 'resourceGroup'

@description('Azure region for the platform resources.')
param location string = resourceGroup().location

@description('Environment name — drives resource names + tags.')
@allowed(['dev', 'prod'])
param env string

@description('Static Web Apps is only offered in a subset of regions; westus2 is the nearest to westus.')
param swaLocation string = 'westus2'

@description('Short prefix for all resource names.')
param namePrefix string = 'lunaris'

var suffix = uniqueString(resourceGroup().id)
var tags = {
  app: 'lunaris'
  env: env
  managedBy: 'bicep'
}

// KV (≤24 chars) and ACR (alphanumeric only) need globally-unique names → fold in a short suffix.
var logName = '${namePrefix}-${env}-logs'
var acaEnvName = '${namePrefix}-${env}-aca-env'
var acrName = toLower('${namePrefix}${env}acr${suffix}')
var kvName = take('${namePrefix}-${env}-kv-${suffix}', 24)
var miName = '${namePrefix}-${env}-api-mi'
var swaName = '${namePrefix}-${env}-web'

// Built-in role definition ids.
var kvSecretsUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)
var acrPullRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: acaEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false // pull via the Managed Identity, never the admin user
  }
}

resource mi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: miName
  location: location
  tags: tags
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true // grant access by RBAC role, not access policies
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: env == 'prod' ? true : null // prod can't be accidentally purged
    publicNetworkAccess: 'Enabled'
  }
}

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: swaName
  location: swaLocation
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    allowConfigFileUpdates: true
    stagingEnvironmentPolicy: 'Enabled'
  }
}

// The API's identity may pull images and read secrets.
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, mi.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: mi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, mi.id, kvSecretsUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: kvSecretsUserRoleId
    principalId: mi.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output keyVaultName string = kv.name
output keyVaultUri string = kv.properties.vaultUri
output managedIdentityResourceId string = mi.id
output managedIdentityClientId string = mi.properties.clientId
output managedIdentityPrincipalId string = mi.properties.principalId
output managedEnvironmentId string = acaEnv.id
output staticWebAppName string = swa.name
output staticWebAppDefaultHostname string = swa.properties.defaultHostname
