from lunaris_runtime.schema import Course, VerifierStatus

from ..claims import collect_claims
from ..report import CheckResult

_NAME = "factuality"


def factuality_check(course: Course) -> CheckResult:
    """Failure-B line: no claim ships live and unsupported.

    Deterministic re-check of the publish gate over every claim in the course: each must
    be SUPPORTED with a citation or explicitly CUT. (Sampled re-verification by a judge is
    the live layer, deferred.)
    """
    claims = collect_claims(course)
    live_unsupported = [
        claim
        for claim in claims
        if claim.supported_by is None and claim.verifier_status is not VerifierStatus.CUT
    ]
    if live_unsupported:
        example = live_unsupported[0].text
        return CheckResult(
            _NAME,
            passed=False,
            detail=f"{len(live_unsupported)} live unsupported claim(s), e.g. {example!r}",
        )

    supported = sum(
        1
        for claim in claims
        if claim.verifier_status is VerifierStatus.SUPPORTED and claim.supported_by
    )
    cut = sum(1 for claim in claims if claim.verifier_status is VerifierStatus.CUT)
    return CheckResult(
        _NAME,
        passed=True,
        detail=f"{supported}/{len(claims)} claims supported, {cut} cut, none left unsupported",
    )
