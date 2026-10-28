"""Pure helpers for auth sessions."""

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from user_agents import parse

import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts


class DeviceType(Enum):
    """Normalized device classes from a user-agent string."""

    MOBILE = "Mobile"
    TABLET = "Tablet"
    PC = "PC"


@dataclass
class DeviceInfo:
    """Parsed user-agent information."""

    device_type: DeviceType
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str


def verify_csrf_token(stored_hmac: str, expected_hmac: str) -> bool:
    """Compare the expected HMAC with a stored CSRF HMAC in constant time."""
    return hmac.compare_digest(expected_hmac, stored_hmac)


def validate_session_timeout(
    session: sessions_contracts.SessionRead,
    policy: sessions_contracts.SessionTimeoutPolicy,
) -> None:
    """Raise an authentication error if a configured session timeout elapsed."""
    if policy.idle_timeout is None or policy.absolute_timeout is None:
        return

    now = datetime.now(UTC)
    if now > session.last_activity_at + policy.idle_timeout:
        raise core_exceptions.UnauthenticatedError("Session expired due to inactivity")
    if now > session.created_at + policy.absolute_timeout:
        raise core_exceptions.UnauthenticatedError("Session expired. Please login again for security.")


def get_user_agent(headers: Mapping[str, str]) -> str:
    """Return the User-Agent header or an empty string."""
    return headers.get("user-agent", "")


def parse_user_agent(user_agent: str) -> DeviceInfo:
    """Parse a user-agent string into normalized device information."""
    agent = parse(user_agent)
    device_type = DeviceType.MOBILE if agent.is_mobile else DeviceType.TABLET if agent.is_tablet else DeviceType.PC
    return DeviceInfo(
        device_type=device_type,
        operating_system=agent.os.family or "Unknown",
        operating_system_version=agent.os.version_string or "Unknown",
        browser=agent.browser.family or "Unknown",
        browser_version=agent.browser.version_string or "Unknown",
    )
