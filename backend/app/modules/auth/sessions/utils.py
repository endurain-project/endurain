"""Pure helpers for auth sessions."""

import hmac
from datetime import UTC, datetime

from user_agents import parse

import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts


def verify_csrf_token(stored_hmac: str, expected_hmac: str) -> bool:
    """Compare the expected HMAC with a stored CSRF HMAC in constant time."""
    return hmac.compare_digest(expected_hmac, stored_hmac)


def validate_session_timeout(
    session: sessions_contracts.SessionRead,
    policy: sessions_contracts.SessionTimeoutPolicy,
) -> None:
    """Raise an authentication error if a session timeout elapsed.

    The idle timeout is checked only when the policy sets one; the absolute timeout always applies.
    """
    now = datetime.now(UTC)
    if policy.idle_timeout is not None and now > session.last_activity_at + policy.idle_timeout:
        raise core_exceptions.UnauthenticatedError("Session expired due to inactivity")
    if now > session.created_at + policy.absolute_timeout:
        raise core_exceptions.UnauthenticatedError("Session expired. Please login again for security.")


def parse_user_agent(user_agent: str) -> sessions_contracts.DeviceInfo:
    """Parse a user-agent string into normalized device information."""
    agent = parse(user_agent)
    device_type = (
        sessions_contracts.DeviceType.MOBILE
        if agent.is_mobile
        else sessions_contracts.DeviceType.TABLET
        if agent.is_tablet
        else sessions_contracts.DeviceType.PC
    )
    return sessions_contracts.DeviceInfo(
        device_type=device_type,
        operating_system=agent.os.family or "Unknown",
        operating_system_version=agent.os.version_string or "Unknown",
        browser=agent.browser.family or "Unknown",
        browser_version=agent.browser.version_string or "Unknown",
    )
