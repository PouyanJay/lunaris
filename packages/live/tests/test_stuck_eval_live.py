"""The two T8 fixes, measured against a real tutor and a real grader (T10).

Everything else in this journey is deterministic and pinned offline. These two are judgements, and
a judgement can only be checked by making it:

1. **A session that cannot land a concept still gets somewhere.** The first real browser session
   spent six turns on concept one of about twenty. Offline, `_GIVE_UP_AFTER` is a number in a table;
   here it has to survive a real learner being genuinely and repeatedly wrong at a real grader.
2. **The grader does not punish a learner for following its own feedback.** The rule is monotonicity
   (T8/AD39): an answer that says everything an earlier one said, plus what it was told was missing,
   must never score lower. Offline this is a prompt string; only a live run says whether the model
   obeys it.

The assertions are on the trace and the verdicts, never on prose — one sample of a generative system
cannot support an assertion about how good an explanation reads. Same rule the P2a eval set.

Keyed and deselected, because it spends real money: one cold compile plus two short sessions.

    uv run --env-file .env pytest packages/live/tests/test_stuck_eval_live.py -m eval -q
"""

import json
import os
from pathlib import Path

import pytest
from lunaris_live.graph import ClaudeGraphCompiler, ConceptGraph
from lunaris_live.session import (
    ClaudeGrader,
    ClaudeTutor,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    SessionClock,
    SessionStatus,
    open_session,
    take_turn,
)
from lunaris_runtime.resilience import build_chat_model, retry_on_transient

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

_TOPIC = "How gradient descent trains a neural network"
_STRONG = "claude-opus-4-8"
_WORKER = "claude-haiku-4-5-20251001"
_BUDGET_S = 1800.0

#: Long enough for the give-up rule to fire (five pieces of evidence) and for the session to prove
#: it went somewhere afterwards. Bounded because every turn is three model calls.
_MAX_TURNS = 10

_DIGESTS = Path(".eval/live-stuck")


@pytest.fixture(scope="module")
async def compiled_map() -> ConceptGraph:
    """One real compile, shared by both runs. Real rather than hand-built: a graph written to suit
    the policy would quietly test the policy against its own notes."""
    return await ClaudeGraphCompiler(_STRONG).compile(_TOPIC, graph_id="eval-stuck", run_id="eval")


async def _says(prompt: str) -> str:
    client = build_chat_model(_WORKER, temperature=1.0)
    message = await retry_on_transient(
        lambda: client.ainvoke(prompt), max_attempts=3, max_delay_s=4.0
    )
    content = message.content
    return (content if isinstance(content, str) else str(content)).strip() or "I'm not sure."


async def test_a_learner_who_cannot_land_one_concept_still_reaches_another(
    compiled_map: ConceptGraph,
) -> None:
    """The defect the user actually sat through, measured end to end.

    A learner who is wrong every single time must not be held on one concept for the whole session.
    Either the session moves on to a different concept, or it closes saying the concept is being
    left for another day. What it must NOT do is ask about the same node ten times running.
    """
    # Arrange
    tutor, grader = ClaudeTutor(_STRONG), ClaudeGrader(_WORKER)
    session = (
        await open_session(
            compiled_map,
            LearnerModel(graph_id=compiled_map.graph_id),
            SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
            session_id="eval-stuck",
            run_id="eval-stuck-1",
            tutor=tutor,
        )
    ).session
    model = LearnerModel(graph_id=compiled_map.graph_id)
    touched: list[str | None] = [session.turns[0].move.node_id]

    # Act
    for turn in range(2, _MAX_TURNS + 1):
        head = session.turns[-1]
        said = await _says(
            "You are a learner who is completely lost in this subject and nothing is landing. "
            f'Your tutor just said:\n"{head.tutor}"\n\n'
            "Answer briefly, vaguely and WRONGLY — guess, or describe something unrelated. Never "
            "give a correct or complete answer. Two sentences at most, in a normal voice. Write "
            "ONLY your reply."
        )
        outcome = await take_turn(
            session,
            compiled_map,
            model,
            answer=said,
            answering_seq=head.seq,
            grader=grader,
            tutor=tutor,
            run_id=f"eval-stuck-{turn}",
            elapsed_s=float(turn) * 60.0,
            budget_s=_BUDGET_S,
        )
        session, model = outcome.session, outcome.model
        touched.append(session.turns[-1].move.node_id)
        if session.status is SessionStatus.CLOSED:
            break

    _write_digest("stuck", session, model, touched)

    # Assert
    taught = [node for node in touched if node is not None]
    moved_on = len(set(taught)) > 1
    closed_deliberately = session.turns[-1].move.kind is MoveKind.CLOSE
    assert moved_on or closed_deliberately, (
        f"a learner who cannot land one concept was held on it for the whole session: {touched}"
    )


