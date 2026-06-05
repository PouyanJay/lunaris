# Lunaris

**Lunaris turns a topic into a real, verified course.** Type a subject; an agent plans the
curriculum, writes the lessons, grounds every factual claim against evidence, and hands you something
you can actually learn from — a prerequisite map, Merrill-structured lessons, branded diagrams, and
claims that carry their sources.

It is a **fully agentic application**: the product is built around a real deep-agent harness that
plans and executes the build by calling capabilities as tools, on top of a conventional web + API +
Supabase surface.

## Why it exists

Most "AI course generators" free-hand an answer in one shot — plausible, unordered, and unsourced.
Lunaris keeps two correctness guarantees in deterministic code, exposed to the agent **as tools** so
the model can't talk its way past them:

- **Failure A — prerequisite order.** A prerequisite-graph builder guarantees an acyclic topological
  ordering: a concept is never taught before its prerequisites.
- **Failure B — grounding.** A claim-level verifier checks every factual sentence against retrieved
  evidence; anything it can't support is cut before the course is published.

The agent reasons about *what to do next*; the moats and a deterministic finalize step guarantee
*what ships*.

## Relevant, not just correct

Ordering and grounding don't make a course about the *right thing at the right level*. Ask for
*"Improve my English to CLB 10"* (an advanced band) and a naive generator enumerates the whole subject
from *"the English alphabet"* — coherent, correctly ordered, and useless. So Lunaris runs the front of
the pipeline a good tutor runs first: **interpret** the request into a typed goal-for-a-learner brief →
**research** the real standard → **model the learner's frontier** (what to skip) → **scope to the gap**
→ design backward and **curate** vetted external resources per lesson. The moats then operate over
*relevant, scoped* input. A learner can optionally **confirm or adjust** the inferred level / prior
knowledge / depth / style before building (the default is one click).

Honest about what this needs: the **relevance fix itself needs only an Anthropic key** — the level-aware
scoping is prompt-driven. **Research grounding and curated resources are enhancements gated on
`SEARCH_API_KEY`** (and an optional `YOUTUBE_API_KEY` for richer video); without them the build still
produces a relevant, right-level course and says so (`research: unavailable`, no resources) rather than
faking either. Full detail + the cost/budget model: [documentation/relevance-model.md](documentation/relevance-model.md).

## Grounded, and auditable

Grounding is not a binary check. Every source the verifier draws on carries a **trust tier**
(official / reputable / open / blocked, plus **vouched** for sources you supply), a **source type**,
and a **credibility score** — constructed at acquisition and shown on the citation. On a HIGH-risk
course the verifier applies a **risk-tiered trust floor**: a claim's evidence must be curated-or-better
*and* credible, **or** corroborated across ≥2 independent domains — otherwise the claim is cut, not
shipped. So a lone open-web page that merely *agrees* with a claim can't rubber-stamp it; **authority
emerges from agreement, not from a label** (and the LLM judges are kept blind to source labels while
the user sees the full trust).

The corpus fills three ways, all into the same trust-graded store: **manual** (you upload / paste /
link sources on the Corpus tab), **auto** (a discovery agent searches, vets, and ingests evidence for
the topic — watched live), and **seed** (the build reuses the authoritative pages it already fetched
while researching — near-free). Grounding is **per-course only** (no shared library). Full trust
model, the three modes, and the honest cost story (search metering, Voyage embeddings, free OpenAlex):
[documentation/grounding-model.md](documentation/grounding-model.md).

## Architecture at a glance

- **Agent harness** (`packages/agent`, `lunaris_agent.harness`) — a `create_deep_agent` planner that
  runs the relevance front (interpret → research → model-learner → gap-scoped extraction →
  competency-mapped design → resource curation), calls the moat tools, and delegates Merrill lesson
  authoring to a LangGraph **author → verify → revise** subagent. Runs as `LUNARIS_PIPELINE=agent`
  (the default).
