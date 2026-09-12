# Live simulator operations

The API only queues requests and serves approved assets. The trusted supervisor is a dedicated
Ubuntu VM (`lunaris-prod-sim-worker`) with no inbound access. It runs one bounded build at a time;
generated code executes only inside disposable Docker containers with no network, credentials,
host mounts, or elevated capabilities. The supervisor alone has the Docker socket.

## Release

`CD (prod)` remains behind the existing GitHub `prod` environment reviewer gate. With
`LIVE_SIMS_ENABLED=true`, it builds/pushes the supervisor and verifier, deploys the VM, then installs
both images by their build-output SHA256 digests. Migrations run first. The supervisor retrieves
secrets using the existing platform managed identity and proves both correct simulator behavior
and rejection of network access through the actual deployed Chromium container. Only after that
readiness check succeeds does the workflow enable `LUNARIS_LIVE_SIMS=factory` on the API.

The VM uses the existing identity's ACR pull and Key Vault permissions; it receives no additional
role grants. Key Vault supplies the Supabase service key, Anthropic key, and optional BYOK master
key. Secrets stay in a root-only `/run` env file and the trusted process environment. No secrets
are embedded in cloud-init, image layers, shell arguments, or deployment output. The host bootstrap
uses Microsoft's [managed-identity token endpoint](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/how-to-use-vm-token)
and [ACR token exchange](https://github.com/Azure/acr/blob/main/docs/AAD-OAuth.md).

Required production variables, in addition to existing platform configuration:

- `LIVE_SIMS_ENABLED=true` to deploy and enable the factory.
- `SIM_WORKER_SSH_PUBLIC_KEY`: stable operator public key. Inbound SSH is denied; normal management
  uses Azure Run Command through the gated release. Changing this key is a separate host operation.

The fixed host is a billable VM even when idle. It is deliberately separate from the Container App
scalers and the existing Container App power switch. Stop the supervisor before deallocating this
VM through an authorized operator action. Keep the host patched; cloud-init installs distribution
Docker and Python, and Azure automatic guest patching is enabled.

## Boundaries and observability

Each build has at most two generation candidates, a 180-second factory deadline, a 60-second
provider-call ceiling, and a 80,000-token conservative reservation. The worker has a 240-second
job envelope. The reservation includes rendering-source bytes for independent visual review.
No provider retry occurs after a failed or indeterminate call. Malformed successful
responses may consume the remaining candidate attempt. Service shutdown allows 300 seconds to
finish admitted work. Paid claims are never automatically requeued.

`live.sim.built`, `live.sim.verified`, and `live.sim.coached` carry run/session correlation. Durable
build results retain rejected candidates and verifier reasons; model calls retain token usage,
known cost, reservations, and indeterminate outcomes. Queue status is read-only through the
owner-scoped session endpoint. Rejected builds preserve the text lesson; they do not grant mastery.

Read supervisor status through Azure Run Command using `systemctl is-active lunaris-sim.service`
and `docker inspect --format '{{.State.Running}}' lunaris-sim-supervisor`. The file
`/tmp/lunaris-sim-ready` inside the supervisor proves startup passed its actual sandbox checks.
Use `journalctl -u lunaris-sim.service` and bounded Docker logs for diagnosis; do not print
`docker inspect` wholesale, the environment file, tokens, or secret-manager responses.

## Fallback and rollback

Set `LIVE_SIMS_ENABLED=false` and run the normal gated production workflow. It drains/stops and disables the
supervisor (including across VM reboots) before deploying the API with the factory off. Text sessions continue. Already approved
history assets remain subject to authentication and revocation; stale or unavailable interactions
show the existing static fallback. To reject a particular artifact, revoke its immutable registry
record; do not overwrite the HTML or clear paid-work claims to force regeneration.

For a code rollback, release a known compatible commit that includes the registry/queue/session
transaction migrations; leave those additive migrations in place. Do not roll back to an old API
writer while relying on the graph transaction safety guarantee. After any API rollout, verify old
revisions have drained before closing issue #217.

## Acceptance status

Local/CI verification and Azure preflight are separate from production delivery. Issue #237 stays
open until the normal production release, fallback verification, and Pouyan's actual learner
acceptance are recorded. Issue #216 is that human acceptance gate; automated screenshots do not
substitute for it.
