class StaleAnswerError(RuntimeError):
    """An answer arrived for a turn the session has already moved past.

    A learner pressing send twice, or a second tab answering while the first was still open.
    Left unguarded the duplicate is graded against the *next* question: the words are recorded
    under a criterion they were never written for, and the belief that moves is about the wrong
    concept — which the transcript then reports as though the learner had said it in reply to
    that question.

    Not the learner doing anything wrong: they answered the thing they were shown. The session
    simply is not there any more.
    """
