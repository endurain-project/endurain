"""Tests for the token-rotation policy enum."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import modules.auth.identity_providers.token_policy as token_policy
from modules.auth.identity_providers.token_policy import TokenAction
from tests._helpers.auth import MOCK_USER_ID

IDP_ID = uuid.uuid4()


class TestTokenActionEnum:
    """TokenAction enum values used by token-rotation policy."""

    def test_enum_values(self):
        assert TokenAction.SKIP.value == "skip"
        assert TokenAction.REFRESH.value == "refresh"
        assert TokenAction.CLEAR.value == "clear"


def _session_token(**overrides):
    now = datetime.now(UTC)
    values = {
        "user_id": MOCK_USER_ID,
        "idp_id": IDP_ID,
        "refresh_token": "encrypted",
        "access_token_expires_at": now + timedelta(hours=1),
        "refresh_token_updated_at": now - timedelta(hours=1),
        "created_at": now - timedelta(hours=2),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestShouldRefreshIdpToken:
    """The policy reads the session's own sign-in row."""

    def test_a_row_without_a_token_is_skipped(self):
        assert token_policy.should_refresh_idp_token(_session_token(refresh_token=None)) is TokenAction.SKIP

    def test_a_token_past_the_maximum_age_is_cleared(self):
        old = datetime.now(UTC) - timedelta(days=token_policy.MAX_IDP_TOKEN_AGE_DAYS + 1)

        assert token_policy.should_refresh_idp_token(_session_token(refresh_token_updated_at=old)) is TokenAction.CLEAR

    def test_the_age_counts_from_the_sign_in_when_the_token_was_never_updated(self):
        old = datetime.now(UTC) - timedelta(days=token_policy.MAX_IDP_TOKEN_AGE_DAYS + 1)
        row = _session_token(refresh_token_updated_at=None, created_at=old)

        assert token_policy.is_token_expired_by_age(row) is True

    def test_an_unknown_access_token_expiry_is_skipped(self):
        assert token_policy.should_refresh_idp_token(_session_token(access_token_expires_at=None)) is TokenAction.SKIP

    def test_a_token_stored_a_moment_ago_is_not_refreshed_again(self):
        row = _session_token(
            access_token_expires_at=datetime.now(UTC) + timedelta(seconds=30),
            refresh_token_updated_at=datetime.now(UTC) - timedelta(seconds=5),
        )

        assert token_policy.should_refresh_idp_token(row) is TokenAction.SKIP

    def test_an_access_token_about_to_expire_is_refreshed(self):
        row = _session_token(access_token_expires_at=datetime.now(UTC) + timedelta(minutes=1))

        assert token_policy.should_refresh_idp_token(row) is TokenAction.REFRESH

    def test_a_token_with_time_left_is_skipped(self):
        assert token_policy.should_refresh_idp_token(_session_token()) is TokenAction.SKIP
