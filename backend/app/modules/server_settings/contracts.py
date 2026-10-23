"""Inter-module data shapes for server settings.

Separate from ``schema.py`` (the HTTP request/response payloads) because these
are shapes other modules consume, not shapes a client ever sees — keeping them
apart also keeps the generated OpenAPI free of internal types.
"""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class TileServerSettings:
    """The configured map-tile source, ready to render with.

    Attributes:
        tile_url: Tile URL template, or None when unconfigured.
        background_color: Map canvas background colour, or None when unconfigured.
        api_key: Tile-provider API key, **decrypted**. Decryption happens inside
            the owning module so a consumer never handles the ciphertext or the
            key material.
    """

    tile_url: str | None = None
    background_color: str | None = None
    api_key: str | None = None


@dataclass(frozen=True)
class SessionPolicy:
    """How long tokens and sessions live.

    Attributes:
        access_token_ttl: Lifetime of a new access token.
        refresh_token_ttl: Lifetime of a new refresh token and of the session it renews.
        idle_timeout: Inactivity after which a session ends, or None when timeouts are disabled.
        absolute_timeout: Age after which a session ends whatever its activity, or None when
            timeouts are disabled.
    """

    access_token_ttl: timedelta
    refresh_token_ttl: timedelta
    idle_timeout: timedelta | None
    absolute_timeout: timedelta | None
