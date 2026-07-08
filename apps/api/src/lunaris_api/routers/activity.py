import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..activity import (
    ActivitySnapshot,
    ActivityStoreUnavailableError,
    LearningEvent,
    derive_activity,
)
from ..dependencies import ActivityStoreDep, OptionalUserIdDep
from ..schemas import (
    ActivityFeedItemView,
    ActivityStatsView,
    ActivityView,
    HeatDayView,
    WeekDayView,
)

router = APIRouter(prefix="/api/activity", tags=["activity"])


def _bind() -> str:
    """Bind a fresh correlation id for the request and return it (for the X-Request-Id header)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    return request_id


def _feed_item(event: LearningEvent) -> ActivityFeedItemView:
    return ActivityFeedItemView(
        event_type=event.event_type,
        course_id=event.course_id,
        course_title=event.course_title,
        lesson_id=event.lesson_id,
        lesson_title=event.lesson_title,
        kc_id=event.kc_id,
        kc_label=event.kc_label,
        occurred_at=event.occurred_at,
    )


def _view(snapshot: ActivitySnapshot) -> ActivityView:
    return ActivityView(
        stats=ActivityStatsView(
            current_streak=snapshot.current_streak,
            longest_streak=snapshot.longest_streak,
            minutes_this_week=snapshot.minutes_this_week,
            concepts_this_week=snapshot.concepts_this_week,
        ),
        heat=[
            HeatDayView(date=day.date, minutes=day.minutes, active=day.active)
            for day in snapshot.heat
        ],
        week=[WeekDayView(date=day.date, minutes=day.minutes) for day in snapshot.week],
        feed=[_feed_item(event) for event in snapshot.feed],
    )


def _zone_or_422(tz: str, request_id: str) -> ZoneInfo:
    """Resolve the viewer's IANA zone; an unknown name is the caller's error, not a server 500."""
    try:
        return ZoneInfo(tz)
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown timezone: {tz!r}",
            headers={"X-Request-Id": request_id},
        ) from exc


_UNAVAILABLE = "Activity is temporarily unavailable"


def _unavailable(request_id: str) -> HTTPException:
    """The recoverable-outage 503. Correlation must ride the exception explicitly — headers set
    on the injected Response are dropped when a handler raises."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_UNAVAILABLE,
        headers={"X-Request-Id": request_id},
    )


@router.get("", response_model=ActivityView)
async def get_activity(
    store: ActivityStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
    tz: str = "UTC",
) -> ActivityView:
    """The caller's learning activity: streaks, study minutes, 14-day heat, week bars, and the
    recent-events feed — all derived per read from real telemetry rows, in the viewer's timezone
    (``tz``, an IANA name; day boundaries and "this week" are user-local).

    A user with no history gets an honest all-zero snapshot — numbers derive only from real rows.
    An activity-backend outage is a recoverable 503 (kept inside the CORS middleware), never a
    raw 500.
    """
    request_id = _bind()
    response.headers["X-Request-Id"] = request_id
    zone = _zone_or_422(tz, request_id)
    try:
        events, minutes = await asyncio.gather(
            store.events(user_id=owner_id),
            store.minutes(user_id=owner_id),
        )
    except ActivityStoreUnavailableError as exc:
        raise _unavailable(request_id) from exc
    snapshot = derive_activity(events, minutes, tz=zone, now=datetime.now(UTC))
    return _view(snapshot)


@router.put("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def put_heartbeat(
    store: ActivityStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> None:
    """The reader's study-minutes heartbeat: upsert the current minute bucket (idempotent — beats
    within one minute collapse to one row). The client sends no payload; the server stamps the
    bucket, so a skewed client clock can't fabricate history. Deliberately coarse: the bucket
    carries no course/lesson refs (privacy — it records "was studying", nothing else)."""
    request_id = _bind()
    response.headers["X-Request-Id"] = request_id
    bucket_start = datetime.now(UTC).replace(second=0, microsecond=0)
    try:
        await store.record_minute(user_id=owner_id, bucket_start=bucket_start)
    except ActivityStoreUnavailableError as exc:
        raise _unavailable(request_id) from exc
