"""Tests for pure auth-session helpers."""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.utils as sessions_utils
import modules.server_settings.contracts as server_settings_contracts

_POLICY = server_settings_contracts.SessionPolicy(
    access_token_ttl=timedelta(minutes=15),
    refresh_token_ttl=timedelta(days=7),
    idle_timeout=timedelta(hours=1),
    absolute_timeout=timedelta(hours=24),
)
_NO_TIMEOUT_POLICY = dataclasses.replace(_POLICY, idle_timeout=None, absolute_timeout=None)


def _session(*, last_activity_at: datetime, created_at: datetime) -> sessions_contracts.SessionRead:
    return sessions_contracts.SessionRead(
        id="session-id",
        user_id=1,
        refresh_token=None,
        ip_address="127.0.0.1",
        device_type="PC",
        operating_system="Linux",
        operating_system_version="1",
        browser="Firefox",
        browser_version="1",
        created_at=created_at,
        last_activity_at=last_activity_at,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        oauth_state_id=None,
        tokens_exchanged=False,
        token_family_id="family-id",
        rotation_count=0,
        last_rotation_at=None,
        csrf_token_hash=None,
    )


def test_device_type_values():
    assert [value.value for value in sessions_utils.DeviceType] == ["Mobile", "Tablet", "PC"]


def test_device_info_fields():
    info = sessions_utils.DeviceInfo(sessions_utils.DeviceType.PC, "Linux", "1", "Firefox", "1")
    assert info.operating_system == "Linux"
    assert info.browser == "Firefox"


def test_get_user_agent_returns_header_or_empty():
    assert sessions_utils.get_user_agent({"user-agent": "Firefox"}) == "Firefox"
    assert sessions_utils.get_user_agent({}) == ""


def test_parse_user_agent_desktop():
    info = sessions_utils.parse_user_agent(
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    )
    assert info.device_type is sessions_utils.DeviceType.PC
    assert info.browser == "Firefox"


def test_parse_user_agent_mobile():
    info = sessions_utils.parse_user_agent(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
    )
    assert info.device_type is sessions_utils.DeviceType.MOBILE


def test_parse_user_agent_unknown_values():
    info = sessions_utils.parse_user_agent("")
    assert info.operating_system == "Other"
    assert info.browser == "Other"


def test_validate_timeout_accepts_active_session():
    now = datetime.now(UTC)
    sessions_utils.validate_session_timeout(_session(last_activity_at=now, created_at=now), _POLICY)


def test_validate_timeout_rejects_idle_session():
    now = datetime.now(UTC)
    session = _session(last_activity_at=now - timedelta(hours=2), created_at=now)
    with pytest.raises(core_exceptions.UnauthenticatedError, match="inactivity"):
        sessions_utils.validate_session_timeout(session, _POLICY)


def test_validate_timeout_rejects_absolute_expiry():
    now = datetime.now(UTC)
    session = _session(last_activity_at=now, created_at=now - timedelta(days=2))
    with pytest.raises(core_exceptions.UnauthenticatedError, match="login again"):
        sessions_utils.validate_session_timeout(session, _POLICY)


def test_validate_timeout_skips_when_policy_disabled():
    old = datetime.now(UTC) - timedelta(days=10)
    sessions_utils.validate_session_timeout(_session(last_activity_at=old, created_at=old), _NO_TIMEOUT_POLICY)


def test_verify_csrf_token_compares_hmac_values():
    assert sessions_utils.verify_csrf_token("a" * 64, "a" * 64)
    assert not sessions_utils.verify_csrf_token("a" * 64, "b" * 64)
