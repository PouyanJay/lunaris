# How Lunaris keeps a course *grounded* — the trust model and the corpus

Lunaris's claim verifier (Failure-B moat) cuts any factual sentence it can't support against
retrieved evidence. That guarantee is only as honest as the **evidence it retrieves from** — the
*grounding corpus*. This doc explains where that corpus comes from, how every source is graded for
trust, and how the verifier stays a safety check rather than a rubber stamp even when the system finds
its own evidence. It is the grounding companion to [relevance-model.md](relevance-model.md) (which
covers keeping a course *relevant*).

> **Scope note:** grounding is **per-course only**. There is no shared, cross-topic "library" a source
> is promoted into — a vector-similar chunk from a close-but-different topic could be rubber-stamped,
> so trust beats reuse. Every chunk is scoped to the course it was acquired for.

## The risk this defends against

Search makes a subtle failure possible. The verifier's promise is *"no unsupported claim ships."* But
if the same system that *writes* a claim also *fetches the page that supports it*, you get a
confirmation-bias loop: the author writes "X is true" → discovery searches "X" → finds an SEO blog or
AI-slop page that also says X → the verifier sees agreement → SUPPORTED. The claim is now "grounded"
by garbage. So the goal is not "auto-find a corpus." It is **auto-find a corpus the verifier can still
be trusted to police** — and make every claim's evidence trust **visible and auditable**.

## The trust model

Grounding is not binary green/red. Every source carries a **trust tier**, a **source type**, and a
**credibility score**, constructed at acquisition and flowing untouched through ingest → retrieve →
the citation → the reader (the structural-provenance invariant). The verifier then applies a
**risk-adaptive floor** on top of its support check, so *how trustworthy* the evidence is gates
*whether the claim ships* — independently of how strongly the text appears to agree.

### Trust tiers — *where* a source sits in the authority order

A deterministic tier, classified from the source's nature (cheap, transparent, not LLM-decided):

| Tier | Meaning | Assigned to |
|---|---|---|
| **official** | the standard's own authority or a government / standards body (`*.gov`, RFC/ISO/W3C) | auto-discovery, spine/pack hit |
| **vouched** | a source the **user** supplied directly — trusted because the learner chose it | manual ingest |
| **reputable** | an established institution (a university, a major organisation, `*.edu`/`*.ac`) | auto-discovery |
| **open** | the general web — usable, but must earn trust through corroboration | auto-discovery default |
| **blocked** | a denylisted domain (content farms, social posts, link farms) | **never** fetched or shown |

An un-tiered source (one whose tier could not be resolved at all) is treated as **open** — never
"trusted by omission."

### Source types — *what* a source is

Orthogonal to the tier: the tier says where a source sits, the **source type** says what it *is*, so
an unknown journal can still read as scholarly and a slick blog on a reputable host does not coast on
its host. The types are **peer-reviewed**, **preprint** (a notch below peer-reviewed), **official**
docs, **database**, **docs**, **reference** works, and plain **web** (the unclassified open-web
default). The type is carried on the citation for the reader.

### The credibility score — a transparent blend, not a black box

Each source gets a `credibility ∈ [0, 1]`, dominated by its **tier prior** and adjusted by signals
the 2026 RAG-trust literature names (relevance to the topic, extraction quality, cross-source
agreement). The priors:

| Tier | Credibility prior |
|---|---|
| official | 0.90 |
| vouched | 0.85 |
| reputable | 0.75 |
| open | 0.50 (nudged ±0.15 by extraction quality → at most 0.65) |
| blocked | 0.00 |

Only the *uncertain* open web is nudged by page shape — a clean, substantive article earns more than
boilerplate sludge; a curated or vouched source's credibility is its prior, not second-guessed by
shape. The blend is logged with its inputs, so a low score is always explainable.

**Authority is topic-relative.** A single global allowlist is a trap: PubMed is authoritative for
medicine and irrelevant for medieval history. So the spine (universal domains), the per-field **packs**
(CS-ML, medicine, physics, chemistry, + a shared multidisciplinary set), and the **denylist** live in
an *editable* `source_authorities` table — nothing is hardcoded. A pack hit sets the **tier prior
only**; it never inflates the credibility score (a degree gets you the interview, not the job). A free
scholarly registry (**OpenAlex**) resolves any source to its peer-reviewed record (venue, DOI,
citations) so authority scales across every field without enumerating the world.

### The risk-tiered trust floor — how the verifier uses all this

The floor is **orthogonal** to the assessor-score thresholds and **AND-joined** with them, so it can
only *tighten* the gate, never loosen it:

- **LOW-risk course** — the floor only excludes **blocked** sources. (Today's behaviour, now
  *recorded* with its trust.)
- **HIGH-risk course** — a claim's chosen evidence must be **curated-or-better** (tier ≥ reputable,
  which vouched clears) **and** credible (credibility ≥ **0.70**) — **or** corroborated by
  **cross-source agreement** across **≥ 2 independent registrable domains**. So authority can *emerge
  from agreement* when no single source is curated.

A claim that fails the floor is **cut** and flows into the existing `needs_review` triage — never
silently shipped. The threshold `0.70` sits just under the reputable prior (0.75), so a curated source
clears it while a nudged-up open-web source (max 0.65) does not.

### The moat defends itself

