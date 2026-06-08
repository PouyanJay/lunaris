# Course-build pipeline — from a subject to a finished course

This traces what happens from the moment a learner submits a **subject** until a **Course** artifact
is built and persisted, on the default **agent** pipeline (`LUNARIS_PIPELINE=agent`,
`AgentCourseBuilder.run()` in [`packages/agent/.../harness/runner.py`](../packages/agent/src/lunaris_agent/harness/runner.py)).

Every stage is a **tool the planning agent calls**; each tool writes its typed result onto a shared
`CourseDraft` (the model plans *when* to call, the tools own the *data*). Two stages are
**deterministic moats** the model cannot talk its way past.

The concrete values below come from the last **CLB 10** build —
`Improve my English to achieve CLB 10` → course `3bf6f86f...` (status `review`).

---

## 1. The pipeline spine

```mermaid
flowchart TD
    U(["Learner submits a subject:<br/>Improve my English to achieve CLB 10"])
    U -->|"raw request : str"| S1

    S1["1 - interpret_request<br/>Claude worker"]
    S1 -->|"CourseBrief"| S2

    S2["2 - research_standard<br/>Claude worker, best-effort"]
    S2 -->|"StandardResearch + research seeds"| S3

    S3["3 - model_learner<br/>Claude worker"]
    S3 -->|"LearnerProfile.frontier"| S4

    S4["4 - extract_concepts<br/>Claude worker"]
    S4 -->|"Extraction: 8 KCs + goal_id"| S5

    S5["5 - build_prerequisite_graph<br/>MOAT A, deterministic"]
    S5 -->|"PrerequisiteGraph: 8 nodes, topoOrder, acyclic"| S6

    S6["6 - design_curriculum<br/>Claude strong"]
    S6 -->|"4 Modules: objectives, Bloom, assessment"| S7

    S7["7 - seed_grounding<br/>deterministic ingest"]
    S7 -->|"SeedReport: research pages to corpus"| S8

    S8["8 - discover_grounding<br/>Claude worker, best-effort"]
    S8 -->|"DiscoveryReport: evidence to corpus"| S9

    S9["9 - author lessons<br/>subagent loop, see section 3"]
    S9 -->|"Lessons with Merrill segments + provenance"| S10

    S10["10 - curate_resources<br/>Claude worker, best-effort"]
    S10 -->|"Resources attached to segments"| S11

    S11["11 - finalize_course<br/>deterministic assembly + critic gate"]
    S11 -->|"Course.model_dump_json by_alias"| OUT

    OUT(["Course persisted to .courses/3bf6f86f....json<br/>status = REVIEW, see section 5"])

    classDef moat fill:#3b2f10,stroke:#d9a441,stroke-width:2px,color:#ffffff;
    classDef loop fill:#10263b,stroke:#4aa3df,stroke-width:2px,color:#ffffff;
    class S5 moat
    class S9 loop
```

> **Pipeline modes.** `agent` (above — the deep-agent harness, with discovery and the
> author/verify/revise loop) is the default. `live` runs the legacy single-shot `Orchestrator` (no
> discovery, one-pass authoring). `stub` runs the same `Orchestrator` with deterministic stubs
> (offline demo, no keys). Mode is chosen by `LUNARIS_PIPELINE`; factories live in
> [`apps/api/.../dependencies.py`](../apps/api/src/lunaris_api/dependencies.py).

---

## 2. The prerequisite graph the CLB 10 build produced (Moat A output)

Stage 5 is deterministic: it orders the extracted knowledge components into an **acyclic** graph and
emits a topological teaching order. The model cannot reorder it.

```mermaid
flowchart LR
    voc["advanced_vocabulary_breadth<br/>diff 0.10, apply"]
    syn["complex_syntax_production<br/>diff 0.15, apply"]
    reg["advanced_register_control<br/>diff 0.20, apply"]
    inf["implicit_inference_reading<br/>diff 0.25, analyze"]
    acc["varied_accent_fluency<br/>diff 0.25, understand"]
    idi["idiomatic_precision<br/>diff 0.30, apply"]
    nat["native_like_fluency<br/>diff 0.50, apply"]
    goal(["clb_10_integrated_mastery<br/>diff 1.00, create, GOAL"])

    voc -->|0.78| reg
    syn -->|0.78| reg
    reg -->|0.72| goal
    inf -->|0.78| goal
    acc -->|0.75| goal
    idi -->|0.72| goal
    nat -->|0.85| goal

    classDef goalNode fill:#10263b,stroke:#4aa3df,stroke-width:2px,color:#ffffff;
    class goal goalNode
```

