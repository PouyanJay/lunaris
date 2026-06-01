"""A tiny shared holder for the pipeline phase currently in progress.

The coarse ``ProgressReporter`` and the fine-grained ``AgentReporter`` are independent emitters, but
the live timeline needs each fine event bucketed under the phase active when it fired. Rather than
couple the two reporters, the runner creates one ``StageCursor`` per run and hands it to both:
``ProgressReporter`` advances it at each stage boundary, ``AgentReporter`` reads it to stamp every
``AgentEvent.stage``. ``current`` is ``None`` until the first stage is reported (the "intro" beats).
"""

from lunaris_runtime.schema import ProgressStage


class StageCursor:
    """Holds the latest reported ``ProgressStage`` for a run; shared across its two reporters."""

    def __init__(self) -> None:
        self.current: ProgressStage | None = None

    def advance(self, stage: ProgressStage) -> None:
        self.current = stage
