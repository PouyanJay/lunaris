class ProdPowerActionError(Exception):
    """Azure refused the start/stop of some governed resources. Every other resource was still
    attempted, so production may be partly changed; ``failed`` names the ones that were refused."""

    def __init__(self, *, on: bool, failed: tuple[str, ...]) -> None:
        self.on = on
        self.failed = failed
        verb = "start" if on else "stop"
        super().__init__(f"Could not {verb}: {', '.join(failed)}")
