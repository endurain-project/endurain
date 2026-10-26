"""Strava request shapes."""

from pydantic import BaseModel


class StravaClient(BaseModel):
    """A user's Strava API application credentials."""

    client_id: int | None
    client_secret: str | None


class StravaDetail(BaseModel):
    """The outcome of a Strava account or sync request."""

    detail: str
