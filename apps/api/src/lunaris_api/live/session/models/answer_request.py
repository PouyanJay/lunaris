from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerRequest:
    answer: str
    answering_seq: int
    run_id: str
    owner_id: str | None
