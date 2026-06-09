# Architecture

The system design of Lunaris in five diagrams. Lunaris is an **agent‑first** application: a conventional
product surface (web + API + Supabase) wraps a deep‑agent core that plans a course build and calls every
capability — including two deterministic correctness moats — as **tools**.

Four invariants hold across every layer (and the harness enforces them):

1. **Reasoning vs recall** — the agent reasons about plans; authoritative facts flow through capability
   tools, never the model's memory.
2. **Tools vs orchestration** — each capability is its own package; the MCP registry is a thin adapter, not a home for logic.
3. **Provenance is structural** — tool results carry where the data came from (source, trust, tool‑call id, timestamp), constructed at the source and flowing untouched to the UI.
4. **Correlation everywhere** — every run carries a `run_id` propagated via `structlog` contextvars, so one build can be traced across every layer.

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

    subgraph Moats["Deterministic moats"]
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

    classDef moat fill:#3b2f10,stroke:#e8a33d,stroke-width:2px,color:#fff;
    class GRAPH,VERIFY moat
```

The harness exposes the same two moats **twice**: as in‑process tools to its own planner, and via the
**MCP registry** so any MCP client can call them. The registry is a thin adapter — the logic lives in
`packages/graph` and `packages/grounding`.

## 2. Build sequence

The planner drives the build by calling tools in a sensible order; each tool emits a typed
`ProgressStage` event that streams to the web timeline over SSE. The two moats (◆) are deterministic.

```mermaid
sequenceDiagram
    autonumber
    participant L as Learner / Web
    participant API as API (SSE)
    participant A as Agent harness
    participant W as Claude workers
    participant G as Graph moat ◆
    participant S as Authoring subagent
    participant V as Verifier moat ◆
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

## 3. The authoring loop (Moat B, up close)

Lessons are authored by a LangGraph subagent that **grounds before it ships**: every factual claim is
checked against retrieved evidence, and unsupported claims trigger a bounded revise — not a rubber stamp.

```mermaid
flowchart LR
    START(["module + objectives"]) --> AUTH["author lesson<br/>Claude strong"]
    AUTH --> VER{{"verify claims<br/>retrieve + assess + trust floor"}}
    VER -->|all supported| DONE(["grounded lesson"])
    VER -->|some cut| REV["revise<br/>repair / drop cut claims"]
    REV --> VER
    VER -.->|revise budget exhausted| TRIAGE(["ship supported only<br/>· mark Needs review"])

    classDef moat fill:#3b2f10,stroke:#e8a33d,stroke-width:2px,color:#fff;
    class VER moat
```

The verifier's thresholds and the risk‑tiered trust floor are documented in
[grounding-model.md](grounding-model.md); the moat is never loosened to make a claim pass.

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

## 5. Deployment (production)

Lunaris runs on Azure with Supabase Cloud for data + identity. Compute is **Azure Container Apps** (not
App Service — the long SSE build outlives a 230s gateway timeout) and **Static Web Apps** for the SPA.
The keyless Draft tier runs as scale‑to‑zero CPU inference sidecars.

```mermaid
flowchart TB
    USER(["Browser"])
    subgraph Azure
        SWA["Static Web Apps<br/>lunaris.pouyan.ai · SPA"]
        subgraph ACAENV["Container Apps environment"]
            APIC["lunaris-api<br/>FastAPI · agent · min 1"]
            INF["inference<br/>Qwen · CPU · scale-to-0"]
            EMB["embeddings<br/>BGE · CPU · scale-to-0"]
        end
        KV["Key Vault<br/>BYOK master key · provider keys"]
    end
    subgraph Supabase["Supabase Cloud"]
        AUTH["Auth · ES256 / JWKS"]
        PG[("Postgres<br/>pgvector · RLS")]
    end

    USER -->|HTTPS| SWA
    SWA -->|"api.lunaris.pouyan.ai · authedFetch + SSE"| APIC
    USER -. login .-> AUTH
    APIC -->|verify JWT via JWKS| AUTH
    APIC -->|RLS-scoped queries| PG
    APIC -->|"keyless: internal ingress"| INF
    APIC --> EMB
    APIC -->|decrypt per-run keys| KV
```

**Multi‑tenancy + BYOK.** Each tenant authenticates with Supabase (ES256, verified by the API via JWKS),
rows are isolated by per‑user RLS, and each tenant supplies their **own** provider keys — stored
AES‑GCM‑encrypted (master key from Key Vault, never the DB) and injected into a run's context, never the
process environment, never logged. CI/CD is GitHub Actions (`cd-dev`, `cd-prod` build‑once‑promote,
`cd-inference`).

---

*These diagrams are the map; the deeper "why" lives in the linked docs and the code under
[`packages/`](../packages) and [`apps/`](../apps).*
