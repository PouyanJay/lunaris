"""The pieces a Live API test composes its stack from, once.

A held compile (a rendezvous, never a sleep), the body the Node runtime posts for one AG-UI answer,
and the settings every suite starts from. One place because a rendezvous primitive is the kind of
thing that should only have to be got right once (``_agui_frames`` says the same of frame reading):
two copies of ``GatedCompiler`` had already drifted (one filtered by topic, one did not) before
this existed (P2c T8, found in review).
"""

import asyncio
from pathlib import Path

from lunaris_api.config import Settings
from lunaris_live.graph import ConceptGraph, StubGraphCompiler


class GatedCompiler:
    """The stub compiler, held at the door until the test lets it through.

    Holds every compile, or only those of ``held_topic`` when one is named. A rendezvous rather than
    a sleep: an answer sent while ``entered`` is set and ``release`` is not is an answer sent
    *during* the compile, whatever the machine's speed. Found in review: the first version of the
    placement tests answered after a stub compile that had already landed, so it never exercised
    the window it claimed to.
    """

    def __init__(self, held_topic: str | None = None) -> None:
        self.held_topic = held_topic
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._inner = StubGraphCompiler()

    async def compile(self, topic: str, **kwargs: object) -> ConceptGraph:
        if self.held_topic is None or topic == self.held_topic:
            self.entered.set()
            await asyncio.wait_for(self.release.wait(), 5)
        return await self._inner.compile(topic, **kwargs)  # type: ignore[arg-type]

    async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
        raise NotImplementedError


def settings_for(tmp_path: Path, **overrides: object) -> Settings:
    """The offline stack's settings: the stub pipeline, nothing else configured, plus overrides."""
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        **overrides,  # type: ignore[arg-type]
    )


def agui_answer(text: str, *, run_id: str = "r1") -> dict:
    """The body the Node runtime POSTs for one run answering with ``text``."""
    return {
        "threadId": "t",
        "runId": run_id,
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
