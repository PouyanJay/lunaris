class GraderUnavailableError(RuntimeError):
    """The answer could not be scored, so no evidence exists about it.

    Never a default verdict. Reading a failure as NOT_MET would have an outage teach the system
    that the learner does not understand the concept — and the director gates progress on exactly
    that belief, so a bad minute for the provider would cost the learner a remediation loop. An
    ungraded answer leaves the model untouched instead.
    """
