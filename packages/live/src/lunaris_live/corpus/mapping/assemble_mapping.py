from ...graph.schema import ConceptGraph
from ..schemas.asset import NodeAsset
from .models.candidate import MappingCandidate
from .models.context import MappingContext
from .models.judgment import MappingJudgment
from .models.request import MappingRequest
from .models.review import MappingReview
from .result_graph import mapping_result
from .schemas.report import MappingDecision, MappingGap, MappingReport
from .schemas.verdict import MappingVerdict
from .verified_asset import verified_asset


def assemble_mapping(
    request: MappingRequest, context: MappingContext, judgment: MappingJudgment
) -> ConceptGraph:
    """Check pairs, verify evidence, then assemble assets and the public coverage report."""
    review = _review(context, judgment)
    assets = _assets(request, context, review)
    return mapping_result(request, _report(request, context, review), assets)


def _pair_integrity(
    context: MappingContext, judgment: MappingJudgment
) -> tuple[set[tuple[str, str]], tuple[str, ...]]:
    candidates = {candidate.locator for candidate in context.candidates}
    proposed = [(item.node_id, item.locator) for item in judgment.proposal.mappings]
    reviewed = [(item.node_id, item.locator) for item in judgment.verdicts.mappings]
    valid = {
        (node, locator)
        for node, locator in proposed
        if node in context.source_nodes and locator in candidates
    }
    issues: list[str] = []
    if len(set(proposed)) != len(proposed) or len(valid) != len(proposed):
        issues.append("invalid_proposal")
    if len(set(reviewed)) != len(reviewed) or set(reviewed) != valid:
        issues.append("invalid_verdict")
    return valid, tuple(issues)


def _review(context: MappingContext, judgment: MappingJudgment) -> MappingReview:
    pairs, issues = _pair_integrity(context, judgment)
    candidates = {candidate.locator: candidate for candidate in context.candidates}
    verdicts = {(item.node_id, item.locator): item for item in judgment.verdicts.mappings}
    decisions: list[MappingDecision] = []
    for node_id, locator in sorted(pairs):
        decision = _decision(node_id, candidates[locator], verdicts.get((node_id, locator)))
        if issues and decision.status == "approved":
            decision = decision.model_copy(
                update={"status": "rejected", "reason": "invalid_evidence", "evidence": ()}
            )
        decisions.append(decision)
    return MappingReview(tuple(decisions), issues)


def _decision(
    node_id: str, candidate: MappingCandidate, verdict: MappingVerdict | None
) -> MappingDecision:
    reason = "missing_verdict" if verdict is None else "verifier_rejected"
    if verdict is not None and verdict.approved:
        valid = (
            len(candidate.excerpt) <= 8000
            and verdict.evidence
            and all(quote.strip() and quote in candidate.excerpt for quote in verdict.evidence)
        )
        reason = "verified" if valid else "invalid_evidence"
    approved = reason == "verified"
    return MappingDecision(
        node_id=node_id,
        locator=candidate.locator,
        status="approved" if approved else "rejected",
        reason=reason,
        evidence=verdict.evidence if approved and verdict else (),
    )


def _assets(
    request: MappingRequest, context: MappingContext, review: MappingReview
) -> dict[str, list[NodeAsset]]:
    candidates = {candidate.locator: candidate for candidate in context.candidates}
    assets: dict[str, list[NodeAsset]] = {}
    for decision in review.decisions:
        if decision.status == "approved":
            asset = verified_asset(request, candidates[decision.locator], decision)
            assets.setdefault(decision.node_id, []).append(asset)
    return assets


def _report(
    request: MappingRequest, context: MappingContext, review: MappingReview
) -> MappingReport:
    candidates = {candidate.locator: candidate for candidate in context.candidates}
    approved = [decision for decision in review.decisions if decision.status == "approved"]
    covered = {
        decision.node_id
        for decision in approved
        if candidates[decision.locator].kind in ("lesson", "video_clip")
    }
    missing = context.source_nodes - covered
    mapped = {decision.locator for decision in approved}
    gaps = [*context.gaps, *(MappingGap(reason=issue) for issue in review.issues)]
    gaps.extend(
        MappingGap(node_id=node, reason="node_without_material") for node in sorted(missing)
    )
    gaps.extend(
        MappingGap(locator=locator, reason="unmapped_candidate")
        for locator in candidates
        if locator not in mapped
    )
    return MappingReport(
        source_digest=request.snapshot.source.digest,
        run_id=request.run_id,
        status="failed" if missing or review.issues else "passed",
        mappings=review.decisions,
        gaps=tuple(gaps[:2000]),
        issues=review.issues,
    )