Topological order:
`advanced_vocabulary_breadth, complex_syntax_production, advanced_register_control,
implicit_inference_reading, varied_accent_fluency, idiomatic_precision, native_like_fluency,
clb_10_integrated_mastery`

Stage 6 then groups these 8 KCs into **4 modules** by backward design (see the table in section 4).

---

## 3. The authoring loop (Stage 9 — Moat B lives here)

Lessons are authored by a delegated subagent that runs a deterministic LangGraph loop
([`harness/authoring/loop.py`](../packages/agent/src/lunaris_agent/harness/authoring/loop.py)). The
**verifier is an independent, deterministic gate** — it grounds each authored claim against the
per-course corpus and marks it `SUPPORTED` or `CUT`. No cut claim ships.

```mermaid
flowchart TD
    A["author - Claude worker<br/>first-pass Merrill lesson<br/>activate, demonstrate, apply, integrate<br/>plus extract claims"]
    A -->|"Lesson with claims"| V

    V["verify - MOAT B, deterministic<br/>ground each claim vs corpus<br/>mark SUPPORTED or CUT + Citation"]
    V --> D{"cut == 0, or budget hit,<br/>or no progress?"}

    D -->|"cuts remain, budget left"| R["revise - Claude worker<br/>re-author, replace or soften cut claims"]
    R -->|"revised Lesson"| V

    D -->|"done"| T["triage<br/>drop residual cut claims<br/>flag needs_review if a goal-critical claim was cut"]
    T -->|"verified Lessons + provenance"| OUT2(["back to spine: curate_resources"])

    classDef moat fill:#3b2f10,stroke:#d9a441,stroke-width:2px,color:#ffffff;
    class V moat
```

> **Revise budget** is risk-tiered: `LOW` = 1 round, `HIGH` = 3 (hard cap 3). Termination is
> deterministic: stop when `cut == 0`, the cap is hit, or the cut set stops shrinking.

---

## 4. What the CLB 10 build passed through each stage

| # | Stage (impl) | Input | Output | CLB 10 concrete value |
|---|---|---|---|---|
| - | user | - | `str` | `"Improve my English to achieve CLB 10"` |
| 1 | `interpret_request` (worker) | raw request `str` | `CourseBrief` | goal = CLB 10 integrated mastery; settings: budget $5 / 30 min, qualityFloor `standard`, maxModules 12; risk tier `low` |
| 2 | `research_standard` (worker) | `CourseBrief` | `StandardResearch` + research seeds | CLB competency descriptors to seeds for the corpus (best-effort; offline means thin) |
| 3 | `model_learner` (worker) | `CourseBrief` | `LearnerProfile.frontier` | `frontier = []` (no prior assumed on this run) |
| 4 | `extract_concepts` (worker) | topic + brief + frontier | `Extraction` = `KnowledgeComponent[]` + `goal_id` | **8 KCs** from `advanced_vocabulary_breadth` (diff 0.10) to `clb_10_integrated_mastery` (diff 1.00, goal) |
| 5 | `build_prerequisite_graph`, **Moat A** (deterministic) | `KnowledgeComponent[]` | `PrerequisiteGraph` | 8 nodes, 7 edges, `isAcyclic=true`, topoOrder (see section 2) |
| 6 | `design_curriculum` (strong) | `PrerequisiteGraph` (+ brief) | `Module[]` | **4 modules**: m0 *Advanced Expressive Language Foundations* (3 KCs, 3 objectives, 6 assessment items, competency "Share information with precision and fluency"); m1 *Nuanced Comprehension Across Modalities*; m2 *Idiomatic and Native-like Performance*; m3 *Integrated CLB 10 Mastery* (Bloom `create`) |
| 7 | `seed_grounding` (deterministic) | research seeds | `SeedReport` | ingest already-fetched research pages into the per-course corpus (no re-fetch) |
| 8 | `discover_grounding` (worker) | draft (KCs + modules + brief) | `DiscoveryReport` | search, vet, score, ingest evidence (best-effort; offline/keyless means thin corpus) |
| 9 | author loop, **Moat B** (see section 3) | `Module[]` | `Lesson[]` + `Citation[]` | each module to 1 lesson with 4 **Merrill** segments. m0-l0: activate (3 claims), demonstrate (8 claims), apply (4 claims), integrate (3 claims); gagne 9 events; loadEstimate 18.0 |
| 10 | `curate_resources` (worker) | `Module[]` (+ brief) | `Resource[]` on segments | m0-l0 got 3 vetted resources, e.g. *"Accuracy and Fluency..."* (video, trust `open`, cred 0.85); *"Module 2 Instructional Reference Guide"* (docs, trust `official`, cred 0.80) |
| 11 | `finalize_course` (deterministic + critic) | full draft | `Course` (persisted) | assembled, critic gate run, written to `.courses/3bf6f86f....json`, `status = review` |

