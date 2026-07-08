import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id

from ..activity import ActivityStoreUnavailableError, LearningEvent
from ..dependencies import ActivityStoreDep, OptionalUserIdDep
from ..schemas import ActivityFeedItemView, ActivityStatsView, ActivityView

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


_UNAVAILABLE = "Activity is temporarily unavailable"


@router.get("", response_model=ActivityView)
async def get_activity(
    store: ActivityStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> ActivityView:
    """The caller's learning activity: streaks, study minutes, and the recent-events feed.

    A user with no history gets an honest all-zero snapshot — numbers derive only from real rows.
    An activity-backend outage is a recoverable 503 (kept inside the CORS middleware), never a
    raw 500.
    """
    response.headers["X-Request-Id"] = _bind()
    try:
        # minutes() is fetched (not yet folded into stats) so the walking skeleton proves BOTH
        # store read paths end-to-end; the aggregation task consumes it.
        events, _minutes = await asyncio.gather(
            store.events(user_id=owner_id),
            store.minutes(user_id=owner_id),
        )
    except ActivityStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNAVAILABLE
        ) from exc
    # Walking-skeleton derivation: the feed passes rows through; streak/heat/week math lands with
    # the aggregation task.
    stats = ActivityStatsView(
        current_streak=0, longest_streak=0, minutes_this_week=0, concepts_this_week=0
    )
    return ActivityView(stats=stats, feed=[_feed_item(event) for event in events])
