"""API key constants."""

from datetime import timedelta
from enum import StrEnum

#: Most active API keys one user may hold; a key is active while it is not revoked and has not expired.
MAX_ACTIVE_API_KEYS_PER_USER = 25

#: How long a revoked or expired API key is kept before the scheduled purge deletes it.
STALE_API_KEY_RETENTION = timedelta(days=30)


class ApiKeyScope(StrEnum):
    """Scopes an API key may be granted: the account's own data.

    A key never holds ``account:security``, ``account:export``, ``account:integrations`` or an administrator scope:
    it is a long-lived credential used without a second factor, so it may read and change the account's data but
    not how the account is protected, take all of it out, hand a provider's credentials to the server, or
    administer the server.
    """

    ACCOUNT = "account"
    ACTIVITIES_READ = "activities:read"
    ACTIVITIES_WRITE = "activities:write"
    ACTIVITIES_UPLOAD = "activities:upload"
    FOLLOWERS_READ = "followers:read"
    FOLLOWERS_WRITE = "followers:write"
    GEARS_READ = "gears:read"
    GEARS_WRITE = "gears:write"
    HEALTH_READ = "health:read"
    HEALTH_WRITE = "health:write"
    HEALTH_TARGETS_READ = "health-targets:read"
    HEALTH_TARGETS_WRITE = "health-targets:write"
    NOTIFICATIONS_READ = "notifications:read"
    NOTIFICATIONS_WRITE = "notifications:write"
    USERS_READ = "users:read"
