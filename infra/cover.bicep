// The cover-worker Container App (course-cover-images) — a scale-to-zero, dedicated worker that
// drains the `cover_jobs` queue and generates course cover images (Claude art-director → GPT Image 2
// → Claude vision-QA). Built from Dockerfile.cover and pushed to ACR by CD, like the API, the video
// worker and the keyless inference apps. It runs the SAME CoverWorker loop the API runs in-process;
// shipping it as its own app keeps cover generation off the latency-sensitive API replica.
//
// Scaling: a KEDA PostgreSQL scaler on the count of NON-TERMINAL rows in `cover_jobs` — 0 when the
// queue is empty, up to maxReplicas when jobs pile up. One worker per replica
// (LUNARIS_COVER_WORKER_COUNT=1), so a replica == a concurrent generation and maxReplicas is the true
// concurrency + spend ceiling. Because the API only enqueues when COVER_GENERATION_ENABLED is on,
// prod stays at zero replicas (dark) until that flag flips — the worker itself never reads it.
//
// No ingress: the worker has no HTTP port. It reaches Supabase over the public API (REST) for the
// queue/storage and decrypts each job owner's BYOK keys from the vault (LUNARIS_KEY_ENC_MASTER) — it
// carries NO provider keys of its own, so every generation bills the tenant, never the platform.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@allowed(['dev', 'prod'])
param env string

@description('Full image reference for the worker, e.g. <acr>.azurecr.io/lunaris-cover-worker:<sha>.')
param image string

param managedEnvironmentId string
param managedIdentityResourceId string
param acrLoginServer string
param keyVaultUri string

@description('Supabase project API URL (not secret) — the worker uses the REST API for queue + storage.')
param supabaseUrl string

@description('libpq connection string to the Supabase Postgres for the KEDA pending-job scaler ONLY (a read-only count query). Empty disables autoscale (the app idles at minReplicas — useful for a first bring-up). Prefer a dedicated least-privilege role (SELECT on public.cover_jobs), NOT the postgres superuser.')
@secure()
param coverJobsDbConnection string = ''

@description('Inject the BYOK AES master key from Key Vault as LUNARIS_KEY_ENC_MASTER. Required for real generation — the worker decrypts each job owner\'s OpenAI + Anthropic keys from the vault — so any cover-enabled environment MUST set WITH_BYOK=true (the secret must already exist in the vault). Defaults false to match app.bicep, keeping the CD WITH_BYOK var the single source of truth.')
param withByok bool = false

@description('Max concurrent generation replicas — bounds wall-time and parallel spend.')
param maxReplicas int = 3

@description('Lease window (seconds): a job whose worker stops heartbeating for this long is treated as dead and requeued by the worker sweep. Passed to the worker via LUNARIS_COVER_LEASE_SECONDS. (The KEDA scaler counts all non-terminal jobs, so it needs no lease.)')
param leaseSeconds int = 300

@description('vCPU/memory per replica. Cover generation is I/O-bound (provider API calls, no local render toolchain), so a modest 1 vCPU / 2Gi is ample — much leaner than the Manim video worker.')
param cpu string = '1.0'
param memory string = '2Gi'

var containerAppName = 'lunaris-${env}-cover-worker'
var tags = { app: 'lunaris', env: env, managedBy: 'bicep', role: 'cover-worker' }

// Key Vault secret names → env vars (each must already exist in the vault or the deploy fails). The
// worker needs the Supabase service-role key (REST) and the BYOK master key (to decrypt tenant keys);
// it deliberately gets NO LLM/image provider keys — tenant-only BYOK resolves them per job.
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

// The BYOK master key — required for real generation (decrypts each job owner's keys); gated so a
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
var hasScaler = !empty(coverJobsDbConnection)
var scalerSecret = hasScaler ? [{ name: 'cover-jobs-db-connection', value: coverJobsDbConnection }] : []

var byokEnv = withByok ? [{ name: 'LUNARIS_KEY_ENC_MASTER', secretRef: byokSecretName }] : []

// One worker per replica (LUNARIS_COVER_WORKER_COUNT=1): a replica == one concurrent generation, so
// the KEDA replica count IS the concurrency and maxReplicas is the clean ceiling (each process also
// keeps its own Claude rate-limit bucket, so bounding replicas bounds the parallel call rate too).
var baseEnv = concat(
  [
    { name: 'SUPABASE_URL', value: supabaseUrl }
    { name: 'SUPABASE_SERVICE_ROLE_KEY', secretRef: supabaseServiceRoleSecret }
    { name: 'LUNARIS_ENV', value: env }
    { name: 'LUNARIS_COVER_WORKER_COUNT', value: '1' }
    // Same lease the KEDA query uses below — the worker's sweep + KEDA's wake threshold stay in lockstep.
    { name: 'LUNARIS_COVER_LEASE_SECONDS', value: string(leaseSeconds) }
  ],
  byokEnv
)

// KEDA PostgreSQL scaler: scale on every job that still needs a worker — i.e. all NON-TERMINAL rows
// (queued + in-flight art_directing…uploading). Counting in-flight rows (not just queued) is
// essential: it keeps a replica alive for the whole generation (a fresh claim drops the queued count
// to 0, so a queued-only metric would scale the busy worker down mid-generation) AND it lets a job a
// dead worker left in-flight keep/wake a replica, whose lease sweep then requeues and re-claims it.
// The count falls to 0 only when everything is terminal → scale to zero. The three terminal statuses
// are 'ready', 'failed' and 'cancelled' — ALL must be excluded here, or a terminal-but-unexcluded
// status pins the worker at max scale forever (the exact bug that pinned the video worker). targetQueryValue
// 1 → one replica per outstanding job (up to maxReplicas); activationTargetQueryValue 0 → wake from
// zero as soon as one appears. Read-only + cheap.
var scaleRules = hasScaler
  ? [
      {
        name: 'pending-cover-jobs'
        custom: {
          type: 'postgresql'
          metadata: {
            query: 'SELECT count(*)::int FROM public.cover_jobs WHERE status NOT IN (\'ready\', \'failed\', \'cancelled\')'
            targetQueryValue: '1'
            activationTargetQueryValue: '0'
          }
          auth: [
            { secretRef: 'cover-jobs-db-connection', triggerParameter: 'connection' }
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
          name: 'cover-worker'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: baseEnv
        }
      ]
      scale: {
        // Scale to zero when the queue is empty (pay only while generating). With no scaler secret
        // wired yet, minReplicas 0 + no rules means the app simply idles at zero.
        minReplicas: 0
        maxReplicas: maxReplicas
        rules: scaleRules
      }
    }
  }
}

output name string = worker.name
