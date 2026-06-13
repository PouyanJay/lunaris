"""Shared test double for the package's ``invoke: Callable[[str], Awaitable[str]]`` model seam.

Records every prompt it is sent (so parse-repair tests can assert repair-turn content) and
replays scripted replies, REPEATING the last reply once the script is exhausted — that is what
lets a single bad reply drive a "exhaust the repair budget" test without listing it N times.
"""


class StubInvokeModel:
    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self._replies = replies

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        call_index = len(self.prompts) - 1
        return self._replies[min(call_index, len(self._replies) - 1)]
