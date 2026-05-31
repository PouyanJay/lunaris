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

## Architecture at a glance

- **Agent harness** (`packages/agent`, `lunaris_agent.harness`) — a `create_deep_agent` planner that
  calls the moat tools and delegates Merrill lesson authoring to a LangGraph
  **author → verify → revise** subagent. Runs as `LUNARIS_PIPELINE=agent` (the default).
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

Configuration lives in `.env` (copied from `.env.sample` on first run). A real key unlocks live
Claude generation; adding Supabase + Voyage keys unlocks real pgvector grounding.

## Development

- Backend: `uv run pytest -q` (deterministic, no key) · `uv run ruff check . && uv run ruff format --check .`
- Web: `cd apps/web && npm run dev` (or `test` / `lint` / `typecheck` / `build`)
- Live evals (real key): `uv run --env-file .env pytest -m eval -q`
- Score a course against the definition of done: `uv run lunaris-eval <course.json>`

> Project-internal engineering standards, agents, and skills live under `.claude/` (gitignored) and
> are not shipped with the product.
</content>