---

## 5. The honest outcome of this run — why it ended in `review`, not `published`

This CLB 10 build is a useful example precisely because the verification moat **fired hard**:

- The author wrote **59 claims** across all lessons.
- The corpus was thin (offline / no live search keys on this run), so the verifier could ground
  **none** of them: **59 CUT, 0 SUPPORTED**, and `provenance = []`.
- Because goal-critical claims were cut, `triage` flagged `needs_review`, the critic gate withheld
  publication, and the course was persisted with **`status = review`** instead of `published`.

That is the system working as designed — it would rather ship a reviewable, ungrounded-flagged course
than publish unsupported claims. Filling the per-course corpus (manual ingest, auto-discovery with
search keys, or research seeding) is what turns those CUTs into SUPPORTED citations and flips the
status to `published`.

---

## 6. Where this runs in production — Azure (pilot scale)

The whole pipeline above executes **inline inside the API request** (streamed to the browser over
SSE). At **pilot scale** (a handful of concurrent builds) that runs as-is on **Azure Container Apps**,
with **managed Supabase** as the data + identity plane. The diagram below is the production topology
for that scale; the heavy build is **not** yet split into a worker/queue — that's a later phase, only
if load grows (see [`.claude/plans/azure-deployment-plan.md`](../.claude/plans/azure-deployment-plan.md)).

```mermaid
flowchart TB
    User(["Learner — browser"])

    subgraph azure["Microsoft Azure — single region"]
        SWA["Azure Static Web Apps<br/>React SPA (Vite build)"]
        API["Azure Container Apps<br/>lunaris-api · FastAPI / uvicorn<br/>min 1 – max ~3 replicas<br/>scale on HTTP concurrency<br/>build runs inline, streamed over SSE"]
        MI{{"Managed Identity"}}
        KV[("Key Vault<br/>provider + Supabase secrets")]
        ACR[("Container Registry<br/>lunaris-api image")]
        LOG[("Log Analytics + App Insights<br/>structlog JSON · run_id / request_id")]
    end

    subgraph supa["Supabase Cloud (Pro) — co-located region"]
        AUTH["Supabase Auth<br/>login → JWT"]
        TUSER[("Postgres + pgvector<br/>courses · course_runs · run_events<br/>RLS: user_id = auth.uid()")]
        TCORP[("Postgres + pgvector<br/>grounding corpus · authorities<br/>shared, service-role, read-only")]
    end

    subgraph extapi["External APIs — egress"]
        ANT["Anthropic Claude<br/>Opus + Haiku"]
        VOY["Voyage AI<br/>embeddings"]
        TAV["Tavily<br/>search"]
        YT["YouTube Data API"]
    end

    User -->|"HTTPS — load SPA"| SWA
    User <-->|"login (magic-link / OAuth)"| AUTH
    SWA -->|"HTTPS + Bearer JWT<br/>start / stream a build (SSE)"| API

    API -->|"validate JWT (JWKS)"| AUTH
    API -->|"per-user — RLS enforced"| TUSER
    API -->|"service-role · pgvector retrieval"| TCORP

    API -->|"read secrets"| MI
    MI --> KV
    ACR -.->|"image pull"| API
    API -->|"logs / traces"| LOG

    API -->|"LLM generation"| ANT
    API -->|"embed claims + corpus"| VOY
    API -->|"research + resources"| TAV
    API -->|"video metadata"| YT

    classDef store fill:#10263b,stroke:#4aa3df,stroke-width:1.5px,color:#ffffff;
    classDef secret fill:#3b2f10,stroke:#d9a441,stroke-width:1.5px,color:#ffffff;
    classDef egress fill:#16241a,stroke:#5fae5f,stroke-width:1.5px,color:#ffffff;
    class TUSER,TCORP,LOG,ACR store
    class KV,MI secret
    class ANT,VOY,TAV,YT egress
```

