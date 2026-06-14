// The video-worker Container App (explainer-video V7) — a scale-to-zero, dedicated render worker that
// drains the `video_jobs` queue and renders Manim videos. Built from Dockerfile.worker and pushed to
// ACR by CD, like the API and the keyless inference apps. It runs the SAME VideoWorker loop the API
// runs in-process; shipping it as its own app keeps CPU-bound renders off the latency-sensitive API
// replica (plan §1.1).
//
// Scaling (plan §8.4): a KEDA PostgreSQL scaler on the count of QUEUED rows in `video_jobs` — 0 when
// the queue is empty, up to maxReplicas (3) when jobs pile up. One worker per replica
// (LUNARIS_VIDEO_WORKER_COUNT=1), so a replica == a concurrent render and maxReplicas is the true
// concurrency + spend ceiling. Because the API only enqueues when VIDEO_GENERATION_ENABLED is on,
// prod stays at zero replicas (dark) until that flag flips (V7-T5) — the worker itself never reads it.
//
// No ingress: the worker has no HTTP port. It reaches Supabase over the public API (REST) for the
// queue/storage and decrypts each job owner's BYOK keys from the vault (LUNARIS_KEY_ENC_MASTER) — it
// carries NO provider keys of its own, so every render bills the tenant, never the platform (V7-T1).

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference for the worker, e.g. <acr>.azurecr.io/lunaris-video-worker:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string
param keyVaultUri string

@description('Supabase project API URL (not secret) — the worker uses the REST API for queue + storage.')
param supabaseUrl string

@description('libpq connection string to the Supabase Postgres for the KEDA pending-job scaler ONLY (a read-only count query). Empty disables autoscale (the app idles at minReplicas — useful for a first bring-up). Prefer a dedicated least-privilege role (SELECT on public.video_jobs), NOT the postgres superuser; see the V7 follow-up note.')
@secure()
param videoJobsDbConnection string = ''

@description('Inject the BYOK AES master key from Key Vault as LUNARIS_KEY_ENC_MASTER. Required for real rendering — the worker decrypts each job owner\'s provider keys from the vault — so any video-enabled environment MUST set WITH_BYOK=true (the secret must already exist in the vault). Defaults false to match app.bicep, keeping the CD WITH_BYOK var the single source of truth.')
param withByok bool = false

@description('Max concurrent render replicas (plan §8.4 ceiling) — bounds wall-time and parallel spend.')
param maxReplicas int = 3

@description('Lease window (seconds): a job whose worker stops heartbeating for this long is treated as dead and requeued by the worker sweep (V7-T4). Passed to the worker via LUNARIS_VIDEO_LEASE_SECONDS. (The KEDA scaler counts all non-terminal jobs, so it needs no lease.)')
param leaseSeconds int = 300

@description('vCPU/memory per replica. Manim rendering is CPU-bound; the default (2 vCPU / 4Gi) is the Consumption-Only ceiling and matches the render sandbox\'s 3 GiB memory cap.')
param cpu string = '2.0'
param memory string = '4Gi'

var containerAppName = 'lunaris-${env}-video-worker'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'video-worker' }

// Key Vault secret names → env vars (each must already exist in the vault or the deploy fails). The
// worker needs the Supabase service-role key (REST) and the BYOK master key (to decrypt tenant keys);
// it deliberately gets NO LLM/search provider keys — tenant-only BYOK resolves them per job (V7-T1).
var supabaseServiceRoleSecret = 'supabase-service-role-key'
var byokSecretName = 'lunaris-key-enc-master'

// Always-present: the Supabase service-role key (queue + storage over REST).
var baseSecrets = [
  {
    name: supabaseServiceRoleSecret
    keyVaultUrl: '${keyVaultUri}secrets/${supabaseServiceRoleSecret}'
    identity: managedIdentityResourceId
  }
]

// The BYOK master key — required for real rendering (decrypts each job owner's keys); gated so a
// no-BYOK deploy doesn't reference a missing vault secret. Mirrors app.bicep's byok wiring.
var byokSecrets = withByok
  ? [
      {
        name: byokSecretName
        keyVaultUrl: '${keyVaultUri}secrets/${byokSecretName}'
        identity: managedIdentityResourceId
      }
    ]
  : []

// The KEDA scaler's DB connection string rides as a plain container-app secret (passed in by CD as a
// @secure() param, not from the vault) — only added when supplied, so a first bring-up still deploys.
var hasScaler = !empty(videoJobsDbConnection)
var scalerSecret = hasScaler ? [{ name: 'video-jobs-db-connection', value: videoJobsDbConnection }] : []

var byokEnv = withByok ? [{ name: 'LUNARIS_KEY_ENC_MASTER', secretRef: byokSecretName }] : []

// One worker per replica (LUNARIS_VIDEO_WORKER_COUNT=1): a replica == one concurrent render, so the
// KEDA replica count IS the concurrency and maxReplicas is the clean ceiling (each process also keeps
// its own Claude rate-limit bucket, so bounding replicas bounds the parallel call rate too).
var baseEnv = concat(
  [
    { name: 'SUPABASE_URL', value: supabaseUrl }
    { name: 'SUPABASE_SERVICE_ROLE_KEY', secretRef: supabaseServiceRoleSecret }
    { name: 'LUNARIS_ENV', value: env }
    { name: 'LUNARIS_VIDEO_WORKER_COUNT', value: '1' }
    // Same lease the KEDA query uses below — the worker's sweep + KEDA's wake threshold stay in lockstep.
    { name: 'LUNARIS_VIDEO_LEASE_SECONDS', value: string(leaseSeconds) }
  ],
  byokEnv
)

// KEDA PostgreSQL scaler: scale on every job that still needs a worker — i.e. all NON-TERMINAL rows
// (queued + in-flight planning…assembling). Counting in-flight rows (not just queued) is essential:
// it keeps a replica alive for the whole render (a fresh claim drops the queued count to 0, so a
// queued-only metric would scale the busy worker down mid-render) AND it lets a job a dead worker
// left in-flight keep/wake a replica, whose lease sweep (V7-T4) then requeues and re-claims it. The
// count falls to 0 only when everything is ready/failed → scale to zero. targetQueryValue 1 → one
// replica per outstanding job (up to maxReplicas); activationTargetQueryValue 0 → wake from zero as
// soon as one appears. Read-only + cheap.
var scaleRules = hasScaler
  ? [
      {
        name: 'pending-video-jobs'
        custom: {
          type: 'postgresql'
          metadata: {
            query: 'SELECT count(*)::int FROM public.video_jobs WHERE status NOT IN (\'ready\', \'failed\')'
            targetQueryValue: '1'
            activationTargetQueryValue: '0'
          }
          auth: [
            { secretRef: 'video-jobs-db-connection', triggerParameter: 'connection' }
          ]
        }
      }
    ]
  : []

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
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
      // No ingress block — the worker has no HTTP port; it is driven entirely by the queue.
      registries: [
        { server: acrLoginServer, identity: managedIdentityResourceId }
      ]
      secrets: concat(baseSecrets, byokSecrets, scalerSecret)
    }
    template: {
      containers: [
        {
          name: 'video-worker'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: baseEnv
        }
      ]
      scale: {
        // Scale to zero when the queue is empty (pay only while rendering). With no scaler secret
        // wired yet, minReplicas 0 + no rules means the app simply idles at zero.
        minReplicas: 0
        maxReplicas: maxReplicas
        rules: scaleRules
      }
    }
  }
}

output name string = worker.name
