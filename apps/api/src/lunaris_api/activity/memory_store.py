from datetime import datetime

from .learning_event import LearningEvent


class InMemoryActivityStore:
    """The no-DB activity store (offline dev / hermetic tests): plain lists keyed by user.

    ``None`` user_id is the single-user posture — all unauthenticated telemetry shares one bucket,
    mirroring the progress store when auth is off. Process-lifetime only.
    """

    def __init__(self) -> None:
        self._events: dict[str | None, list[LearningEvent]] = {}
        self._minutes: dict[str | None, dict[datetime, None]] = {}

    async def record_event(self, *, user_id: str | None, event: LearningEvent) -> None:
        self._events.setdefault(user_id, []).append(event)

    async def record_minute(self, *, user_id: str | None, bucket_start: datetime) -> None:
        # Dict-as-set keyed by bucket: repeated heartbeats within one minute stay one entry.
        self._minutes.setdefault(user_id, {})[bucket_start] = None

    async def events(self, *, user_id: str | None) -> list[LearningEvent]:
        # Newest-first, with insertion order breaking timestamp ties — wall-clock alone can tie
        # at coarse clock resolution and silently flip the feed order.
        indexed = list(enumerate(self._events.get(user_id, [])))
        indexed.sort(key=lambda pair: (pair[1].occurred_at, pair[0]), reverse=True)
        return [event for _, event in indexed]

    async def minutes(self, *, user_id: str | None) -> list[datetime]:
        return list(self._minutes.get(user_id, {}))