- **Shared discovery** (`packages/grounding`, `lunaris_grounding.discovery`) — one search provider
  (Tavily) + content extractor (Trafilatura) + domain-trust model, shared by research and resource
  curation; key-gated on `SEARCH_API_KEY`, with deterministic stubs otherwise.
- **MCP registry** (`lunaris_agent.mcp_registry`) — the moats exposed as FastMCP tools (`lunaris-mcp`).
- **Moats** — `packages/graph` (prerequisite graph) and `packages/grounding` (retrieval + verifier;
  Supabase **pgvector** + Voyage embeddings when configured, a conservative stub otherwise).
- **Runtime** (`packages/runtime`) — the course-object schema (Pydantic), persistence, structlog
  logging (with correlation IDs + sensitive-data redaction), and resilience helpers.
- **API** (`apps/api`, FastAPI) — `POST /api/courses`, an SSE build stream, and a live agent
  transcript; selects the pipeline via `LUNARIS_PIPELINE`.
- **Web** (`apps/web`, Vite + React + TS) — a studio with a run-history sidebar, a live agent
  transcript, and a lesson **Reader** (Merrill phases, objectives, assessment, claims-with-sources,
  branded visuals) plus a prerequisite-graph **Map** view.
- **Eval** (`packages/eval`, `lunaris-eval`) — independent, offline checkers for the definition of
  done (prerequisite order + factuality).

The model provider is **Anthropic Claude** (a strong + worker tier); embeddings are **Voyage AI**.

## Quick start

The one command, from a fresh clone:

```bash
make run
```

This installs everything (uv + Python workspace + web deps), brings up Supabase + the API + the web
dev server, then opens the studio. **Pipeline selection is automatic:** with a real
`ANTHROPIC_API_KEY` reachable (in `.env` or the in-app Settings panel) `make run` serves the **real
agent harness**; with no key it falls back to the deterministic **stub** pipeline (no key, instant,
always works) and tells you so. Force a mode with `LUNARIS_PIPELINE=agent|live|stub`.

Common targets:

```bash
make            # command reference
make start      # backend only (Supabase + API)
make stop       # tear everything down (Supabase data preserved)
make test       # Python + web test suites
make lint       # ruff + typecheck + eslint gates
```

Configuration lives in `.env` (copied from `.env.sample` on first run). Every external key is
**optional** — each unlocks a live feature, and its absence falls back to a deterministic stub, so the
no-key path always works:

| Key | Unlocks | Absent |
|---|---|---|
| `ANTHROPIC_API_KEY` | Live Claude (the `agent`/`live` pipelines, the relevance front, every `-m eval`) | The deterministic `stub` pipeline |
| `SEARCH_API_KEY` (Tavily) | Standard research + curated per-lesson resources (metered, per-build budget) | `research: unavailable`, no resources — the course still builds at the right level |
| `YOUTUBE_API_KEY` | Richer video resources (duration / channel) | Video candidates via the shared search |
| `EMBEDDINGS_API_KEY` (Voyage) + Supabase | Real pgvector grounding → claim-level citations | The verifier fails safe (cuts every claim → *Needs review*) |

See [documentation/relevance-model.md](documentation/relevance-model.md) for the relevance pipeline and
its cost/budget model, and [documentation/grounding-model.md](documentation/grounding-model.md) for the
grounding trust model, the three corpus modes, and their costs.

## Development

- Backend: `uv run pytest -q` (deterministic, no key) · `uv run ruff check . && uv run ruff format --check .`
- Web: `cd apps/web && npm run dev` (or `test` / `lint` / `typecheck` / `build`)
- Live evals (real key): `uv run --env-file .env pytest -m eval -q`
- Score a course against the definition of done: `uv run lunaris-eval <course.json>`

> Project-internal engineering standards, agents, and skills live under `.claude/` (gitignored) and
> are not shipped with the product.
</content>
