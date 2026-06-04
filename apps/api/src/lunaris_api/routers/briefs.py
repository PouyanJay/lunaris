from uuid import uuid4

from fastapi import APIRouter, Response
from lunaris_runtime.clarifier import build_clarifier
from lunaris_runtime.logging import bind_request_id

from ..dependencies import GoalInterpreterDep
from ..schemas import BriefResponse, CourseRequest

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


@router.post("", response_model=BriefResponse)
async def interpret_brief(
    payload: CourseRequest, interpreter: GoalInterpreterDep, response: Response
) -> BriefResponse:
    """Interpret a topic into a brief and derive the opt-in confirm clarifier (P7.5, phase 1).

    The web shows the questions — each pre-picking the interpreter's inference — so the learner can
    confirm or adjust before building; the confirmed answers ride the build request as a
    ``clarification``. With no model key the interpreter falls back to a topic-derived default, so
    the clarifier still renders. (``CourseRequest`` is reused for the topic; any ``clarification``
    on it is ignored here — this stage makes the questions, not the answers.)

    A ``request_id`` is bound + returned in ``X-Request-Id`` so an interpreter failure is traceable
    across the structured logs (this endpoint calls the live model when a key is present).
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    brief = await interpreter.interpret(payload.topic)
    return BriefResponse(brief=brief, clarifier=build_clarifier(brief))
