from lunaris_runtime.schema import Clarifier, CourseBrief

from .base import CamelModel


class BriefResponse(CamelModel):
    """Phase-1 response for the interpret clarifier (P7.5): the inferred brief + the questions.

    The web renders the questions (each pre-picking the inference) so the learner can confirm or
    adjust before building; the confirmed answers come back as a ``clarification`` on the build
    request. The brief here is informational — the authoritative brief is re-interpreted on build.
    """

    brief: CourseBrief
    clarifier: Clarifier
