from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusMediaRequest:
    session_id: str
    asset_id: str
    turn: int
    owner_id: str
    run_id: str
