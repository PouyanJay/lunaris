from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SecretStatusView(_CamelModel):
    """What the API reveals about one secret — set/unset + last 4 chars, never the value."""

    name: str
    is_set: bool
    last4: str | None


class SettingsView(_CamelModel):
    """The settings surface: per-secret status + the current (read-only) pipeline mode."""

    secrets: list[SecretStatusView]
    pipeline: str
    # Whether the active pipeline can re-author a single lesson; the web hides the regenerate
    # action when False rather than offering a button the pipeline would reject with a 501.
    supports_lesson_regeneration: bool


class SecretValue(BaseModel):
    """Request body for setting a secret. ``SecretStr`` keeps the value out of logs/reprs."""

    value: SecretStr
