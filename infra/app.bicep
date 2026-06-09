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

@description('When true, inject the BYOK AES master key from Key Vault as LUNARIS_KEY_ENC_MASTER (enables per-tenant encrypted key storage + the authed Settings keys panel). The secret MUST already exist in the vault or the deploy fails.')
param withByok bool = false

@description('Keyless (Draft) build tier on/off. False (the default until a keyless inference endpoint is wired) makes an unkeyed build a clean "add a key" 403 instead of failing mid-build with no model server. Flip to true once the serverless-GPU inference app is deployed (keyless-fallbacks T6/T8).')
param draftTierEnabled bool = false

@description('Internal base URL of the keyless chat endpoint (the inference.bicep app, e.g. https://lunaris-<env>-inference.internal…/v1). Empty = use the in-process default (localhost) — i.e. no keyless backend in this deployment.')
param keylessLlmBaseUrl string = ''

@description('Internal base URL of the keyless embeddings endpoint (the voyage-4-nano service). Empty = the localhost default.')
param keylessEmbeddingsBaseUrl string = ''

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

// BYOK master key (per-tenant key encryption) — one Key Vault secret mapped to LUNARIS_KEY_ENC_MASTER,
// wired only when withByok is set. Read from env only by the API (never the DB, never .env).
var byokSecretName = 'lunaris-key-enc-master'
var byokSecrets = withByok
  ? [
      {
        name: byokSecretName
        keyVaultUrl: '${keyVaultUri}secrets/${byokSecretName}'
        identity: managedIdentityResourceId
      }
    ]
  : []
var byokEnv = withByok ? [{ name: 'LUNARIS_KEY_ENC_MASTER', secretRef: byokSecretName }] : []

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
  { name: 'LUNARIS_DRAFT_TIER_ENABLED', value: string(draftTierEnabled) }
]

// Point the keyless fallbacks at the self-hosted inference endpoints when wired; otherwise omit the
// vars so the app keeps its localhost default (no keyless backend → keyless builds rely on the Draft
// toggle being off). Each is added only when non-empty.
var keylessLlmEnv = empty(keylessLlmBaseUrl)
  ? []
  : [{ name: 'LUNARIS_FALLBACK_LLM_BASE_URL', value: keylessLlmBaseUrl }]
var keylessEmbeddingsEnv = empty(keylessEmbeddingsBaseUrl)
  ? []
  : [{ name: 'LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL', value: keylessEmbeddingsBaseUrl }]
var keylessEnv = concat(keylessLlmEnv, keylessEmbeddingsEnv)

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
      // NOTE: this ingress block does not declare customDomains, so each deploy resets ingress and
      // drops any bound custom domain. cd-prod re-binds api.lunaris.pouyan.ai (+ its managed cert)
      // after every deploy via the "Restore API custom domain" step. dev has no custom domain.
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
      secrets: concat(baseSecrets, providerSecrets, byokSecrets)
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
          env: concat(baseEnv, providerEnv, byokEnv, keylessEnv)
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
