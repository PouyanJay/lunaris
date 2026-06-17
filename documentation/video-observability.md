# Video observability

When an explainer-video job fails or ships imperfect scenes, you should be able to tell *why* from a
single structured query — not by reading raw render logs. The video worker and pipeline emit a small
set of structured `structlog` events for exactly this. They stream to **Log Analytics** in cloud
(see [Deployment](deployment.md)) and to stdout JSON locally; every line carries `run_id = job_id`,
so one video job triangulates across queue → worker → pipeline → storage.

## The events

| Event | Where | Carries | Read it for |
|---|---|---|---|
| `video_worker.job_failed` | worker, on any failure | `failure_kind`, `failure_class`, `scene_id` | *Why did this job fail?* |
| `video_pipeline.produced` | pipeline, on a finished render | `scenes`, `narrated`, `degraded_scenes`, `degraded_by_kind` | *How degraded was the output?* |
| `codegen.sanitized` | scene validator, when a deterministic fix fires | `scene_id`, `fix`, `codepoints` | *How often is a completion recovered for free vs by an LLM repair turn?* |

### Failure taxonomy (`failure_kind`)

Coarse on purpose — `failure_class` always carries the exact exception type, so a kind is never
ambiguous. Sync and length imperfections are **not** here: they degrade best-effort (the video still
ships voiced), they never fail a job.

| `failure_kind` | Meaning | Typical `failure_class` |
|---|---|---|
| `factual` | Gate C major: a scene smuggles a figure/comparison no cited claim supports (caught pre-render) | `FactualGateError` |
| `render` | Gate A: a scene exhausted its render-repair budget and still won't render | `SceneRenderError` |
| `codegen_parse` | Generated source never parsed after the bounded parse-repair turns (dominant: "unterminated string literal") | `ValueError` (or a `ValidationError` for a structured-output parse) |
| `pipeline` | Any other pipeline failure | `VideoPipelineError` |
| `infrastructure` | Non-pipeline: queue/storage down, or an unexpected error | anything else |

### Degraded-issue histogram (`degraded_by_kind`)

Counts degraded **issues** (not scenes) for a produced video, by gate source:

- `visual` — Gate B spatial defects that survived repair.
- `sync` — Gate D / Gate 1 narration-vs-visual or timing drift shipped best-effort (voiced only).
- `factual` — Gate C *minor* flags: a grounded scene narrating an extra unsupported figure.

A scene with two spatial defects contributes 2 to `visual`; a clean produce is all zeros.

### Deterministic sanitization (`codegen.sanitized`)

Fires once per deterministic, meaning-preserving fix the validator applies before `compile()`:
`fix="line_endings"` (CRLF/CR → LF) or `fix="smart_punctuation"` (a curly quote/dash → ASCII, with
the offending `codepoints`). Unterminated strings and `2x`-style malformed decimals are **not** fixed
deterministically — those need the bounded LLM parse-repair turn, so they never appear here. The ratio
of `codegen.sanitized` to `llm_parse_repair` events is the determinism-vs-repair signal.

## Querying it (Log Analytics / KQL)

Worker and pipeline logs land in `ContainerAppConsoleLogs_CL`, app `lunaris-<env>-video-worker`. The
structured event is a JSON line in `Log_s`. The Azure CLI Log-Analytics extension is flaky to install;
query through `az rest` against the workspace instead.

**Failure taxonomy over the last day:**

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "lunaris-prod-video-worker"
| where Log_s contains "video_worker.job_failed"
| extend p = parse_json(Log_s)
| summarize count() by failure_kind = tostring(p.failure_kind), failure_class = tostring(p.failure_class)
| order by count_ desc
```

**Degradation profile of produced videos:**

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "lunaris-prod-video-worker"
| where Log_s contains "video_pipeline.produced"
| extend p = parse_json(Log_s)
| summarize
    videos = count(),
    degraded = countif(toint(p.degraded_scenes) > 0),
    visual = sum(toint(p.degraded_by_kind.visual)),
    sync = sum(toint(p.degraded_by_kind.sync)),
    factual = sum(toint(p.degraded_by_kind.factual))
```

**Determinism vs LLM repair (codegen):**

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "lunaris-prod-video-worker"
| where Log_s has_any ("codegen.sanitized", "llm_parse_repair")
| extend p = parse_json(Log_s)
| summarize count() by event = tostring(p.event), fix = tostring(p.fix)
```

Run any of these via `az rest --method post` against
`https://api.loganalytics.io/v1/workspaces/<workspace-id>/query` (resource
`https://api.loganalytics.io`). Use `contains`, not `has`, for substring matches on `Log_s` —
`has` tokenizes and misses ids. Locally, the same events are stdout JSON: `... | jq 'select(.event ==
"video_worker.job_failed")'`.

## The C4 quality eval (proactive, not forensic)

The events above tell you *why a video failed* after it happened. The **C4 quality eval** is the
proactive counterpart: it drives the real pipeline over a fixed topic set and reports the same
taxonomy as a single `QualityReport`, so a change to the planner or the QA gates (Workstream C —
C1/C2/C3) is judged against a number instead of waiting for prod to degrade.

It is a **key-gated** pytest eval (`pytestmark = pytest.mark.eval`,
`packages/video/tests/test_video_quality_eval_live.py`) that self-skips without `ANTHROPIC_API_KEY`
and the render extra — exactly like `test_video_pipeline_live`. The harness itself
(`packages/video/tests/_quality_eval.py`) is covered hermetically by `test_quality_eval` so the
aggregation stays green in CI without a model.

**Run it (keyed nightly — it renders several full lessons, minutes per topic):**

```bash
uv run --env-file .env pytest -m eval packages/video/tests/test_video_quality_eval_live.py -s
```

**What it reports.** Per topic and aggregate:

| Metric | Meaning |
|---|---|
| `produced` / `degraded` / `failed` | topics that shipped a video / shipped with ≥1 best-effort scene / the pipeline raised |
| `degraded_scene_rate` | degraded scenes / total scenes — the headline "how clean do scenes come out" number |
| `degraded_by_kind` | `{visual, sync, factual}` issue histogram — tells whether C2 (visual) or C3 (sync) owns the degradation. Read off the pipeline's `video_pipeline.produced` telemetry (above), the one source both this eval and Log Analytics share |
| `failures_by_kind` | the same `failure_kind` taxonomy as `video_worker.job_failed`, via the shared `VideoFailureKind.classify` (`lunaris_video.worker.failure_taxonomy`) |

**The regression ceiling.** `QualityReport.meets_ceiling(max_degraded_scene_rate=…, max_failures=…)`
is the gate the live eval asserts. It starts permissive — `max_degraded_scene_rate=0.75` (the prod
incident showed 50–75% of scenes degraded) and `max_failures=0` (the Phase-1 severity-tiered factual
gate means one uncited figure should degrade, not hard-fail a whole video). **Calibrate down on the
first real keyed run** and tighten as C1/C2/C3 land — a run that degrades *more* than the ceiling, or
hard-fails a video, fails the eval.

The topic set spans easy → hard and includes the cases that exposed the prod failures: binary search
(the uncited-figure `S2_mechanism` incident), the neural-net "web of nodes" archetype, and a
framing-only topic with no verified claims.
