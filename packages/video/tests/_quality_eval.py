"""The C4 quality-eval harness — the flywheel that makes scene quality measurable.

Test-support scaffolding (mirrors ``_stubs.py``), NOT a product surface: it drives the real video
pipeline over a fixed topic set and aggregates a structured ``QualityReport`` — per-topic and
aggregate produced / degraded / failed counts plus a degraded-scene rate — so a change to the
planner or the QA gates (C1/C2/C3) is judged against a number instead of prod-log spelunking.

The harness is decoupled from pipeline wiring by a ``produce`` thunk (``Produce``): it only knows
"run one topic → a ``RenderedVideo``, or raise". The hermetic ``test_quality_eval`` passes a stub
thunk so the aggregation stays green in CI; the key-gated live eval passes a thunk that drives the
real pipeline on live Claude (self-skips without keys). Metrics are read straight off the returned
bundle (``degraded_scenes`` + the scene count in ``contracts_json``) — no log scraping.
"""

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from lunaris_video.models import RenderedVideo


class QualityStatus(StrEnum):
    """How one topic came out of the pipeline. A degraded video still PRODUCED — it shipped a
    playable MP4 with best-effort scenes flagged — so it counts toward ``produced`` and, as a
    subset, ``degraded``. (``FAILED`` — the pipeline raised — is added in T2.)"""

    PRODUCED_CLEAN = "produced_clean"
    PRODUCED_DEGRADED = "produced_degraded"


@dataclass(frozen=True)
class TopicSpec:
    """One entry in the eval's fixed topic set: a stable id (the report key) and a human label."""

    id: str
    label: str


@dataclass(frozen=True)
class TopicResult:
    """How one topic scored: its status plus the scene counts the rate is computed from."""

    topic_id: str
    status: QualityStatus
    scene_count: int
    degraded_scene_count: int


@dataclass(frozen=True)
class QualityReport:
    """The aggregate of an eval run — the metric C1/C2/C3 move. Counts are derived properties over
    the per-topic results so the report cannot drift out of sync with them."""

    results: tuple[TopicResult, ...]

    @property
    def produced(self) -> int:
        """Topics that shipped a playable video (clean or degraded)."""
        return len(self.results)

    @property
    def degraded(self) -> int:
        """Produced videos carrying at least one best-effort (degraded) scene."""
        return sum(1 for result in self.results if result.status is QualityStatus.PRODUCED_DEGRADED)

    @property
    def total_scenes(self) -> int:
        return sum(result.scene_count for result in self.results)

    @property
    def degraded_scenes(self) -> int:
        return sum(result.degraded_scene_count for result in self.results)

    @property
    def degraded_scene_rate(self) -> float:
        """Degraded scenes / total scenes — the headline "how clean do scenes come out" number.
        Zero when no scenes were produced (an empty run is vacuously clean, not a zero-division)."""
        return self.degraded_scenes / self.total_scenes if self.total_scenes else 0.0


# The pipeline seam: run one topic and return its finished bundle (or raise a pipeline error). The
# harness stays ignorant of how the bundle is produced — a stub in CI, the real pipeline live.
Produce = Callable[[TopicSpec], Awaitable[RenderedVideo]]


class VideoQualityEval:
    """Runs every topic through ``produce`` and folds the bundles into a ``QualityReport``."""

    async def run(self, topics: Sequence[TopicSpec], produce: Produce) -> QualityReport:
        results = [await self._score(topic, produce) for topic in topics]
        return QualityReport(tuple(results))

    async def _score(self, topic: TopicSpec, produce: Produce) -> TopicResult:
        video = await produce(topic)
        degraded_count = len(video.degraded_scenes)
        status = QualityStatus.PRODUCED_DEGRADED if degraded_count else QualityStatus.PRODUCED_CLEAN
        return TopicResult(
            topic_id=topic.id,
            status=status,
            scene_count=_scene_count(video.contracts_json),
            degraded_scene_count=degraded_count,
        )


def _scene_count(contracts_json: bytes) -> int:
    """The number of scenes in a contract bundle, for both shapes: a flat ``SceneContracts``
    (``scenes``) and a chaptered ``ChapteredSceneContracts`` (``chapters`` each with ``scenes``)."""
    contract = json.loads(contracts_json)
    if "scenes" in contract:
        return len(contract["scenes"])
    return sum(len(chapter.get("scenes", ())) for chapter in contract.get("chapters", ()))
