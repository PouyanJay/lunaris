from lunaris_grounding.evidence import Evidence


def render_evidence(evidence: list[Evidence]) -> str:
    """Render evidence for the assessor prompt — deliberately BLIND to the trust label (§10).

    Only the id + the text (snippet/title/url) reach the judge; ``trust_tier`` and ``credibility``
    are withheld so the verdict can't be biased by a source's authority badge (the label-bias
    invariant). Trust is applied separately + deterministically by the Verifier's risk-tiered floor,
    never by the LLM. Pure + module-level so the invariant is unit-testable without a model call.
    """
    return "\n".join(
        f"- [{e.citation.id}] {e.citation.snippet or e.citation.title or e.citation.url or ''}"
        for e in evidence
    )
