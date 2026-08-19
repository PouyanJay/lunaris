from .schema import NodeKnowledge


def claim_of(known: NodeKnowledge | None) -> float | None:
    """The placement claim standing on this concept, or ``None`` when there is none to stand.

    A claim stands only while nothing has been demonstrated about the concept: the first evidence
    settles it (``apply_evidence`` clears it, and ``seed_priors`` never seeds over evidence), so a
    row with both would be a row some writer got wrong. Read here, once, rather than in each of the
    director, Tier 2 and the update — three readers of one rule is where drift comes from — and
    read defensively, so such a row reads as evidence rather than as a claim.
    """
    if known is None or known.evidence_count > 0:
        return None
    return known.prior
