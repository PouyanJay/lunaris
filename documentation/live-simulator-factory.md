# Bounded simulator factory

`SimFactory` runs outside the synchronous session registry lookup. A LangGraph first plans an
independent numeric teaching specification, then generates candidate HTML, runs the isolated
Chromium verifier, and asks a separate model call to judge two actual rendered screenshots.
Only a passing behavioral report and passing visual verdict for the exact candidate hash produce
a `VerifiedBundle`. A subjective or insufficiently grounded concept can return `unsuitable`.
Rejection and timeout return no publishable bundle, preserving the existing session fallback.

The planner sees the concept definition and criterion, but no candidate code. The generator sees
the independent specification and previous rejection evidence. The visual reviewer sees the
original definition, specification and screenshots, but no generated code. This separation helps
catch outputs that agree numerically while drawing the wrong mechanism. Model judgment is still
fallible; the wider domain evaluation and human learner acceptance remain separate release gates.

Default budgets allow two candidates, 180 seconds total, 60 seconds per model call, 6000 output
tokens and 60000 reserved tokens. Explicit overrides are bounded by the schema. Reservations use
a conservative UTF-8 text bound plus output and image allowances before each paid invocation.
The model adapter disables provider retries; interrupted potentially billed calls are marked
`indeterminate`. No timeout triggers an automatic re-bill. Calls record actual provider/model,
prompt version, measured tokens, cost when a cost scope exists, and outcome. Results retain
candidate bytes, source/specification hashes, reports, rejection reasons and elapsed time.

The isolated verifier captures complete instruments up to 1560px high at 1100px width, restoring
scroll before taking PNGs. Oversized instruments reject rather than causing unbounded image
input. Review receives the actual two PNGs as provider image content. Screenshot evidence and
full candidates belong in owner-scoped artifact storage; generic logs contain status and hashes,
not learner source text or model output.

## Verification

Build the appliance using `infra/sim-verifier/README.md`, then run:

```sh
uv run pytest packages/live/tests/test_sim_factory.py packages/live/tests/test_sim_model_metering.py -q
uv run pytest tests/browser -m browser -q
uv run --env-file .env pytest packages/live/tests/test_sim_factory_eval_live.py -m eval --basetemp /tmp/lunaris-sim-eval -q
```

The final command spends on a real provider and writes inspectable `result.json`, including failed
candidates, before asserting acceptance. It is excluded from offline CI. Missing credentials are
a skip, never evidence of success. Offline tests exercise repair, exhaustion, invalid contracts,
unsuitable concepts, model failures, concurrent metering, missing visual evidence and visual
rejection. Real Docker tests exercise generated-candidate repair and screenshot delivery, plus
known wrong, malicious, oversized and nonresponsive candidates.

Persistent publication, duplicate-build coordination, production execution and session integration
are delivered in the registry/integration tickets. The factory does not execute candidate code on
the API host or expose a Docker socket to application containers.
