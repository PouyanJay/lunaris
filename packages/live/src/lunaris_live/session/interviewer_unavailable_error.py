class InterviewerUnavailableError(RuntimeError):
    """The interviewer could not produce its next question: the provider was down, timed out, or
    answered with something no learner could be asked.

    Distinct from ``TutorUnavailableError`` because the loop degrades it differently: an interview
    is a nicety in front of the compile, so a question that cannot be asked ends the interview
    (the learner's answer is kept) rather than failing the turn. A lesson that cannot be taught
    fails the turn, because a turn with no words is not a turn.
    """
