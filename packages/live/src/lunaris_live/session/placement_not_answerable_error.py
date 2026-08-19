class PlacementNotAnswerableError(RuntimeError):
    """The session is still placing, and this build cannot take an interview answer yet.

    P2c T1 opens a session on a topic and asks the first question; T2 is what reads the answer.
    Until then the honest refusal is this one, not the closed-session refusal a placing session
    would otherwise fall into — a learner told their session "has already ended" one question in
    would be told something false. T2 removes this error along with the guard that raises it.
    """
