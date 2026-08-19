from collections.abc import Iterable

from .schema import InterviewExchange, MoveKind, SessionTurn


def exchanges_of(turns: Iterable[SessionTurn]) -> list[InterviewExchange]:
    """What the placement interview has asked and been answered, oldest first: every interview
    turn with an answer. One reader of that rule (the loop asks the interviewer with it, the mapper
    is placed by it), so the two cannot come to disagree about what "the interview" was."""
    return [
        InterviewExchange(question=turn.tutor, answer=turn.answer)
        for turn in turns
        if turn.move.kind is MoveKind.PLACE and turn.answer is not None
    ]
