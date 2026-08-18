from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RunProps(BaseModel):
    """What a client may say about a run beyond its messages, read out of ``forwardedProps``.

    AG-UI's ``RunAgentInput`` is CopilotKit's own schema, and ``forwardedProps`` is the one field it
    leaves untyped for the application, the kit sends whatever the browser put in
    ``<CopilotKit properties>`` there on every run. This is the typed reading of it, and it exists
    for one thing (P2b T9): letting a browser name the turn it is answering, so a late answer to a
    card the thread still shows is refused (409, as REST refuses it) rather than graded against
    whatever question is up now.

    Validated at the door like every other input, but *lenient about company*: the kit puts its
    own keys beside ours (``a2uiCatalogAvailable``, an ``a2uiAction`` while one is in flight), so
    unknown keys are ignored rather than refused. What is ours has to be well-formed, a seq that
    is not a positive integer is a bad request, not a guess.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    #: The turn the learner was answering, or ``None`` when the client did not say, every AG-UI
    #: client written before T9, and a bare reload, in which case the standing turn is meant.
    answering_seq: int | None = Field(default=None, ge=1)

    @classmethod
    def of(cls, forwarded_props: Any) -> "RunProps":
        """The props of a run, from the untyped field. Anything that is not a mapping carries
        nothing of ours and reads as an empty one; a mapping with a malformed value raises
        ``ValidationError``, which the router answers as a 422."""
        return cls.model_validate(forwarded_props if isinstance(forwarded_props, dict) else {})
