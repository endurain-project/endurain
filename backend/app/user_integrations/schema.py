from pydantic import BaseModel


class UserIntegrations(BaseModel):
    id: int
    user_id: int
    strava_state: str | None = None
    strava_token: str | None = None
    strava_refresh_token: str | None = None
    strava_token_expires_at: str | None = None
    strava_sync_gear: bool
    garminconnect_oauth1: dict | None = None
    garminconnect_oauth2: dict | None = None

    class Config:
        from_attributes = True
