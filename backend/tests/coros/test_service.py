"""Tests for the COROS connection lifecycle and token storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.coros.constants as constants
import modules.coros.contracts as contracts
import modules.coros.crud as coros_crud
import modules.coros.models as coros_models
import modules.coros.oauth as coros_oauth
import modules.coros.service as coros_service
from tests._helpers.db import create_sqlite_session


def _metadata() -> contracts.CorosOAuthMetadata:
    return contracts.CorosOAuthMetadata(
        issuer="https://mcpeu.coros.com",
        authorization_endpoint="https://mcpeu.coros.com/oauth2/authorize",
        token_endpoint="https://mcpeu.coros.com/oauth2/token",
        revocation_endpoint="https://mcpeu.coros.com/oauth2/revoke",
        registration_endpoint="https://mcpeu.coros.com/connect/register",
        mcp_url="https://mcpeu.coros.com/mcp",
        scopes=("openid", "offline_access", "mcp.tools"),
    )


def _tokens(access: str = "access", refresh: str = "refresh", *, expired: bool = False) -> contracts.CorosTokenSet:
    now = datetime.now(UTC)
    return contracts.CorosTokenSet(
        access_token=access,
        refresh_token=refresh,
        token_expires_at=now - timedelta(minutes=1) if expired else now + timedelta(days=1),
        refresh_token_expires_at=now + timedelta(days=30),
        scope="openid offline_access mcp.tools",
    )


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


class TestAuthorization:
    """State is bound to the user and stored encrypted."""

    def test_begin_authorization_stores_the_state_and_verifier(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )

        url = coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)

        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        assert "state=" in url and "code_challenge=" in url
        assert row.state is not None
        assert row.code_verifier is not None and row.code_verifier != "verifier"
        assert core_cryptography.decrypt_token_fernet(row.code_verifier) is not None

    def test_begin_authorization_reuses_a_client_registered_for_the_same_callback(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        register = Mock(return_value=contracts.CorosClientRegistration("client-1"))
        monkeypatch.setattr(coros_oauth, "register_client", register)

        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)

        register.assert_called_once()

    def test_an_unknown_or_foreign_state_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            coros_service.complete_link(2, "code", "unknown-state", db)

    def test_an_expired_state_is_cleared(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        state = row.state
        row.state_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

        with pytest.raises(core_exceptions.InvalidInputError):
            coros_service.complete_link(1, "code", state, db)
        assert coros_crud.get_by_state(state, db) is None

    def test_complete_link_stores_encrypted_tokens(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )
        monkeypatch.setattr(coros_oauth, "exchange_code", Mock(return_value=_tokens()))
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        state = row.state

        coros_service.complete_link(1, "code", state, db)

        stored = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        assert stored.access_token != "access"
        assert stored.refresh_token != "refresh"
        assert core_cryptography.decrypt_token_fernet(stored.access_token) == "access"
        assert core_cryptography.decrypt_token_fernet(stored.refresh_token) == "refresh"
        assert stored.state is None


class TestRefresh:
    """Expired access tokens rotate the refresh token before a sync."""

    def test_an_expired_access_token_is_refreshed_and_persisted(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )
        monkeypatch.setattr(coros_oauth, "exchange_code", Mock(return_value=_tokens(expired=True)))
        refresh = Mock(return_value=_tokens(access="new-access", refresh="new-refresh"))
        monkeypatch.setattr(coros_oauth, "refresh_tokens", refresh)
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        state = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one().state
        coros_service.complete_link(1, "code", state, db)
        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        row.last_sync_status = "success"
        row.last_sync_activity_count = 4
        row.fit_download_count = 10
        db.commit()

        connection = coros_service.get_valid_connection(1, db)

        assert connection.access_token == "new-access"
        assert connection.refresh_token == "new-refresh"
        assert connection.last_sync_status == "success"
        assert connection.last_sync_activity_count == 4
        assert connection.fit_download_count == 10
        refresh.assert_called_once()

    def test_an_expired_refresh_token_requires_reconnection(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )
        monkeypatch.setattr(coros_oauth, "exchange_code", Mock(return_value=_tokens(expired=True)))
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        state = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one().state
        coros_service.complete_link(1, "code", state, db)
        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        row.refresh_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

        with pytest.raises(coros_oauth.CorosAuthenticationError):
            coros_service.get_valid_connection(1, db)


class TestUnlinkAndQuota:
    """Disconnect revokes tokens; the daily quota is enforced per user."""

    def test_unlink_revokes_both_tokens_and_clears_the_row(self, db, monkeypatch):
        monkeypatch.setattr(coros_oauth, "discover_metadata", Mock(return_value=_metadata()))
        monkeypatch.setattr(
            coros_oauth,
            "register_client",
            Mock(return_value=contracts.CorosClientRegistration("client-1")),
        )
        monkeypatch.setattr(coros_oauth, "exchange_code", Mock(return_value=_tokens()))
        revoke = Mock()
        monkeypatch.setattr(coros_oauth, "revoke_token", revoke)
        coros_service.begin_authorization(1, "https://app.example.com/coros/callback", db)
        state = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one().state
        coros_service.complete_link(1, "code", state, db)

        coros_service.unlink(1, db)

        row = db.query(coros_models.CorosIntegration).filter_by(user_id=1).one()
        assert row.access_token is None and row.refresh_token is None
        assert revoke.call_count == 2

    def test_the_daily_fit_quota_is_fifty(self, db):
        row = coros_crud.create_if_missing(1, db)
        db.commit()

        for _ in range(constants.MAX_FIT_DOWNLOADS_PER_DAY):
            assert coros_crud.reserve_fit_download(1, db) is True
            db.commit()

        assert coros_crud.reserve_fit_download(1, db) is False
        assert row.fit_download_count == constants.MAX_FIT_DOWNLOADS_PER_DAY

    def test_the_quota_resets_on_a_new_day(self, db):
        row = coros_crud.create_if_missing(1, db)
        row.fit_download_date = datetime.now(UTC).date() - timedelta(days=1)
        row.fit_download_count = constants.MAX_FIT_DOWNLOADS_PER_DAY
        db.commit()

        assert coros_crud.reserve_fit_download(1, db) is True
        assert row.fit_download_count == 1


class TestSkippedActivityRetry:
    """Missing files are permanent; parse failures are retried after a delay."""

    def test_a_missing_file_is_skipped_permanently(self, db):
        coros_crud.mark_activity_skipped(1, "label-1", "no_file", db)
        db.commit()
        row = db.query(coros_models.CorosSkippedActivity).filter_by(label_id="label-1").one()
        row.created_at = datetime.now(UTC) - timedelta(days=365)
        db.commit()

        assert coros_crud.is_activity_skipped(1, "label-1", db) is True

    def test_an_invalid_file_is_retried_after_a_week(self, db):
        coros_crud.mark_activity_skipped(1, "label-2", "invalid_file", db)
        db.commit()
        row = db.query(coros_models.CorosSkippedActivity).filter_by(label_id="label-2").one()
        row.created_at = datetime.now(UTC) - timedelta(days=constants.INVALID_FILE_RETRY_DAYS + 1)
        db.commit()

        assert coros_crud.is_activity_skipped(1, "label-2", db) is False

        coros_crud.mark_activity_skipped(1, "label-2", "invalid_file", db)
        db.commit()
        assert coros_crud.is_activity_skipped(1, "label-2", db) is True
