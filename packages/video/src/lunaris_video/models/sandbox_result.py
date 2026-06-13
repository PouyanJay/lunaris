from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxResult:
    """What a sandboxed subprocess run came back with — bounded tails, never raw firehoses.

    ``timed_out`` is distinct from a nonzero ``returncode``: a hang and a crash repair
    differently (a hang usually means an animation loop, not an API error).
    """

    returncode: int
    stdout_tail: str
    stderr_tail: str
    timed_out: bool

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out
