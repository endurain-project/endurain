"""OneLapFit request/response schemas."""

from pydantic import BaseModel


class OneLapFitClient(BaseModel):
    """OneLapFit client credentials request schema."""

    email: str
    password: str
