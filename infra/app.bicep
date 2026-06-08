// The Lunaris API Container App — deployed per image by CD (build-once-promote), separate from the
// stable platform (main.bicep). References the platform's Managed Identity for ACR pull + Key Vault
// secret reads, and pulls its secret values from Key Vault at deploy time.
//
// Deploy (dev):
//   az deployment group create -g rg-lunaris-dev -f infra/app.bicep \
//     -p env=dev managedEnvironmentId=<...> managedIdentityResourceId=<...> \
//        acrLoginServer=<...> keyVaultUri=<...> supabaseUrl=<...> image=<acr>/lunaris-api:<tag>

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference, e.g. lunarisdevacr….azurecr.io/lunaris-api:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string
param keyVaultUri string

@description('Supabase project API URL (not secret).')
param supabaseUrl string

@description('Allowed browser origin(s) for CORS, comma-separated.')
param corsOrigins string = ''

@description('Pipeline mode. stub = no LLM keys needed (cheap smoke test); agent = real builds.')
@allowed(['agent', 'live', 'stub'])
param pipeline string = 'stub'

@description('When true, also inject the LLM/search provider keys from Key Vault (needed by the agent/live pipeline). Each referenced secret MUST already exist in the vault or the deploy fails.')
param withProviderKeys bool = false

@description('dev scales to zero to save cost; prod should be >=1 so in-flight builds survive.')
param minReplicas int = (env == 'prod') ? 1 : 0
param maxReplicas int = 3
param cpu string = '1.0'
param memory string = '2Gi'

var containerAppName = 'lunaris-${env}-api'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep' }

// Key Vault secret names the app maps to env vars. Each must already exist in the vault (CD/setup
// loads them) — a reference to a missing secret fails the deploy.
var supabaseServiceRoleSecret = 'supabase-service-role-key'

// LLM/search provider keys — only wired when withProviderKeys is set (the agent/live pipeline). Each
// is one Key Vault secret name mapped to the env var the app reads (os.getenv in composition.py).
var providerKeys = [
  { secret: 'anthropic-api-key', envVar: 'ANTHROPIC_API_KEY' }
  { secret: 'embeddings-api-key', envVar: 'EMBEDDINGS_API_KEY' }
  { secret: 'search-api-key', envVar: 'SEARCH_API_KEY' }
  { secret: 'youtube-api-key', envVar: 'YOUTUBE_API_KEY' }
]

var providerSecretsAll = [
  for k in providerKeys: {
    name: k.secret
    keyVaultUrl: '${keyVaultUri}secrets/${k.secret}'
    identity: managedIdentityResourceId
  }
]
var providerEnvAll = [for k in providerKeys: { name: k.envVar, secretRef: k.secret }]

var providerSecrets = withProviderKeys ? providerSecretsAll : []
var providerEnv = withProviderKeys ? providerEnvAll : []

var baseSecrets = [
  {
    name: supabaseServiceRoleSecret
    keyVaultUrl: '${keyVaultUri}secrets/${supabaseServiceRoleSecret}'
    identity: managedIdentityResourceId
  }
]

var baseEnv = [
  { name: 'SUPABASE_URL', value: supabaseUrl }
  { name: 'SUPABASE_SERVICE_ROLE_KEY', secretRef: supabaseServiceRoleSecret }
  { name: 'LUNARIS_PIPELINE', value: pipeline }
  { name: 'LUNARIS_CORS_ORIGINS', value: corsOrigins }
  { name: 'LUNARIS_ENV', value: env }
]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityResourceId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        { server: acrLoginServer, identity: managedIdentityResourceId }
      ]
      secrets: concat(baseSecrets, providerSecrets)
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(baseEnv, providerEnv)
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '6'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
