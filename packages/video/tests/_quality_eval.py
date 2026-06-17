"""The C4 quality-eval harness — the flywheel that makes scene quality measurable.

Test-support scaffolding (mirrors ``_stubs.py``), NOT a product surface: it drives the real video
pipeline over a fixed topic set and aggregates a structured ``QualityReport`` — per-topic and
aggregate produced / degraded / failed counts, the per-gate degrade histogram, and a degraded-scene
rate — so a change to the planner or the QA gates (C1/C2/C3) is judged against a number instead of
prod-log spelunking.

The harness is decoupled from pipeline wiring by a ``produce`` thunk (``Produce``): it only knows
"run one topic → a ``RenderedVideo``, or raise". The hermetic ``test_quality_eval`` passes a stub
thunk so the aggregation stays green in CI; the key-gated live eval passes a thunk that drives the
real pipeline on live Claude (self-skips without keys).

Where the numbers come from:
- produced / degraded / scene counts → straight off the returned ``RenderedVideo`` bundle.
- failures → the raised exception, bucketed by ``VideoFailureKind.classify`` — the SAME classifier
  the worker logs, so a measured failure is taxonomised exactly as a prod failure would be.
- the per-gate {visual, sync, factual} degrade split → captured off the pipeline's
  ``video_pipeline.produced`` telemetry event (E1 / ``video-observability.md``), since the bundle's
  ``DegradedScene.issues`` flatten the gate source away.
"""

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from lunaris_video.models import RenderedVideo
from lunaris_video.worker.failure_taxonomy import VideoFailureKind
from structlog.testing import capture_logs

# The pipeline's quality-telemetry event and the key carrying its per-gate degrade histogram. The
# harness reads these rather than re-deriving the split, so C4 and the worker share one source.
_PRODUCED_EVENT = "video_pipeline.produced"
_DEGRADED_BY_KIND = "degraded_by_kind"


class QualityStatus(StrEnum):
    """How one topic came out of the pipeline. A degraded video still PRODUCED — it shipped a
    playable MP4 with best-effort scenes flagged — so it counts toward ``produced`` and, as a
    subset, ``degraded``. ``FAILED`` means the pipeline raised (no video shipped)."""

    PRODUCED_CLEAN = "produced_clean"
    PRODUCED_DEGRADED = "produced_degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class TopicSpec:
    """One entry in the eval's fixed topic set: a stable id (the report key) and a human label."""

    id: str
    label: str


@dataclass(frozen=True)
class TopicResult:
    """How one topic scored: its status, the scene counts the rate is computed from, the per-gate
    degrade histogram (produced topics), and the failure kind (failed topics)."""

    topic_id: str
    status: QualityStatus
    scene_count: int
    degraded_scene_count: int
    degraded_by_kind: Mapping[str, int] = field(default_factory=dict)
    failure_kind: VideoFailureKind | None = None


@dataclass(frozen=True)
class QualityReport:
    """The aggregate of an eval run — the metric C1/C2/C3 move. Counts are derived properties over
    the per-topic results so the report cannot drift out of sync with them."""

    results: tuple[TopicResult, ...]

    @property
    def produced(self) -> int:
        """Topics that shipped a playable video (clean or degraded) — failures excluded."""
        return sum(1 for result in self.results if result.status is not QualityStatus.FAILED)

    @property
    def degraded(self) -> int:
        """Produced videos carrying at least one best-effort (degraded) scene."""
        return sum(1 for result in self.results if result.status is QualityStatus.PRODUCED_DEGRADED)

    @property
    def failed(self) -> int:
        """Topics the pipeline could not ship a video for (it raised)."""
        return sum(1 for result in self.results if result.status is QualityStatus.FAILED)

    @property
    def failure_rate(self) -> float:
        """Failed topics / all topics. Zero for an empty run (not a zero-division)."""
        return self.failed / len(self.results) if self.results else 0.0

    @property
    def total_scenes(self) -> int:
        # Failed topics contribute no scenes, so they never dilute the degraded-scene rate.
        return sum(result.scene_count for result in self.results)

    @property
    def degraded_scenes(self) -> int:
        return sum(result.degraded_scene_count for result in self.results)

    @property
    def degraded_scene_rate(self) -> float:
        """Degraded scenes / total scenes — the headline "how clean do scenes come out" number.
        Zero when no scenes were produced (an empty run is vacuously clean, not a zero-division)."""
        return self.degraded_scenes / self.total_scenes if self.total_scenes else 0.0

    @property
    def failures_by_kind(self) -> dict[str, int]:
        """The failure taxonomy histogram: ``VideoFailureKind`` value → count."""
        histogram: dict[str, int] = {}
        for result in self.results:
            if result.failure_kind is not None:
                kind = result.failure_kind.value
                histogram[kind] = histogram.get(kind, 0) + 1
        return histogram

    @property
    def degraded_by_kind(self) -> dict[str, int]:
        """The per-gate degrade histogram summed across produced topics: gate source → issue count
        (e.g. ``{"visual": 5, "sync": 2, "factual": 1}``) — tells whether C2 (visual) or C3 (sync)
        is where the degradation lives."""
        histogram: dict[str, int] = {}
        for result in self.results:
            for kind, count in result.degraded_by_kind.items():
                histogram[kind] = histogram.get(kind, 0) + count
        return histogram

    def meets_ceiling(self, *, max_degraded_scene_rate: float, max_failures: int = 0) -> bool:
        """The regression gate: the run is acceptable iff at most ``max_failures`` topics failed AND
        the degraded-scene rate is at or under ``max_degraded_scene_rate``. The live eval asserts
        this so a quality regression (more degraded scenes, or a new hard-fail) fails CI."""
        return self.failed <= max_failures and self.degraded_scene_rate <= max_degraded_scene_rate