**Two paths through it.** The *request* path: the browser loads the SPA from Static Web Apps, signs
in against Supabase Auth (a JWT), and calls the Container Apps API with that bearer token; the API
validates the JWT and runs the section-1 pipeline inline, streaming `run_events` back over SSE. The
*data* path: user-owned tables (`courses`, `course_runs`, `run_events`) are read/written **on behalf
of the user with RLS enforced** (`auth.uid()`), while the **shared grounding corpus** is read
service-role (it's a global asset, §2/§5). Secrets never live in the image or env files — the API
fetches them from **Key Vault via its Managed Identity**; logs (with the `run_id`/`request_id`
correlation IDs used throughout this doc) stream to **Log Analytics**.

> **Deferred (Phase 4, only past pilot):** the inline build moves behind a **queue + worker Container
> App**, and the browser tails progress via **Supabase Realtime** on `run_events` instead of a held
> SSE connection. The `run_events` transcript (§3) is what makes that split a drop-in.

---

## Legend

- **MOAT** = a deterministic guarantee the model cannot override. **A** = prerequisite ordering
  (acyclic, topological). **B** = claim verification (every published claim is grounded or cut).
- **worker / strong** = Claude tier. Worker (Haiku-class) handles extraction, interpretation,
  profiling, authoring, revision, discovery, curation; strong (Opus-class) handles the agent planner,
  the curriculum architect, and the independent claim assessor.
- **best-effort** = the stage degrades gracefully (e.g. offline) without failing the build.
- Schemas live in [`packages/runtime/.../schema/`](../packages/runtime/src/lunaris_runtime/schema/);
  the final `Course` is serialized camelCase via `Course.model_dump_json(by_alias=True)` by the
  `CourseStore`.

---

## Appendix — Why Azure Container Apps, not App Service

The §6 diagram hosts the API on **Azure Container Apps (ACA)**, not Azure App Service. That's a
deliberate choice driven by this pipeline's execution model.

**The deciding factor — long, streamed builds.** A build runs **inline in the request and streams
over SSE for 30s–5 min** (§1, §6). Azure App Service's front end enforces a **hard ~230-second
(3.8 min) idle timeout that cannot be raised** — it would cut long builds and SSE streams mid-flight.
ACA tolerates long-lived streamed connections (with the ingress timeout tuned and SSE heartbeats),
so the inline model works without a rewrite.

**Two more reasons ACA fits better:**
- **A clean path to the Phase-4 worker/queue split.** ACA runs a second long-running **worker
  container** with **KEDA queue-based autoscaling** natively. App Service has no real background-worker
  primitive (you'd bolt on WebJobs or a separate Functions app).
- **Scale-to-N on HTTP concurrency**, with per-replica concurrency control — which matters because
  each build is heavy (so a replica should take only a few at once).

**App Service isn't impossible — but it costs you a redesign.** App Service *can* run the container
(Web App for Containers) and is fine for short requests. To use it you'd have to **drop the held SSE
stream and switch the client to short-poll `run_events`** (to dodge the 230s cut), and accept the
weaker background-work story for Phase 4. With today's inline-SSE design, **Container Apps is the
right call** — and it's typically a bit cheaper at idle on the consumption plan.

> **Rule of thumb:** long-lived/streamed or background-heavy → **Container Apps**. Short
> request/response web apps → App Service is fine. This pipeline is the former.
