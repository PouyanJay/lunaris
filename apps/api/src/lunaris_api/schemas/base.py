from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for API wire models: camelCase aliases on the wire, populatable by field name."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