The reason all of this exists: auto-discovery is exactly where the grounding moat could quietly invert
from a safety check into a rubber stamp (the confirmation-bias loop in [the section above](#the-risk-this-defends-against)).
The floor is what stops it. The poisoning-resistance evals (`test_discovery_poisoning.py`,
`test_seed_poisoning.py`) prove it on every commit: a lone open-web source that *agrees* with a claim
is still **cut** at HIGH risk — even when the support assessor always votes SUPPORTED — because one
uncorroborated open source cannot clear the floor. Only genuine cross-source agreement (or a curated
source) clears it. **Authority emerges from agreement, not from a label.**

### Label-blindness (the judge sees merit, the user sees trust)

Two surfaces, two rules. The LLM support-assessor and the relevance judge are kept **blind to source
labels** — they score the *text* on its merits, never told "this is from Wikipedia" (research shows
the label moves the judge). The trust weighting is applied **deterministically, outside** the model.
The *user*, by contrast, sees the full tier + credibility on every citation and in the live
source-vetting canvas — that transparency is the entire point.

## The three acquisition modes

There is one corpus and three adapters that fill it. **Hybrid falls out for free**: manual, auto, and
seed all emit the *same* candidate-source shape and pass through the *same* trust gate and ingestor —
there is never a "manual corpus" and an "auto corpus," only one corpus where every chunk's provenance
records how it arrived (its `acquisition_mode`). Whatever the mode, the author never picks its own
evidence: discovery is keyed to the **topic / knowledge component**, not to the sentence the author
wrote, so the verifier independently decides whether each sentence is supported.

### manual — you supply the source

Add a document yourself from the per-course **Corpus tab** — paste text, give a URL, or upload a file
(PDF / DOCX / MD / TXT). The source is classified **vouched** (you chose it), deduped, embedded, and
ingested for that course. URL ingest fetches and extracts the page (with an SSRF guard); uploads are
capped at 10 MB. The operator path `make ingest DIR=… COURSE=…` ingests a whole folder. This is the
cold-start answer and the trust escape hatch — *upload your Dijkstra notes, re-ground, and the
citations go green.*

### auto — the system finds its own corpus

The discovery agent fills the corpus before claims are verified. It runs a bounded LangGraph loop —
**plan → search → fetch + extract → gate (score + a label-blind relevance judge) → ingest →
reflect** — and you watch every step in the build canvas: the queries it plans, each source it finds
with its tier + credibility, and the accept/reject verdict with a one-line reason. Found sources are
graded by the same scorer + floor as everything else, so a machine-found page is never trusted just
for being found. Discovery depth is **pre-authorized** up front (the build can't safely pause
mid-flight to ask): **standard** is the one-click default; **thorough** raises the per-round
search/fetch caps and the round ceiling to corroborate more concepts across more domains, for a higher
search cost.

### seed — reuse what the build already read

The research stage (relevance front) already searches, fetches, and trust-classifies authoritative
pages to ground the *brief* — then normally discards the text. Seed mode carries that text forward
into the corpus instead, so the build's claims verify against the very evidence it already read. **No
second fetch, no search key** — it reuses pages already pulled, which makes it the **near-free** half
of a hybrid corpus. Seeded sources are graded by the same scorer + floor (seeded ≠ trusted).

## Costs & keys

Every external key is optional; each unlocks a live path, and its absence falls back to a
deterministic stub (zero network, zero cost), so the no-key path always works. The grounding-relevant
keys:

| Mode / step | Keys it needs | Cost | Without the keys |
|---|---|---|---|
| **claim grounding** (retrieval at verify time) | `EMBEDDINGS_API_KEY` (Voyage) + `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | one embedding per claim, vector lookup | verifier fails safe → every claim **cut** → *Needs review* |
| **manual** ingest | `EMBEDDINGS_API_KEY` + Supabase | one embedding per chunk | in-memory stub corpus (not persisted) |
| **auto** discovery | `SEARCH_API_KEY` (Tavily) + `EMBEDDINGS_API_KEY` + Supabase | **metered** search + fetch (per-build budget) + embeddings | discovery stubbed — no auto corpus |
| **seed** | `EMBEDDINGS_API_KEY` + Supabase (**no** search key) | embeddings only (reuses research fetches) | seeding stubbed — no seed corpus |

Notes that keep the cost story honest:

- **Search is metered and bounded.** Auto-discovery and research issue a *hard per-build budget* of
  search + fetch calls (capped like the authoring loop's round limit); on exhaustion they degrade
  (`partial` / `unavailable`, fewer sources) rather than running away. The caps are conservative,
  tunable defaults.
- **The scholarly registry (OpenAlex) is free.** Resolving a source to its peer-reviewed record costs
  nothing — it is a free API, not a metered one.
- **Voyage embeddings are the real recurring cost.** Every ingested chunk *and* every claim retrieval
  embeds. Voyage's free tier is **3 requests/minute** — far too low for a full course; a **paid plan**
  is needed for live grounding over a whole run.
- **No key → no calls.** With the keys unset, the research / discovery / seed / retrieval steps use
  deterministic stubs — the CI path (and a curious first run) stays free and instant.

## Honest limits

- **Per-course only.** There is no shared cross-topic library and no promotion; grounding does not
  accumulate across courses (trust beats reuse — see the scope note at the top).
- **Voyage's free tier (3 RPM) cannot ground a whole course.** A real grounded build needs a paid
  embeddings plan; without one, the verifier fails safe and cuts claims, and the course still ships
  correct + ordered, just unpublished (*Needs review*).
- **Discovery depth is chosen up front.** A fire-and-forget build can't pause to ask for more budget
  mid-run, so depth (standard / thorough) is pre-authorized; when a run ends with concepts still thin,
  the canvas says so and you can rebuild thorough.
- **The denylist is hygiene, not a guarantee.** An exhaustive list of bad domains is impossible; the
  real poisoning defense is cross-source agreement + the trust floor + the poisoning evals, not the
  blocklist.

---

*See also [relevance-model.md](relevance-model.md) (keeping a course at the right level) and
[build-a-course-walkthrough.md](build-a-course-walkthrough.md) (a hands-on run, including filling the
corpus so citations go green).*
