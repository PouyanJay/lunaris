# Phase 3 simulator evaluation — 2026-09-12

Three selected model-generated instruments pass fixed independent numeric checks and manual
source/screenshot teaching review. This demonstrates useful examples, not reliable first-attempt
success for arbitrary topics. Production release and Pouyan's learner acceptance remain open in
[#237](https://github.com/PouyanJay/lunaris/issues/237) and
[#216](https://github.com/PouyanJay/lunaris/issues/216).

## Selected positive artifacts

| Domain | Independent relationship and fixed states | Build time | Known build cost | Candidates |
| --- | --- | ---: | ---: | ---: |
| Algorithms | Worst-case bubble-sort comparisons n(n−1)/2: n=2→1, 5→10, 10→45 | 43.767 s | $0.137395 | 1 |
| Physics | Ideal resistor I=V/R: (0 V,1 Ω)→0.00 A, (6,3)→2.00, (12,2)→6.00 | 48.119 s | $0.162875 | 1 |
| Economics | Profit=(price−10)×quantity−100: (10,0)→−100, (20,10)→0, (30,20)→300 | 52.975 s | $0.169355 | 1 |

`approved-{domain}.json` contains the actual generated source, independent planner specification,
provider usage, candidate history, and verification evidence. The adjacent state PNGs come from
replaying the fixed oracle, not from hand editing screenshots. The selected artifacts use
`claude-opus-4-8`, factory prompt/cache version `sim-factory-v11`, wire contract version 1, and
verifier `chromium-contract-v2`. Physics includes the factory-assembled `series-resistor-v1`
component; generated controls, explanation and graph remain part of its complete HTML.

The fixed inputs live in `packages/live/tests/fixtures/sim_domains.json`; independent oracle source
version is `2026-09-12-v1`. Manual review checked equations, endpoints, plot transforms, labels,
circuit connectivity/polarity, and short pass-count explanations. The unsuitable input asks whether
a poetic speaker is sincere; it must decline numeric simulation rather than invent a score.

## Development reliability, failures and cost

`development-runs.json` records **45 development builds** across changing prompts and two models
(early Sonnet 4.6, later Opus 4.8), including unsuccessful runs. These are iterative engineering
trials, not a held-out success-rate estimate:

- 21 engine approvals, 13 rejections, 11 unsuitable decisions; 42 generation candidates attempted.
- Of 35 numeric-domain requests, 21 were engine-approved (60%); 12 rejected and 2 incorrectly
  declined after an ambiguous circuit-only prompt. The latter prompt was corrected.
- The non-simulatable input was correctly declined in 9 of 10 trials; the other provider call
  failed safely without a candidate.
- **At least 7 engine approvals failed subsequent manual acceptance**, including open/bypassed
  circuitry, contradictory arrows, diagram clipping/overlap, and an incorrect ellipsis at a small
  algorithm boundary. Engine approval is explicitly not counted as manual teaching acceptance.
- Median build latency: 50.704 s. Known factory-call cost: **$5.010772**. Three factory calls have
  unknown cost after provider failure/timeout; they are not counted as free. Standalone critic and
  tutor calls are separately recorded in `supplemental-evaluations.json`; it contains completed
  responses only, and additional connection failures without responses have unknown cost.

Rejection reasons include malformed planner JSON/schema, currency/readout mismatches, missing DOM
IDs, invalid JavaScript, wrong tick labels/arrows, source bypasses, exhausted reservation, and failed
provider calls. The report retains per-call usage, model, reservation, outcome, candidate hashes,
verifier reasons, and visual verdicts. Negative source/screenshot examples are retained as
`rejected-open-circuit.json` and `rejected-current-directions.json`; their old engine approval is
part of the regression evidence, not current permission to publish them.

## What now prevents the observed circuit failures

Visual model judgments remain stochastic: repeated standalone reviews sometimes accepted known
wrong circuits. We did not treat a later favorable review as proof that this was fixed. Current
voltage/resistance contracts require the assembled circuit at the verifier boundary. The browser
checks its actual shadow subtree against a trusted template, independently checks circuit topology,
and checks state-dependent labels and direction. Hiding or moving a component, adding a tagged or
untagged bypass, removing a wire, hiding the instrument, or omitting the renderer is rejected.
A failed structural report cannot construct a `VerifiedBundle`, even with a positive visual verdict.

The standalone negative evaluation records model judgments separately and asserts this full
publication rejection. It does not assert that the critic is now infallible. Other generated visual
domains still rely on bounded independent behavioral and source/screenshot review; occasional
rejection, and residual semantic-review error, remain limitations requiring monitoring.

The factory allows two candidates, 180 seconds total, 60 seconds per provider call, and an 80,000
conservative token reservation including rendering source review. Successful malformed generation
can consume the remaining repair attempt; failed or indeterminate calls are never automatically
retried. The worker's existing claim and text fallback prevent automatic rebilling loops.

## Tutor reactions, reuse and safety

`coach-{domain}.json` records actual Opus reactions to the selected assets, returned commands,
latency and cost. All three command states were replayed through the isolated browser against the
same independent equations. Manual text review found the comparisons correct. These interactions
are ungraded and grant no mastery. The coach fixture uses a private owner-scoped asset store;
it is not a claim of a real production learner session.

The authenticated browser integration separately demonstrates one actual generated linear asset
mounted by two fresh learners, history reload, private authenticated asset fetch, and revocation
with static fallback. It uses a preloaded registry and performs zero factory calls, so reuse cannot
regenerate an asset. This reuse test is generic integration coverage; it does not claim all three
domain artifacts were exercised by real learners. Each selected domain does have its own offline
browser replay against fixed oracles.

The browser safety suite also rejects wrong mechanisms, hidden outputs, invalid events, missing
command redraw, network/storage access and other existing sandbox mutations. The new supervisor
proves valid behavior and network rejection through its actual Docker boundary before readiness.

## Reproduce

```sh
docker build -f infra/sim-verifier/Dockerfile -t lunaris-sim-verifier:test .
uv run pytest tests/browser -m browser -q
uv run pytest -q
# Paid, requires ANTHROPIC_API_KEY; generated results are allowed to fail evaluation.
uv run pytest packages/live/tests/test_sim_domains_eval_live.py -m eval -q
uv run pytest packages/live/tests/test_sim_coach_eval_live.py packages/live/tests/test_sim_visual_regression_eval_live.py -m eval -q
```

The paid tests write sanitized results before assertions. A new paid run may reject; offline replay
of the committed positive artifacts provides deterministic regression coverage. Full CI, gated
production rollout, production fallback verification, and actual learner acceptance are distinct
gates. See [operations](../../live-simulator-operations.md).
