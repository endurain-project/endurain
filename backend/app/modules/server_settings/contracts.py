"""Inter-module data shapes for server settings.

Separate from ``schema.py`` (the HTTP request/response payloads) because these
are shapes other modules consume, not shapes a client ever sees — keeping them
apart also keeps the generated OpenAPI free of internal types.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum


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
        idle_timeout: Inactivity after which a session ends, or None when the idle timeout is disabled.
        absolute_timeout: Age after which a session ends whatever its activity; always applies.
        api_key_max_lifetime: Longest lifetime of a new API key, and the lifetime it gets when none is asked for.
    """

    access_token_ttl: timedelta
    refresh_token_ttl: timedelta
    idle_timeout: timedelta | None
    absolute_timeout: timedelta
    api_key_max_lifetime: timedelta


@dataclass(frozen=True)
class AuditRetention:
    """How long the audit trail is kept.

    Attributes:
        retention_days: Days after which audit trail partitions are dropped; 0 keeps everything.
        legal_hold: Suspend all pruning of the audit trail.
    """

    retention_days: int
    legal_hold: bool


class RequireMfa(StrEnum):
    """Which accounts the server requires to have MFA.

    Attributes:
        OFF: No account is required to.
        ADMINISTRATORS: Administrators are.
        EVERYONE: Every account is.
    """

    OFF = "off"
    ADMINISTRATORS = "administrators"
    EVERYONE = "everyone"

    def covers(self, *, is_admin: bool) -> bool:
        """Return whether the requirement applies to an account.

        Args:
            is_admin: Whether the account is an administrator.

        Returns:
            True when the account must have MFA.
        """
        if self is RequireMfa.EVERYONE:
            return True
        return self is RequireMfa.ADMINISTRATORS and is_admin


@dataclass(frozen=True)
class AccessPolicy:
    """What the server decides about a request's credential, read once per request.

    Attributes:
        session: How long tokens and sessions live.
        require_mfa: Which accounts must have MFA.
    """

    session: SessionPolicy
    require_mfa: RequireMfa
