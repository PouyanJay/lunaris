// The keyless inference Container App — a scale-to-zero llama.cpp server that hosts the keyless chat
// model (Qwen2.5-3B) so an unkeyed account can build in Draft mode (keyless-fallbacks T8). Built from
// infra/inference/Dockerfile and pushed to ACR by CD, like the API.
//
// CPU by default: Qwen2.5-3B is small + GQA-light, so this runs on the built-in Consumption (CPU)
// profile — no GPU and no GPU quota needed. Scale-to-zero means you pay only while a build runs; the
// cost is a cold start (~30–90s) on the first build after idle, surfaced via GET /api/keyless/readiness.
//
// GPU (optional speed upgrade): pass `gpuWorkloadProfileName` (a serverless/Consumption GPU profile
// that exists + has quota in your region — e.g. Consumption-GPU-NC8as-T4) AND build the image from
// the CUDA base (see the Dockerfile). CPU is slower (a build takes minutes) but needs no quota.
//
// The embeddings service (bge-large-en-v1.5) is deployed separately (see inference/README).

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference for the inference server, e.g. <acr>.azurecr.io/lunaris-inference:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string

@description('Optional GPU workload profile name (a serverless/Consumption GPU profile with quota, e.g. Consumption-GPU-NC8as-T4). Empty (the default) runs on CPU via the built-in Consumption profile — no GPU quota needed.')
param gpuWorkloadProfileName string = ''

@description('vCPU/memory for the container. The default (2 vCPU / 4Gi) is the max a Consumption-Only environment allows and fits the ~1.9GB Qwen2.5-3B Q4 model; a GPU profile sets its own capacity.')
param cpu string = '2.0'
param memory string = '4Gi'

// CPU runs on the env's default profile, so `workloadProfileName` is OMITTED entirely — a
// Consumption-Only environment rejects the property even with the value "Consumption". Only a GPU
// profile name (which requires a workload-profiles environment) adds it back, via union() below.
var gpuProfile = empty(gpuWorkloadProfileName) ? {} : { workloadProfileName: gpuWorkloadProfileName }

// Internal-only ingress: the API reaches it over the managed environment's private network; it is
// never exposed to the public internet (no browser talks to it directly).
var containerAppName = 'lunaris-${env}-inference'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'keyless-inference' }

resource inference 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityResourceId}': {}
    }
  }
  properties: union(gpuProfile, {
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
          name: 'inference'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          // llama.cpp's /health returns 200 when the model is loaded, 503 while loading — the same
          // signal GET /api/keyless/readiness maps to ready / provisioning.
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
        // Scale to zero when idle (pay only during a build); one warm replica is plenty for the
        // serialized keyless build tier (LUNARIS_DRAFT_MAX_CONCURRENT defaults to 1).
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '1' } }
          }
        ]
      }
    }
  })
}

// The internal URL the API points LUNARIS_FALLBACK_LLM_BASE_URL at (app.bicep's keylessLlmBaseUrl).
output internalChatBaseUrl string = 'https://${inference.properties.configuration.ingress.fqdn}/v1'
