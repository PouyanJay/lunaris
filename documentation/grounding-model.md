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

*(Written in T1 — the trust tiers, the credibility blend, the risk-tiered floor, and the
moat-defends-itself guarantee.)*

## The three acquisition modes

One corpus, three adapters writing the same shape:

- **manual** — you upload / paste / name a source (the Corpus tab).
- **auto** — the discovery agent searches, fetches, vets, and ingests sources for the topic.
- **seed** — the build ingests the pages it already fetched and vetted while researching the standard.

*(Detailed in T2, with the per-mode costs and key requirements.)*

## Costs & keys

*(Written in T2 — what each mode costs, which keys it needs, and how it degrades without them.)*

## Honest limits

*(Written in T2.)*
