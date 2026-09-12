# Live simulator integration

`LUNARIS_LIVE_SIMS=factory` enables approved lookup and background requests when Supabase is
configured. The default remains off; `stub` remains the explicit offline reference. The existing
text lesson is available while an instrument is queued, building, unsuitable or unavailable.
Approved instruments are selected on the concept's next turn. The status endpoint is read-only.

The session loads a per-request registry snapshot before teaching. After committing the turn,
it requests the current missing instrument; the material prefetcher requests the next predicted
node. No generation occurs in `app_for` or in the paid session turn. Concepts with an available
prose criterion retain the existing prose-first assessment policy.

## Durable background work

The queue admits at most two distinct instruments per session and ten per learner over 24 hours.
The daily count includes durable build admissions, so deleting transcript history cannot reset
paid quotas. Requests are private, derived from the owned graph, and readable only by the service.
A trusted supervisor claims each request once through `claim_live_sim`, calls the bounded factory,
and publishes through the existing fenced verification boundary.

Unclaimed requests older than ten minutes or tied to a closed session can be adopted by a new
session. Requests that admitted potentially paid work are never automatically restarted. A lost
worker becomes indeterminate when its build claim expires. The worker checks session expiry,
closure/deletion and its cost rollup before generation, and checks the session again before
publication. Per-job work is limited to 240 seconds; cost draining has a five-second deadline.
Factory defaults remain two candidates and 180 seconds. The worker records costs against the
requesting session using that learner's credentials.

The entry point is `python -m lunaris_api.live.sim_worker_entrypoint`. It requires a digest-pinned
`LUNARIS_SIM_VERIFIER_IMAGE` and `LUNARIS_SIM_SECCOMP_PATH`. It is a **separate trusted supervisor**,
never an API process or generated sandbox. Deployment of that supervisor, production flag enablement,
and release acceptance belong to #237. The API must never receive Docker daemon access.

## Runtime teaching and containment

The host fetches approved HTML with its bearer token. Generated code receives no credentials.
A trusted, sandboxed wrapper embeds escaped generated HTML in another sandboxed `srcdoc` frame.
The wrapper's `frame-src 'none'` blocks the generated frame's own external navigation; the child
also inherits restrictions on fetches, forms, workers, images and scripts. A child-only CSP was
insufficient: a real Chromium regression attempted an external navigation despite `connect-src
'none'`. The enclosing policy prevented the request while preserving ordinary interaction.
This follows the containing document's frame-source restrictions in the
[Content Security Policy specification](https://www.w3.org/TR/CSP/#directive-frame-src).

The fixed wrapper relays messages only between the expected parent and instrument windows. The
host validates instance, sequence, app identity and complete numeric state. Revocation is checked
on every HTML load and every model-backed interaction. Tutor reactions use the approved teaching
specification and its independent cases, with a 25-second/700-token limit and validated commands.
Gestures do not update mastery; the existing separately graded answer remains the evidence path.

The protocol remains the explicit custom iframe bridge documented in `live-simulator-contract.md`,
not MCP Apps standards compliance.
