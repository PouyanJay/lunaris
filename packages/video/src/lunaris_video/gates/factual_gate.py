import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

import structlog

from lunaris_video.errors import FactualGateError
from lunaris_video.models import GroundingPacket
from lunaris_video.schemas import FRAMING_ONLY_SENTINEL, SceneContract, VideoContract

_logger = structlog.get_logger(__name__)

# A figure is a digit-bearing token: 8, 1,000, 2.5, 47%, 1990. Spelled-out numbers ("eight") are
# deliberately not flagged — the high-risk surface is hard figures, and ordinals like "step one"
# stay clear of false positives.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

# A comparison is an empirical claim ("faster than", "twice as fast", "3x"). Matched conservatively
# — an "-er … than" form, "twice/three times as", or an explicit "N times"/"Nx" — so process words
# like "split in half" are not mistaken for comparisons.
_COMPARISON = re.compile(
    r"\b(?:more|less|fewer|faster|slower|greater|larger|smaller|higher|lower|better|worse|"
    r"cheaper|stronger|weaker|bigger|longer|shorter)\b[\s\w,'-]{0,40}?\bthan\b"
    r"|\btwice as\b|\bthree times as\b"
    r"|\b\d+(?:\.\d+)?\s*(?:times|x)\b",
    re.IGNORECASE,
)


class _Severity(StrEnum):
    """How a factual violation is disposed of (the Phase-1 severity tiers).

    ``MINOR`` — a *grounded* scene narrates a figure no cited claim supports — degrades: the scene
    ships flagged in ``degraded_scenes`` rather than failing the video. ``MAJOR`` — a framing-only
    scene smuggling a figure or comparison (a scene that should assert nothing), or a scene citing a
    claim absent from the packet (structurally ungrounded) — still hard-fails the job clean. The
    split keeps the grounding moat biting where it matters while removing the single biggest
    "whole video lost on one figure" cause.
    """

    MINOR = "minor"
    MAJOR = "major"


@dataclass(frozen=True)
class _Violation:
    """One factual problem found in a scene, tagged with how it should be disposed of.

    ``message`` is the human-readable record (the degrade note for a minor; the failure detail for a
    major); ``unsupported`` is the exact smuggled figures, carried so a major's ``FactualGateError``
    still names what the gate caught.
    """

    scene_id: str
    severity: _Severity
    message: str
    unsupported: list[str]


class FactualGate:
    """Gate C: the video can say only what the lesson's verified claims prove.

    Runs on the CONTRACT right after PLAN (factual content is static once planned, so checking the
    contract is equally correct and strictly cheaper than re-checking rendered frames — it catches
    a smuggled figure before any render compute). For each scene it diffs the numeric figures in
    the narration against the claims the scene cites: a grounded scene's figures must each appear
    in a cited claim, and a framing-only scene may carry no figure and no comparison at all.

    **Severity-tiered disposition (Phase-1 quality hardening).** A *grounded* scene narrating an
    unsupported figure is a MINOR violation: ``check`` records it and the pipeline ships the scene
    flagged in ``degraded_scenes`` (the same 'publish anyway' path Gate B/D use) rather than losing
    the whole video. A framing-only scene smuggling a figure or comparison, or a scene citing a
    claim absent from the packet, is a MAJOR violation that still fails the job clean (no
    auto-repair — re-planning is the V6 regenerate path). A major anywhere in the contract fails the
    whole video; otherwise the minor violations are returned for the pipeline to fold into the
    artifact's provenance.

    Deterministic by design — no model call. The narrated script is the claim surface the spec's
    ``narration_claim_check_vs_sources`` gate names; visual-composition counts in ``objects`` (an
    "array of 8 cells") are not empirical claims and are not checked, and semantic comparison
    verification for grounded scenes is left to the planner's claim constraint.
    """

    def check(self, contract: VideoContract, packet: GroundingPacket) -> dict[str, list[str]]:
        """Diff every scene against the packet. Raise on the first MAJOR violation (the moat); else
        return ``{scene_id: [minor violation messages]}`` for the pipeline to flag in provenance."""
        violations = [v for scene in contract.scenes for v in self._check_scene(scene, packet)]
        major = next((v for v in violations if v.severity is _Severity.MAJOR), None)
        if major is not None:
            raise FactualGateError(
                major.scene_id, unsupported=major.unsupported, detail=major.message
            )
        degraded: dict[str, list[str]] = defaultdict(list)
        for violation in violations:
            degraded[violation.scene_id].append(violation.message)
        if degraded:
            _logger.info(
                "factual_gate.degraded", scenes=len(contract.scenes), flagged=len(degraded)
            )
        else:
            _logger.info("factual_gate.passed", scenes=len(contract.scenes))
        return dict(degraded)

    def _check_scene(self, scene: SceneContract, packet: GroundingPacket) -> list[_Violation]:
        narration = _scene_narration(scene)
        figures = _figures(narration)
        if scene.sources == [FRAMING_ONLY_SENTINEL]:
            return _framing_violations(scene, figures, narration)
        return _grounded_violations(scene, figures, packet)


def _framing_violations(
    scene: SceneContract, figures: set[str], narration: str
) -> list[_Violation]:
    # A framing-only scene asserts nothing, so any figure or comparison smuggles an empirical claim
    # into framing — MAJOR (the scene should never have carried it; re-plan, don't degrade).
    violations: list[_Violation] = []
    if figures:
        ordered = sorted(figures)
        violations.append(
            _Violation(
                scene.id,
                _Severity.MAJOR,
                f"framing-only scene states figures {ordered}",
                ordered,
            )
        )
    if _COMPARISON.search(narration):
        violations.append(
            _Violation(
                scene.id, _Severity.MAJOR, "framing-only scene makes an empirical comparison", []
            )
        )
    return violations


def _grounded_violations(
    scene: SceneContract, figures: set[str], packet: GroundingPacket
) -> list[_Violation]:
    supported, missing_claim = _supported_figures(scene, packet)
    if missing_claim is not None:
        # A cited claim absent from the packet leaves the gate no text to diff figures against, so
        # the scene is structurally ungrounded: a MAJOR violation (deny it, never allow any figure).
        return [
            _Violation(
                scene.id,
                _Severity.MAJOR,
                f"cites claim {missing_claim!r}, absent from the grounding packet",
                [],
            )
        ]
    smuggled = sorted(figures - supported)
    if smuggled:
        # The scene IS grounded; it just narrates an extra figure no cited claim proves — MINOR, so
        # the scene ships flagged in degraded_scenes rather than losing the whole video.
        return [
            _Violation(
                scene.id,
                _Severity.MINOR,
                f"states a figure no cited source verifies: {', '.join(smuggled)}",
                smuggled,
            )
        ]
    return []


# Beats can hide a smuggled figure the scene-level script omits — both surfaces are checked.
def _scene_narration(scene: SceneContract) -> str:
    return " ".join([scene.narration, *(beat.narration for beat in scene.beats)])


def _supported_figures(
    scene: SceneContract, packet: GroundingPacket
) -> tuple[set[str], str | None]:
    """The figures every cited claim proves, and the first cited claim id missing from the packet
    (``None`` when all resolve) — a missing claim is a structural defect the caller raises on."""
    supported: set[str] = set()
    for claim_id in scene.sources:
        claim = packet.by_id(claim_id)
        if claim is None:
            return supported, claim_id
        supported |= _figures(claim.text)
    return supported, None


def _figures(text: str) -> set[str]:
    return {_normalize_figure(token) for token in _FIGURE.findall(text)}


def _normalize_figure(token: str) -> str:
    return token.replace(",", "").rstrip("%")
