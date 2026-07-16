from pydantic import BaseModel


class StravaClient(BaseModel):
    client_id: int | None
    client_secret: str | None
