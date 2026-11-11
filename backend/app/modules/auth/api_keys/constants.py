"""API key constants."""

from enum import StrEnum


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
