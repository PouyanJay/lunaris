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
