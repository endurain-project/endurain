"""The data shapes the user integrations surface accepts from the provider modules."""

from typing import TypedDict


class StravaTokens(TypedDict):
    """The tokens Strava returns when an authorization code is exchanged or a token is refreshed.

    Attributes:
        access_token: The short-lived token that authenticates API calls.
        refresh_token: The token the next access token is refreshed with; Strava rotates it.
        expires_at: When the access token expires, in seconds since the epoch.
    """

    access_token: str
    refresh_token: str
    expires_at: int
