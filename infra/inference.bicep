// The keyless inference Container App — a serverless-GPU, scale-to-zero llama.cpp server that hosts
// the keyless chat model (Bonsai 8B) so an unkeyed account can build in Draft mode (keyless-fallbacks
// T8). Built from infra/inference/Dockerfile and pushed to ACR by CD, like the API.
//
// Scale-to-zero is the whole point: you pay for GPU only while a build runs. The cost is a cold start
// (~30–90s) on the first build after idle — surfaced in the UI via GET /api/keyless/readiness.
//
// ⚠ UNVERIFIED ON AZURE. Serverless-GPU workload profiles are region- + quota-gated and their names
// change; confirm `workloadProfileName` against your managed environment's available GPU profiles
// (e.g. a Consumption GPU profile) before deploying. This is a vetted starting point, not a tested
// deployment. The embeddings service (voyage-4-nano) is deployed separately (see inference/README).

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference for the inference server, e.g. <acr>.azurecr.io/lunaris-inference:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string

@description('The name of a GPU workload profile defined on the managed environment (serverless/Consumption GPU). MUST exist + be available in this region.')
param gpuWorkloadProfileName string

@description('vCPU/memory for the GPU container (the GPU itself comes from the workload profile).')
param cpu string = '4.0'
param memory string = '16Gi'

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
  properties: {
    managedEnvironmentId: managedEnvironmentId
    workloadProfileName: gpuWorkloadProfileName
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
  }
}

// The internal URL the API points LUNARIS_FALLBACK_LLM_BASE_URL at (app.bicep's keylessLlmBaseUrl).
output internalChatBaseUrl string = 'https://${inference.properties.configuration.ingress.fqdn}/v1'
