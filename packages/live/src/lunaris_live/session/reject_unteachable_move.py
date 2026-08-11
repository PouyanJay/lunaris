from typing import NoReturn

from .schema import MoveKind


def reject_unteachable_move(kind: MoveKind) -> NoReturn:
    """Refuse a move that is about the session rather than a concept.

    Shared by every tutor rather than written out in each, because it is one rule: CLOSE arrives
    with no ``node_id`` at all, so teaching whatever node was passed alongside it would be a bug
    that reads as a lesson. Two implementations each holding their own copy is how T1's owner check
    came to be wrong in one store and right in the other.
    """
    raise ValueError(f"{kind} is not a move a tutor teaches")
