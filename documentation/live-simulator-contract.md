# Live simulator bridge, version 1

Live uses a custom `postMessage` iframe bridge. It does not implement MCP Apps.
The reference instrument is a deterministic development fixture; generated bundles
require the factory's verification and approval path before production use.

A contract declares its teaching objective and 1–8 named numeric parameters, each
with a label, finite minimum/maximum, positive step, and default. Defaults and
maximum values must align to the step grid. Every state snapshot contains exactly
these parameters, with finite, bounded, grid-aligned numbers. Booleans are invalid.

The iframe runs with `sandbox="allow-scripts"` and no referrer. The host accepts
messages only from that iframe's window. Because its sandbox gives it an opaque
origin, replies use `*`; window identity and the current turn's instance identity
are checked instead of trusting an origin string. No credentials enter the iframe.

1. The iframe emits `{type: "lunaris.sim.ready", version: 1}`.
2. The host sends `lunaris.sim.init` with version, appId, instanceId, state, active.
   State is the last persisted tutor command or the contract's defaults.
3. The iframe sends `lunaris.sim.event` with version, appId, instanceId, kind, state.
   Kinds are `param_changed`, `milestone_reached`, and `misconception_signal`.
4. The host attaches its session/turn identity and sequence, and submits through
   authenticated `POST /api/live/sessions/{sessionId}/sim`. The iframe cannot
   choose the endpoint, owner, turn, or sequence.
5. The API returns a persisted exchange: event, reaction `{text, state}`, and runId.
   The host displays the text and sends `lunaris.sim.command` containing version,
   instanceId, state, active. The iframe applies the state without echoing a gesture.
   `lunaris.sim.availability` updates active without resetting unsent controls.

There are at most 20 exchanges per turn. Only one request is pending in the host.
Failed requests retain their exact event for the explicit retry action. An exact
duplicate API request returns its saved exchange; reuse of a sequence with changed
data, out-of-order events, stale instances, and inactive turns return 409. Invalid
state/version returns 422; another owner's session is not disclosed (404).

Simulator gestures are untrusted learner input. They never grant mastery, grade
an answer, or advance a turn. The ordinary explanation/answer path remains the
source of graded evidence. Request, session, and run identifiers correlate the
persisted exchange with structured interaction logs.

The API accepts only version 1. An unsupported frontend contract shows an
explanation fallback without mounting the frame. Missing registry matches retain
the existing text/surface fallback. Legacy cards without a contract retain the
read-only simulator host. A failed load leaves the ordinary answer form available.
Production rollout remains gated on durable session coordination and acceptance.
