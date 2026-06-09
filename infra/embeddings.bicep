// The keyless EMBEDDINGS Container App — a CPU, scale-to-zero llama.cpp server hosting voyage-4-nano
// over an OpenAI-compatible /v1/embeddings, so a keyless account can ground + retrieve without an
// embeddings key (keyless-fallbacks T8). Built from infra/inference/Dockerfile.embeddings.
//
// CPU, not GPU: the nano embedder is light, so unlike the chat server (inference.bicep) this needs
// no GPU workload profile — it runs on the default Consumption profile. Internal ingress only.
//
// ⚠ UNVERIFIED ON AZURE — confirm the voyage-4-nano GGUF + llama.cpp embedding compatibility (see the
// Dockerfile note). A vetted starting point, not a tested deployment.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference for the embeddings server, e.g. <acr>.azurecr.io/lunaris-embeddings:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string

@description('vCPU/memory for the embeddings container (CPU-only; the nano embedder is light).')
param cpu string = '1.0'
param memory string = '2Gi'

var containerAppName = 'lunaris-${env}-embeddings'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'keyless-embeddings' }

resource embeddings 'Microsoft.App/containerApps@2024-03-01' = {
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
        external: false // internal only — the API calls it over the private network
        targetPort: 8080
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
          name: 'embeddings'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8080 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        // Scale to zero when idle; a single warm replica covers the serialized keyless build tier.
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '4' } }
          }
        ]
      }
    }
  }
}

// The internal URL the API points LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL at (app.bicep's keylessEmbeddingsBaseUrl).
output internalEmbeddingsBaseUrl string = 'https://${embeddings.properties.configuration.ingress.fqdn}/v1'
