# How Lunaris keeps a course *relevant*

Lunaris's two correctness moats — prerequisite order and claim grounding — guarantee a course is
**well-ordered and well-sourced**. They do **not**, on their own, guarantee it's about the *right
thing at the right level*. This doc explains the part of the pipeline that does, and is honest about
what it needs to work and how it degrades when it can't.

## The failure it fixes

Ask for *"Improve my English to achieve CLB 10"* (CLB 10 is the **top** advanced band) and a naive
generator enumerates the whole subject from the bottom — it starts at *"the English alphabet and basic
phonetics."* The result is coherent, correctly ordered, fully grounded… and **useless** to an advanced
learner. Every moat did its job; the course was simply *about the wrong level*.

The fix is not a smarter moat. It's adding the front of the pipeline a good human tutor runs **before**
designing anything: read the request as a *goal for a learner at a level*, find out what the level
actually means, work out what the learner already has, and scope the course to the **gap** — then let
the moats operate over that relevant, scoped input.

## The pipeline, stage by stage

Each stage is a tool the agent calls; each streams to the live build timeline so you can watch it
happen. New stages were added in front of, and beside, the original moats — the moats themselves are
unchanged.

| Stage | What it does | Needs | Without it |
|---|---|---|---|
| **Interpret** | Reads the request into a typed `CourseBrief` — subject, goal, target level, named standard, assumed prior, deliverable shape, preferences. | Anthropic key | The build still runs; the brief is a topic-derived default. |
| **(opt-in) Confirm** | An infer-and-confirm clarifier: the learner reviews the inferred level / what they know / depth / style, each pre-picked, and confirms or adjusts. | Anthropic key (to infer) | Skipped by default — the inference is used as-is (one click). |
| **Research** | Grounds the target standard in its **real** competency descriptors (e.g. fetches the CLB 10 descriptors), with provenance. | `SEARCH_API_KEY` | Degrades honestly to `research: unavailable`; the build continues on the model's internal knowledge. |
| **Model the learner** | Infers the learner's **frontier** — the foundations to assume known and skip — from the brief. | Anthropic key | Empty frontier (true-novice assumption) — the old behaviour. |
| **Scope to the gap** | Extracts only the knowledge components that distinguish the target level from the assumed prior — the competencies that *define* the goal — not the whole ladder. | Anthropic key | — (this is where the alphabet-up bug dies). |
| **Order + design backward** | The prerequisite-graph moat orders the gap KCs (still acyclic); the architect maps modules to the standard's competencies and authors each lesson as a personalized arc (*expects → strategies → worked example → practice → self-check*). | Anthropic key | — (moats unchanged). |
| **Author + verify** | The author → verify → revise subagent writes each lesson and grounds every claim; unsupported claims are cut. | Anthropic key (+ Voyage/corpus for real citations) | Without a corpus the verifier fails safe — cuts every claim, withholds *Published* — the structure is still correct. |
| **Curate resources** | Attaches vetted external resources (video / article / docs / practice / tool / reference) per lesson phase, each with a one-line "why" + trust tier + provenance. | `SEARCH_API_KEY` (+ optional `YOUTUBE_API_KEY`) | No resources attached; the verified lesson is still the spine. |

## The honest part: what actually needs a search key

This is the line we don't want to blur:

- **The relevance fix itself needs no search key.** Interpret → model-the-learner → gap-scoped
  extraction are all prompt-driven from the brief and the inferred frontier. *"Improve my English to
  CLB 10"* builds an **advanced** course with only an Anthropic key — no web search required.
- **Research and resources are enhancements gated on `SEARCH_API_KEY`** (Tavily). They make the course
  *grounded in the real standard* and *point to the best of the web*. Absent, the build still produces
  a relevant, right-level course — it just can't cite the official descriptors or attach external
  resources, and says so (`research: unavailable`, no resources) rather than faking either.
- **`YOUTUBE_API_KEY` is a further enhancement** for richer video metadata; without it, video
  candidates come through the shared search, vetted the same way.

So there are three honest tiers: **Anthropic key only** → relevant, right-level course;
**+ `SEARCH_API_KEY`** → grounded in the real standard, with curated resources;
**+ Voyage/corpus** → publishable claim-level citations.

## Costs & guardrails

- **Search APIs are metered.** Each build with research + curation issues a bounded number of search +
  fetch calls — a hard **per-build budget** (a few searches for research, a few per resource kind),
  capped like the authoring loop's round limit. On exhaustion it degrades (`partial`/`unavailable`,
  fewer resources) rather than running away. The caps are conservative defaults, tunable in settings.
- **No key, no calls.** With `SEARCH_API_KEY` unset the research and curation steps use deterministic
  stubs — zero network, zero cost — so the no-key path (and CI) stays free and instant.
- **The LLM relevance judge is kept blind to source labels** — it scores a resource on merit; the
  *user* sees the trust tier. We never let a domain's brand stand in for quality.

## What the moats still guarantee (unchanged)

Relevance work happens **in front of** the moats; it never weakens them. The prerequisite-graph moat
still guarantees acyclic, prerequisite-first ordering — now over the gap-scoped graph. The claim
verifier still cuts any claim it can't ground. The personalization (frontier, confirmed preferences)
is **scaffolding** that steers *what* is taught and *how* it's written; it is never treated as a
claim, so the factuality guarantee is untouched.

## Where to look in the code

- Stages: `packages/agent/src/lunaris_agent/harness/tools/` (`interpret_request`, `research_standard`,
  `model_learner`, `extract_concepts`, `prereq_graph`, `design_curriculum`, `curate_resources`).
- The brief + clarifier contracts: `packages/runtime/src/lunaris_runtime/schema/`
  (`course_brief.py`, `clarifier.py`) and `lunaris_runtime/clarifier/`
  (`build_clarifier`, `apply_clarification`).
- Key-gating (the honest degradation): `packages/agent/src/lunaris_agent/composition.py`
  (`_researcher_from_env`, `_curator_from_env`, `_video_source_from_env`).
- The opt-in confirm UI: `apps/web/src/components/personalize/`.
