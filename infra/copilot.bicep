// The Lunaris Live CopilotKit runtime Container App (live-generative-surfaces T8) — the AG-UI
// transport hop between the browser and the API's session loop (`POST /api/live/sessions/{id}/agui`).
// Built from Dockerfile.copilot and pushed to ACR by CD, like the API. Its own app rather than a
// sidecar of the API: the SPA is a static build, so the runtime must be reachable at a stable
// public origin of its own, and it scales on open SSE streams rather than on API load.
//
// It holds NO credential (AD3): the learner's bearer token is forwarded untouched and the runtime
// authenticates as nobody, so — unlike app.bicep — nothing here is read from Key Vault. The only
// identity it carries is the platform's Managed Identity, for the ACR pull.
//
// The two things it needs are both plain configuration: where the API is (LUNARIS_API_URL) and which
// browser origins may call it (LUNARIS_COPILOT_ORIGINS — the SPA's, and nothing else; the runtime
// allows no origin by default). Tier 3 simulators stay off unless LUNARIS_LIVE_SIMS says otherwise,
// matching the API's own switch.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference, e.g. <acr>.azurecr.io/lunaris-copilot:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string

@description('Base URL of the Lunaris API this runtime forwards runs to, e.g. https://lunaris-dev-api.<region>.azurecontainerapps.io — resolved by CD from the API app that was just deployed.')
param apiBaseUrl string

@description('Browser origin(s) allowed to call this runtime, comma-separated — the SPA origin(s), the same value app.bicep receives as corsOrigins. Empty allows no origin.')
param allowedOrigins string = ''

@description('Tier 3 simulator registry switch, mirroring the API\'s LUNARIS_LIVE_SIMS. Empty (the default) registers nothing; "stub" serves the placeholder simulator. Set the same value on both apps or the socket disagrees with itself.')
param liveSims string = ''

@description('dev scales to zero to save cost; prod should be >=1 so a learner\'s first turn does not pay a cold start.')
param minReplicas int = (env == 'prod') ? 1 : 0
param maxReplicas int = 3

@description('vCPU/memory per replica. The runtime is a streaming proxy — no model calls, no rendering — so half a vCPU and 1Gi is ample.')
param cpu string = '0.5'
param memory string = '1Gi'

var containerAppName = 'lunaris-${env}-copilot'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'copilot-runtime' }

// The port main.ts listens on (its default, stated here so the ingress and the app agree in one
// place a reader can see).
var port = 8100

var baseEnv = [
  { name: 'PORT', value: string(port) }
  { name: 'LUNARIS_API_URL', value: apiBaseUrl }
  { name: 'LUNARIS_COPILOT_ORIGINS', value: allowedOrigins }
]
// Added only when set, so the app keeps its own default (off) rather than reading an empty string.
var simsEnv = empty(liveSims) ? [] : [{ name: 'LUNARIS_LIVE_SIMS', value: liveSims }]

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
        targetPort: port
        transport: 'auto'
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        { server: acrLoginServer, identity: managedIdentityResourceId }
      ]
    }
    template: {
      containers: [
        {
          name: 'copilot'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(baseEnv, simsEnv)
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: port }
              initialDelaySeconds: 5
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/healthz', port: port }
              initialDelaySeconds: 3
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            // A turn holds one SSE stream open for its whole length, and each open stream counts as a
            // concurrent request — so this is "learners mid-turn per replica", not requests per second.
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '40'
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
