from dataclasses import dataclass


@dataclass(frozen=True)
class LeaseSweepResult:
    """What one lease-timeout sweep recovered (explainer-video V7-T4): how many stale in-flight jobs
    were requeued for a fresh claim, and how many were dead-lettered (failed) for exhausting their
    attempts. The worker logs both so a recovery is visible in the run's structured logs."""

    requeued: int
    dead_lettered: int
