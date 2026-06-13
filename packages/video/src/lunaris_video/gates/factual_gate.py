import re

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


class FactualGate:
    """Gate C: the video can say only what the lesson's verified claims prove.

    Runs on the CONTRACT right after PLAN (factual content is static once planned, so checking the
    contract is equally correct and strictly cheaper than re-checking rendered frames — it catches
    a smuggled figure before any render compute). For each scene it diffs the numeric figures in
    the narration against the claims the scene cites: a grounded scene's figures must each appear
    in a cited claim, and a framing-only scene may carry no figure and no comparison at all. A
    violation fails the job clean (no auto-repair — re-planning is the V6 regenerate path); the gate
    is never loosened to let a scene through.

    Deterministic by design — no model call. The narrated script is the claim surface the spec's
    ``narration_claim_check_vs_sources`` gate names; visual-composition counts in ``objects`` (an
    "array of 8 cells") are not empirical claims and are not checked, and semantic comparison
    verification for grounded scenes is left to the planner's claim constraint.
    """

    def check(self, contract: VideoContract, packet: GroundingPacket) -> None:
        for scene in contract.scenes:
            self._check_scene(scene, packet)
        _logger.info("factual_gate.passed", scenes=len(contract.scenes))

    def _check_scene(self, scene: SceneContract, packet: GroundingPacket) -> None:
        narration = _scene_narration(scene)
        figures = _figures(narration)
        if scene.sources == [FRAMING_ONLY_SENTINEL]:
            _reject_figures_in_framing_scene(scene, figures)
            _reject_comparison_in_framing_scene(scene, narration)
            return
        smuggled = sorted(figures - _supported_figures(scene, packet))
        if smuggled:
            raise FactualGateError(
                scene.id,
                unsupported=smuggled,
                detail=f"narrates {smuggled} but no cited claim ({scene.sources}) supports it",
            )


def _reject_figures_in_framing_scene(scene: SceneContract, figures: set[str]) -> None:
    if figures:
        raise FactualGateError(
            scene.id,
            unsupported=sorted(figures),
            detail=f"framing-only scene states figures {sorted(figures)}",
        )


def _reject_comparison_in_framing_scene(scene: SceneContract, narration: str) -> None:
    if _COMPARISON.search(narration):
        raise FactualGateError(
            scene.id,
            unsupported=[],
            detail="framing-only scene makes an empirical comparison",
        )


# Beats can hide a smuggled figure the scene-level script omits — both surfaces are checked.
def _scene_narration(scene: SceneContract) -> str:
    return " ".join([scene.narration, *(beat.narration for beat in scene.beats)])


def _supported_figures(scene: SceneContract, packet: GroundingPacket) -> set[str]:
    supported: set[str] = set()
    for claim_id in scene.sources:
        claim = packet.by_id(claim_id)
        if claim is None:
            # A missing claim leaves the gate no text to diff figures against — the scene is
            # ungrounded, so deny it rather than silently allow any figure.
            raise FactualGateError(
                scene.id,
                unsupported=[],
                detail=f"cites claim {claim_id!r}, absent from the grounding packet",
            )
        supported |= _figures(claim.text)
    return supported


def _figures(text: str) -> set[str]:
    return {_normalize_figure(token) for token in _FIGURE.findall(text)}


def _normalize_figure(token: str) -> str:
    return token.replace(",", "").rstrip("%")