async def test_adding_what_the_grader_asked_for_never_scores_lower(
    compiled_map: ConceptGraph,
) -> None:
    """Monotonicity, against the real grader.

    The learner answers thinly, reads the verdict, then answers again saying everything they said
    before *plus* whatever the feedback named as missing. The second verdict must not be worse than
    the first. This is the rule the first real session broke: an answer was told it lacked "adjusts
    many small numbers", said exactly that next time, and was marked down.
    """
    # Arrange
    tutor, grader = ClaudeTutor(_STRONG), ClaudeGrader(_WORKER)
    session = (
        await open_session(
            compiled_map,
            LearnerModel(graph_id=compiled_map.graph_id),
            SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
            session_id="eval-monotonic",
            run_id="eval-monotonic-1",
            tutor=tutor,
        )
    ).session
    model = LearnerModel(graph_id=compiled_map.graph_id)
    head = session.turns[-1]

    thin = await _says(
        "You are a learner having a first go at explaining something you half understand. "
        f'Your tutor just said:\n"{head.tutor}"\n\n'
        f'They asked you to: "{head.criterion.statement if head.criterion else ""}"\n\n'
        "Give a SHORT, partial answer: the general shape of the idea with the mechanism left out. "
        "Two sentences. Write ONLY your reply."
    )

    # Act: first attempt.
    first = await take_turn(
        session,
        compiled_map,
        model,
        answer=thin,
        answering_seq=head.seq,
        grader=grader,
        tutor=tutor,
        run_id="eval-monotonic-2",
        elapsed_s=60.0,
        budget_s=_BUDGET_S,
    )
    session, model = first.session, first.model
    graded_first = session.turns[-2].grade
    assert graded_first is not None, "the first attempt was not graded, so there is nothing to test"

    # The learner does the thing feedback exists for: keeps what they said and adds what was named.
    fuller = await _says(
        "You are the same learner, answering again. This is what you said last time:\n"
        f'"{thin}"\n\nThis is what you were told:\n"{graded_first.reason}"\n\n'
        "Write a new answer that says EVERYTHING you said before, plus exactly what the feedback "
        "says was missing. Do not drop anything. Three or four sentences. Write ONLY your reply."
    )
    head = session.turns[-1]
    second = await take_turn(
        session,
        compiled_map,
        model,
        answer=fuller,
        answering_seq=head.seq,
        grader=grader,
        tutor=tutor,
        run_id="eval-monotonic-3",
        elapsed_s=120.0,
        budget_s=_BUDGET_S,
    )
    session, model = second.session, second.model
    graded_second = session.turns[-2].grade
    assert graded_second is not None

    _write_digest("monotonic", session, model, [thin, graded_first.reason, fuller])

    # Assert: never worse than before. MET > PARTIAL > NOT_MET.
    rank = {EvidenceKind.NOT_MET: 0, EvidenceKind.PARTIAL: 1, EvidenceKind.MET: 2}
    assert rank[graded_second.kind] >= rank[graded_first.kind], (
        f"following the feedback scored lower: {graded_first.kind.value} → "
        f"{graded_second.kind.value}\nfirst: {thin}\nfeedback: {graded_first.reason}\n"
        f"second: {fuller}\nverdict: {graded_second.reason}"
    )


def _write_digest(name: str, session: object, model: object, extra: list) -> None:
    """Leave the run on disk for a human to read. Gitignored, like every other eval digest: the
    assertions say whether the shape held, and only a person can say whether it taught well."""
    _DIGESTS.mkdir(parents=True, exist_ok=True)
    (_DIGESTS / f"{name}.json").write_text(
        json.dumps(
            {
                "session": session.model_dump(mode="json", by_alias=True),  # type: ignore[attr-defined]
                "model": model.model_dump(mode="json", by_alias=True),  # type: ignore[attr-defined]
                "notes": extra,
            },
            indent=2,
        )
    )
