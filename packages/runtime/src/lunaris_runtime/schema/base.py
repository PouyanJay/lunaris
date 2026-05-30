from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CourseModel(BaseModel):
    """Base for every course-object entity.

    Python fields are snake_case; the persisted JSON is camelCase (the TypeScript
    contract the web consumes). `populate_by_name` lets us construct with either.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )
