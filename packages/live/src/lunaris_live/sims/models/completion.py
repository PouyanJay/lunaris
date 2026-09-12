from dataclasses import dataclass


@dataclass(frozen=True)
class SimCompletion:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
