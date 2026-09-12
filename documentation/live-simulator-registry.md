# Approved simulator registry

`SupabaseSimAssetStore` persists immutable approved bundles and their model/verification provenance.
`PreloadedSimRegistry` consumes an owner-scoped snapshot; `app_for` does no I/O and never starts a
build. Each returned reference has an independent contract copy. Learner gestures and tutor state
remain in each session's interaction history, outside the shared asset.

Cache identity hashes the definition, name, aliases, authored teaching context and criteria,
selected objective, and factory/verifier/contract versions. Transient node/map IDs are excluded.
Ownership is a separate database scope, so matching private teaching text never publishes it to
another owner. Public reuse requires an explicit trusted `public_source` with no private owner;
normal user-graph builds must not supply that field. An owner's compatible asset takes precedence
over the public catalog. Model identity is recorded in provenance; changing the version policy is
an explicit invalidation decision rather than silently replacing previously approved code.

The database claims one build per scope/key before paid work. Independent connections converge on
one token. Publication locks that row, checks token/scope/lease, validates behavioral and visual
content hashes, and commits the immutable asset and completed build atomically. Missing or wrong
tokens cannot publish. A claim expires after 300 seconds, beyond the factory's maximum 240-second
budget. Expired potentially paid work becomes `indeterminate`; requests cannot automatically claim
it again and re-bill. Rejected/indeterminate work retains its result for operator review. A deliberate
new version permits a fresh attempt; it does not overwrite the old asset or its evidence.

Both tables have RLS. Authenticated clients can read only their own or explicitly public,
unrevoked assets; they cannot write assets, read build receipts, or execute build RPCs. The server's
service-role adapter independently applies owner/public filters on every read. Payload and scope
changes are forbidden after publication. Revocation is permanent and checked on each serving request.

`GET /api/live/sims/assets/{uuid}` requires the deployment's normal bearer authentication and serves
only a currently visible approved asset. It emits the simulator CSP, `nosniff`, `no-referrer`, and
`private, no-store`. The host must fetch this route with its bearer token before mounting generated
HTML; direct iframe navigation cannot add that header. Authenticated browser mounting, session
preloading and the dedicated build supervisor are the following integration slice. The existing
reference/stub URLs retain their separate fixture behavior.

Validation includes real Postgres claim races, publication fencing, expired-work behavior, immutable
payloads, RLS grants and scope, plus a real Supabase REST publish/reload/revoke roundtrip. CI starts
the local REST gateway for that test and masks its ephemeral service key. Offline tests cover semantic
reuse, independent contract copies, objective/definition/version mismatch, revocation, mutation
rejection and serving headers. Two actual learner histories and authenticated browser mounting are
verified in the integration slice, not inferred from contract-copy tests.
