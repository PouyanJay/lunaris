from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LiveModel(BaseModel):
    """Base for every Lunaris Live contract entity.

    Python fields are snake_case; the persisted and wire JSON is camelCase (the TypeScript
    contract the web consumes). Deliberately Live's own base rather than Studio's ``CourseModel``:
    the concept graph is Live's internal contract (plan §2), and sharing a base class is the first
    step towards sharing a schema.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )
