// A GPU-capable Container Apps environment for the keyless inference (OPTIONAL — off the default path).
//
// Why a separate environment: the default platform (main.bicep) creates a CONSUMPTION-ONLY managed
// environment, which cannot host a GPU. A GPU needs a WORKLOAD-PROFILES environment with a serverless
// GPU profile — and that profile needs GPU quota in the target region (request via an Azure support
// ticket; serverless GPU is region-limited, e.g. West US 3). You cannot convert a Consumption-Only
// environment in place, so this template stands up the workload-profiles environment alongside it.
//
// The environment carries TWO profiles: a "Consumption" profile (scale-to-zero CPU — for the API +
// embeddings) and a "gpu" profile (the serverless GPU — for the chat inference). They live together
// because ACA internal ingress is per-environment: the API reaches the inference over the env's
// private network, so the caller (the API, deployed via app.bicep) and the GPU app must share this
// environment — i.e. app.bicep + embeddings.bicep must also be redeployed here (see inference/README).
//
// Deploy (AFTER quota is approved), then redeploy the apps into this env's id — full sequence in
// infra/inference/README.md § "GPU rollout". The inference image is already GPU-ready (it auto-uses
// the GPU when present); inference.bicep just needs gpuWorkloadProfileName=gpu.

targetScope = 'resourceGroup'

param location string

@allowed(['dev', 'prod'])
param env string

@description('Log Analytics workspace customerId (the `customerId` output / property of the platform workspace).')
param logAnalyticsCustomerId string

@secure()
@description('Log Analytics workspace primary shared key.')
param logAnalyticsSharedKey string

@description('Serverless GPU workload profile type with quota in this region (e.g. Consumption-GPU-NC8as-T4 or Consumption-GPU-NC24-A100). Must match what your quota request was approved for.')
param gpuWorkloadProfileType string = 'Consumption-GPU-NC8as-T4'

var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'gpu-aca-env' }

resource gpuEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'lunaris-${env}-gpu-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    // A workload-profiles env always carries the base Consumption profile (scale-to-zero CPU); the
    // GPU profile is added alongside it. The chat inference runs on `gpu`; the API + embeddings stay
    // on `Consumption` (same env → internal ingress between them keeps working).
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
      {
        name: 'gpu'
        workloadProfileType: gpuWorkloadProfileType
      }
    ]
  }
}

@description('Pass as managedEnvironmentId to inference.bicep / embeddings.bicep / app.bicep.')
output managedEnvironmentId string = gpuEnv.id

@description('Pass as gpuWorkloadProfileName to inference.bicep (the chat app runs on this profile).')
output gpuWorkloadProfileName string = 'gpu'
