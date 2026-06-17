class InvalidInviteCodeError(ValueError):
    """The invite code an admin tried to set is empty, too long, or contains control characters."""
