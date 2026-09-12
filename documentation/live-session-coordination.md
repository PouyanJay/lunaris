# Live session coordination

Live serializes mutations by **learner and graph**, including turns in different sessions on the
same graph. This protects the whole learner model, which the knowledge store persists as a graph
snapshot. Production uses Postgres leases; the shared in-memory backend supports offline tests.

## Admission and persistence

`acquire_live_graph` grants a fenced 120-second lease. The API renews it every 15 seconds with a
10-second RPC timeout. Renewal failure cancels the admitted task. A disconnected streaming reader
does not cancel an admitted turn: that task owns renewal through its final commit and release.
Cancellation during acquisition releases a late grant without starting model work.

The service rereads mutable state after admission. Start, answer, advance, simulator interaction,
end, discard, delete, expiry and knowledge reset use the same coordination boundary. Reset waits
at most two seconds for another reset, preserving idempotent concurrent clears. Other competing
mutations receive HTTP 409. Reads remain available while a turn is running.

`commit_live_graph` fences the claim and commits the transcript and knowledge together. Updates
also compare the expected turn count; they never upsert a missing session. Deletion cannot be
undone by a stale writer, and reset rechecks that no open session remains inside the transaction.

Before paid work, an opaque hash of the operation and its session snapshot is recorded. A commit
marks it completed. A failed, cancelled or expired attempt becomes indeterminate and cannot be
silently billed again. This deliberately favors avoiding duplicate charges over automatic recovery
of uncertain turns. No transcript or answer text is stored in these receipts. Both coordination
tables and all RPCs are service-only, with RLS and no authenticated/anonymous client grants.

## Release gate

On 2026-09-11 production ran API revision `lunaris-prod-api--0000099`, with minReplicas=1,
maxReplicas=3 and HTTP concurrency=6. The old process-local guard was therefore exposed to
cross-replica races. A deterministic test reproduced two grader admissions through independent
service instances, separate Supabase clients and separate throttles against real Postgres.

The new migration is additive and precedes the API deployment. **Do not claim protection during
an overlap with old API writers.** Complete the normal production release, confirm old revisions
have stopped and outstanding old work has drained, then verify session mutations through the new
revision before closing issue #217 or enabling Phase 3 production acceptance. Rolling back to an
older API restores the old coordination limitation; the additive tables can remain in place.

## Verification

Real database tests exercise competing same-session and same-graph turns, completed and uncertain
retry refusal, detached streaming, lifecycle exclusion, expiry, reset and deletion. SQL assertions
cover atomic rollback, replacement tokens, cross-owner/graph rejection, stale commits after reset
or deletion, and service-only access. API tests cover late acquisition cancellation and renewal loss.
