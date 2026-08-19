from datetime import datetime


def review_day(due_at: datetime) -> str:
    """A review's day as the learner is told it: "Thursday 20 August" (P2c T6). The day, never the
    time: the ladder is measured in days, and a minute would promise a precision it does not have.
    """
    return f"{due_at:%A} {due_at.day} {due_at:%B}"
