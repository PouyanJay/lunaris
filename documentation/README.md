# Lunaris documentation

Lunaris turns a topic into a real, verified course: an agent plans the curriculum, writes the
lessons, orders every prerequisite, and grounds every factual claim against evidence. These docs
explain how to run it, how it works, and how it is deployed.

Start with the [project README](../README.md) for the one-paragraph overview and install steps.

## Use it

- **[Getting started](getting-started.md)** — a hands-on first build, from a cold machine to a
  finished course, with the output to expect at each step.

## Understand it

- **[Architecture](architecture.md)** — the system design in diagrams: the product surface, the
  agentic core, the two deterministic correctness guarantees, and how a build flows across layers.
- **[Build pipeline](build-pipeline.md)** — the eleven-stage build traced end to end on a worked
  example, including the authoring loop where claims are verified.
- **[Relevance](relevance.md)** — how Lunaris scopes a course to the right *subject and level*, what
  that needs, and how it degrades honestly without optional keys.
- **[Grounding](grounding.md)** — the trust model behind every citation: trust tiers, the
  risk-tiered credibility floor, and the three ways evidence enters a course's corpus.

## Operate it

- **[Deployment](deployment.md)** — the production topology on Azure and Supabase, the
  multi-tenancy and bring-your-own-key model, and why the API runs on Container Apps.
- **[Video observability](video-observability.md)** — the structured events behind explainer-video
  generation: the failure taxonomy, the degraded-issue histogram, and the queries that read them.

---

Each page is self-contained and cross-links the others where concepts meet. The diagrams are
authored in Mermaid and render on GitHub.
