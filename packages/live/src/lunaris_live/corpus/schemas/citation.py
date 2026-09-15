from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, field_validator

from .base import CorpusModel


class CorpusCitation(CorpusModel):
    id: str = Field(min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=2000)
    url: str | None = Field(default=None, max_length=4000)
    snippet: str | None = Field(default=None, max_length=20000)
    trust_tier: str | None = Field(default=None, max_length=100)
    credibility: float | None = Field(default=None, ge=0, le=1)
    source_type: str | None = Field(default=None, max_length=100)
    fetched_at: str | None = Field(default=None, max_length=100)

    @field_validator("url")
    @classmethod
    def validate_link(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        credential_fields = {"token", "key", "api_key", "apikey", "signature", "sig"}
        query_keys = {key.lower() for key, _ in parse_qsl(parsed.query)}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(
                key in credential_fields
                or any(part in key for part in ("token", "secret", "password"))
                or key.startswith(("x-amz-", "x-goog-"))
                for key in query_keys
            )
            or any(char.isspace() for char in value)
        ):
            raise ValueError("Source citation must be a public HTTP(S) reference")
        return value
