class TutorUnavailableError(RuntimeError):
    """The tutor could not say anything, so the turn did not happen.

    Deliberately not a degraded turn taught from the concept's definition. A session that quietly
    fell back would look to the learner model like teaching that landed badly, and to anyone reading
    the transcript like a tutor doing a poor job — when what actually happened is that nobody taught
    anything. The distinction survives only if the failure stays a failure.

    Retryable in principle: the provider being down is a state that ends.
    """