# The pipeline seam: run one topic and return its finished bundle (or raise a pipeline error). The
# harness stays ignorant of how the bundle is produced — a stub in CI, the real pipeline live.
Produce = Callable[[TopicSpec], Awaitable[RenderedVideo]]


class VideoQualityEval:
    """Runs every topic through ``produce`` and folds the bundles into a ``QualityReport``."""

    async def run(self, topics: Sequence[TopicSpec], produce: Produce) -> QualityReport:
        # Sequential on purpose: a live run drives one shared pipeline and saturates Claude's
        # process rate limiter anyway, so fanning out buys little and would interleave the per-topic
        # log capture (the `produced` telemetry read) across topics. A nightly eval is latency-OK.
        results = [await self._score(topic, produce) for topic in topics]
        return QualityReport(tuple(results))

    async def _score(self, topic: TopicSpec, produce: Produce) -> TopicResult:
        # Capture the pipeline's telemetry for THIS topic so the per-gate degrade split is read off
        # the authoritative `produced` event. A raise (any exception, mirroring the worker's broad
        # catch) is a FAILED topic, bucketed by the shared taxonomy — the run never aborts mid-set.
        with capture_logs() as events:
            try:
                video = await produce(topic)
            except Exception as exc:
                return TopicResult(
                    topic_id=topic.id,
                    status=QualityStatus.FAILED,
                    scene_count=0,
                    degraded_scene_count=0,
                    failure_kind=VideoFailureKind.classify(exc),
                )
        degraded_count = len(video.degraded_scenes)
        status = QualityStatus.PRODUCED_DEGRADED if degraded_count else QualityStatus.PRODUCED_CLEAN
        return TopicResult(
            topic_id=topic.id,
            status=status,
            scene_count=_scene_count(video.contracts_json),
            degraded_scene_count=degraded_count,
            degraded_by_kind=_degraded_by_kind(events),
        )


def _degraded_by_kind(events: list[dict[str, object]]) -> dict[str, int]:
    """The per-gate degrade histogram off the most recent ``video_pipeline.produced`` event in this
    topic's captured logs (the last one wins if a fresh-take re-plan produced more than one), or an
    empty dict if the pipeline emitted none."""
    for event in reversed(events):
        if event.get("event") == _PRODUCED_EVENT:
            histogram = event.get(_DEGRADED_BY_KIND)
            if isinstance(histogram, Mapping):
                return {str(kind): int(count) for kind, count in histogram.items()}
    return {}


def _scene_count(contracts_json: bytes) -> int:
    """The number of scenes in a contract bundle, for both shapes: a flat ``SceneContracts``
    (``scenes``) and a chaptered ``ChapteredSceneContracts`` (``chapters`` each with ``scenes``)."""
    contract = json.loads(contracts_json)
    if "scenes" in contract:
        return len(contract["scenes"])
    return sum(len(chapter.get("scenes", ())) for chapter in contract.get("chapters", ()))
