from pydantic import BaseModel, ConfigDict, HttpUrl


class MediaUrl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    url: HttpUrl
