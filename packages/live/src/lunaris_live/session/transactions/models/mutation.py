from dataclasses import dataclass

from ...schema import LearnerModel, Session


@dataclass(frozen=True)
class SessionMutation:
    session: Session | None = None
    knowledge: LearnerModel | None = None
    expected_turns: int | None = None
    create: bool = False
    delete_session: str | None = None
    forget: bool = False
