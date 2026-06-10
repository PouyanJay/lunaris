# Architecture

The system design of Lunaris in four diagrams. Lunaris is an **agent-first** application: a
conventional product surface (web + API + Supabase) wraps a deep-agent core that plans a course build
and calls every capability — including two deterministic correctness guarantees — as **tools**.

Four invariants hold across every layer, and the harness enforces them:

1. **Reasoning vs recall** — the agent reasons about plans; authoritative facts flow through
   capability tools, never the model's memory.
2. **Tools vs orchestration** — each capability is its own package; the MCP registry is a thin
   adapter, not a home for logic.
3. **Provenance is structural** — tool results carry where the data came from (source, trust,
   tool-call id, timestamp), constructed at the source and flowing untouched to the UI.
4. **Correlation everywhere** — every run carries a `run_id` propagated via `structlog` contextvars,
   so one build can be traced across every layer.

The two correctness guarantees referenced throughout these docs are:

- **Prerequisite ordering** — the prerequisite graph is acyclic and teaches in topological order; the
  model cannot reorder it. Built in [`packages/graph`](../packages/graph).
- **Claim grounding** — every factual claim is verified against retrieved evidence and either
  supported or cut; the model cannot talk an unsupported claim past it. Built in
  [`packages/grounding`](../packages/grounding).

---

## 1. Components

```mermaid
flowchart TB
    subgraph Surface["Product surface"]
        WEB["Web studio · React 19 + Vite<br/>Reader · Map · Build timeline · Corpus · Settings"]
        API["API · FastAPI<br/>SSE build stream · auth · per-tenant BYOK"]
    end

    subgraph Core["Agentic core · packages/agent"]
        HARNESS["Deep-agent harness<br/>create_deep_agent — plans + calls tools"]
        SUB["Authoring subagent<br/>author → verify → revise (LangGraph)"]
        MCP["MCP registry · FastMCP<br/>build_prerequisite_graph · verify_claims"]
    end

    subgraph Guarantees["Deterministic correctness guarantees"]
        GRAPH{{"PrerequisiteGraphBuilder<br/>packages/graph"}}
        VERIFY{{"Verifier + PgVectorRetriever<br/>packages/grounding"}}
    end

    subgraph Capabilities["Capability tools (key-gated, stubbed otherwise)"]
        DISC["Shared discovery<br/>Tavily search · Trafilatura · domain trust"]
        WORKERS["Claude workers<br/>interpret · research · model · extract · design · curate"]
    end

    subgraph DataLayer["Data"]
        PG[("Supabase · Postgres<br/>pgvector corpus · RLS")]
        STORE[("Course store<br/>Postgres / filesystem")]
    end

    WEB <-->|"authedFetch · SSE"| API
    API --> HARNESS
    HARNESS --> WORKERS
    HARNESS --> SUB
    HARNESS -->|tool call| GRAPH
    HARNESS -->|tool call| VERIFY
    SUB -->|grounds each claim| VERIFY
    HARNESS --> DISC
    DISC -->|ingest graded sources| PG
    VERIFY -->|retrieve evidence| PG
    HARNESS -->|persist Course| STORE
    HARNESS -.portable tools.-> MCP
    MCP --> GRAPH
    MCP --> VERIFY

    classDef guarantee fill:#3b2f10,stroke:#e8a33d,stroke-width:2px,color:#fff;
    class GRAPH,VERIFY guarantee
```

The harness exposes the same two guarantees **twice**: as in-process tools to its own planner, and
via the **MCP registry** so any MCP client can call them. The registry is a thin adapter — the logic
lives in `packages/graph` and `packages/grounding`.

## 2. Build sequence

The planner drives the build by calling tools in a sensible order; each tool emits a typed
`ProgressStage` event that streams to the web timeline over SSE. The two guarantees (◆) are
deterministic. The same flow is traced stage by stage, with example values, in
[build-pipeline.md](build-pipeline.md).

```mermaid
sequenceDiagram
    autonumber
    participant L as Learner / Web
    participant API as API (SSE)
    participant A as Agent harness
    participant W as Claude workers
    participant G as Prerequisite graph ◆
    participant S as Authoring subagent
    participant V as Verifier ◆
    participant DB as Supabase pgvector

    L->>API: POST /api/courses {topic}
    API->>A: start run (run_id)
    A-->>L: RUN_STARTED

    A->>W: interpret · research · model · extract
    W-->>A: CourseBrief · competencies · frontier · concepts
    A-->>L: BRIEF_INTERPRETED … CONCEPTS_EXTRACTED

    A->>G: build_prerequisite_graph(concepts)
    G-->>A: acyclic graph + topo order
    A-->>L: GRAPH_BUILT

    A->>W: design_curriculum
    A->>DB: seed + discover grounding (graded sources)
    A-->>L: CURRICULUM_DESIGNED · GROUNDING_SEEDED · GROUNDING_DISCOVERED

    loop per module
        A->>S: author module
        S->>V: verify each claim
        V->>DB: retrieve evidence
        V-->>S: supported / cut (trust floor)
        S-->>A: lesson (grounded)
        A-->>L: MODULE_AUTHORED · CLAIMS_VERIFIED
    end

    A->>W: curate_resources · coverage gate
    A-->>L: RESOURCES_CURATED · COVERAGE_VERIFIED
    A->>DB: persist Course
    A-->>L: RUN_COMPLETED
```

## 3. The authoring loop, up close

Lessons are authored by a LangGraph subagent that **grounds before it ships**: every factual claim is
checked against retrieved evidence, and unsupported claims trigger a bounded revise — not a rubber
stamp.

```mermaid
flowchart LR
    START(["module + objectives"]) --> AUTH["author lesson<br/>Claude strong"]
    AUTH --> VER{{"verify claims<br/>retrieve + assess + trust floor"}}
    VER -->|all supported| DONE(["grounded lesson"])
    VER -->|some cut| REV["revise<br/>repair / drop cut claims"]
    REV --> VER
    VER -.->|revise budget exhausted| TRIAGE(["ship supported only<br/>· mark Needs review"])

    classDef guarantee fill:#3b2f10,stroke:#e8a33d,stroke-width:2px,color:#fff;
    class VER guarantee
```

The verifier's thresholds and the risk-tiered trust floor are documented in
[grounding.md](grounding.md); the guarantee is never loosened to make a claim pass.

## 4. Pipeline selection

The API selects a build pipeline from `LUNARIS_PIPELINE` (`apps/api/.../config.py`), defaulting to the
agent harness and degrading safely when no model key is reachable:

```mermaid
flowchart TD
    REQ["build request"] --> SW{"LUNARIS_PIPELINE"}
    SW -->|"agent (default)"| AG["Deep-agent harness<br/>plan + tools + subagent"]
    SW -->|live| LV["Legacy single-shot orchestrator"]
    SW -->|stub| ST["Deterministic stub<br/>no key · instant · always works"]
    AG --> KEY{"Anthropic key reachable?"}
    KEY -->|yes| CLAUDE["real Claude"]
    KEY -->|no| DRAFT["keyless Draft tier<br/>local Qwen + BGE + DuckDuckGo"]
```

When no Anthropic key is reachable, the build runs in a labelled **Draft tier** on fully local,
self-hosted models — see [deployment.md](deployment.md#the-keyless-draft-tier).

---

For how this runs in production — the Azure topology, multi-tenancy, and bring-your-own-key model —
see **[deployment.md](deployment.md)**.

*These diagrams are the map; the deeper "why" lives in the linked docs and the code under
[`packages/`](../packages) and [`apps/`](../apps).*
