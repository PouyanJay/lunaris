class ProdPowerStateUnavailableError(Exception):
    """Azure did not answer the power-state read (a resource read failed or came back malformed).

    Raised for a plain read, and also after a start/stop whose actions were all sent: the change is
    under way, only its outcome could not be read back."""
