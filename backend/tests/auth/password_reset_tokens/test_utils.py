"""Tests for password-reset workflows after their move to service.py."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import core.i18n as core_i18n
import modules.auth.computation as token_hashing
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.password_reset_tokens.service as password_reset_service
from tests._helpers.db import create_sqlite_session_factory, ensure_user


class TestUsePasswordResetToken:
    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_completed"
    )
    @patch("modules.auth.password_reset_tokens.service.mfa_integration.clear_pending_mfa_for_user")
    @patch("modules.auth.password_reset_tokens.service.sessions_integration.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.mark_user_password_reset_tokens_used")
    @patch("modules.auth.password_reset_tokens.service.credentials_integration.set_local_password_hash")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token")
    def test_password_and_sessions_commit_before_pending_mfa_is_cleared(
        self, claim, set_password, mark_tokens, delete_sessions, clear_pending, publish_completed, mock_db
    ):
        user = MagicMock(active=True, access_type="regular", username="alice", email="alice@example.com")
        settings = MagicMock(local_login_enabled=True)
        claim.return_value = 42
        order = MagicMock()
        order.attach_mock(set_password, "password")
        order.attach_mock(mark_tokens, "tokens")
        order.attach_mock(delete_sessions, "sessions")
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(clear_pending, "clear_pending")
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=settings,
            ),
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.ensure_password_differs_from_current"
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.validate_and_hash_password_for_user",
                return_value="hashed",
            ) as hash_password,
        ):
            password_reset_service.use_password_reset_token("plain", "new password", mock_db)

        claim.assert_called_once_with(hashlib.sha256(b"plain").hexdigest(), mock_db)
        hash_password.assert_called_once_with(
            settings, "regular", "new password", mock_db, username="alice", email="alice@example.com"
        )
        assert [call[0] for call in order.mock_calls] == [
            "password",
            "tokens",
            "sessions",
            "commit",
            "clear_pending",
        ]
        clear_pending.assert_called_once_with(42)
        set_password.assert_called_once_with(42, "hashed", mock_db, change_required=False)
        publish_completed.assert_called_once_with(42, mock_db)

    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_completed"
    )
    @patch("modules.auth.password_reset_tokens.service.sessions_integration.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.service.credentials_integration.set_local_password_hash")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=42)
    def test_the_current_password_is_refused_before_any_write_or_event(
        self, _claim, set_password, delete_sessions, stage_event, mock_db
    ):
        user = MagicMock(active=True, access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=MagicMock(local_login_enabled=True),
            ),
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.ensure_password_differs_from_current",
                side_effect=credentials_contracts.PasswordUnchangedError(),
            ),
            pytest.raises(credentials_contracts.PasswordUnchangedError),
        ):
            password_reset_service.use_password_reset_token("plain", "same password", mock_db)

        set_password.assert_not_called()
        delete_sessions.assert_not_called()
        stage_event.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.auth.password_reset_tokens.service.jasil_audit.record_detached")
    @patch("modules.auth.password_reset_tokens.service.sessions_integration.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.service.credentials_integration.set_local_password_hash")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=42)
    def test_an_inactive_account_cannot_reset_its_password(
        self, _claim, set_password, delete_sessions, record, mock_db
    ):
        user = MagicMock(active=False, access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=MagicMock(local_login_enabled=True),
            ),
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired"),
        ):
            password_reset_service.use_password_reset_token("plain", "new password", mock_db)

        set_password.assert_not_called()
        delete_sessions.assert_not_called()
        record.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=None
    )
    def test_invalid_token_is_a_domain_error(self, _claim, mock_db):
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=MagicMock(password_breach_check_enabled=False),
            ),
            pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired"),
        ):
            password_reset_service.use_password_reset_token("invalid", "replacement", mock_db)
        mock_db.commit.assert_not_called()

    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=42)
    def test_password_policy_error_is_unprocessable_and_keeps_its_code(self, _claim, mock_db):
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=MagicMock(local_login_enabled=True),
            ),
            patch(
                "modules.auth.password_reset_tokens.service.users_integration.require_user",
                return_value=MagicMock(access_type="regular"),
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.ensure_password_differs_from_current"
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.validate_and_hash_password_for_user",
                side_effect=credentials_contracts.PasswordTooShortError("Password is too short"),
            ),
            pytest.raises(credentials_contracts.PasswordTooShortError) as exc_info,
        ):
            password_reset_service.use_password_reset_token("valid", "weak", mock_db)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "Password is too short"
        assert exc_info.value.code == "password-too-short"
        mock_db.commit.assert_not_called()


class TestStagePasswordResetToken:
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.mark_user_password_reset_tokens_used")
    def test_stages_replacement_without_committing(self, invalidate, create, mock_db):
        password_reset_service._stage_password_reset_token(7, token_hashing.sha256_hex("plain"), mock_db)

        invalidate.assert_called_once_with(7, mock_db)
        token = create.call_args.args[0]
        assert token.user_id == 7
        assert token.token_hash == token_hashing.sha256_hex("plain")
        mock_db.commit.assert_not_called()


class TestRetriedResetEvent:
    """The event is delivered at least once, so preparing it again must not break the link already mailed."""

    @pytest.fixture
    def factory(self):
        session_factory = create_sqlite_session_factory()
        ensure_user(session_factory, 5)
        yield session_factory
        session_factory.kw["bind"].dispose()

    def _prepare(self, factory, event_id: str) -> str:
        user = MagicMock(id=5, active=True, preferred_language="en", email="test@example.test")
        payload = password_reset_events.PasswordResetRequestedPayload(user_id=5, ip_address=None, user_agent=None)
        with (
            patch("modules.auth.password_reset_tokens.service.users_integration.get_user", return_value=user),
            patch("modules.auth.password_reset_tokens.service._may_reset_password", return_value=True),
            patch(
                "modules.auth.password_reset_tokens.service.password_reset_email_messages.get_password_reset_email",
                return_value=("subject", "html", "text"),
            ) as build_email,
            factory() as db,
        ):
            # A fresh store per call: the cooldown belongs to the request that admits the event, not the retry.
            password_reset_service.prepare_password_reset_email(
                payload, event_id, "https://example.test", MemoryState(), db
            )
        return build_email.call_args.args[1].split("token=")[1]

    def _claim(self, factory, token: str) -> int | None:
        with factory() as db:
            claimed = password_reset_crud.claim_password_reset_token(token_hashing.sha256_hex(token), db)
            db.commit()
        return claimed

    def test_the_email_carries_the_reset_link_in_the_users_language(self, factory):
        user = MagicMock(id=5, active=True, preferred_language="pt", email="test@example.test")
        user.name = "Ana"
        payload = password_reset_events.PasswordResetRequestedPayload(user_id=5, ip_address=None, user_agent=None)
        with (
            patch("modules.auth.password_reset_tokens.service.users_integration.get_user", return_value=user),
            patch("modules.auth.password_reset_tokens.service._may_reset_password", return_value=True),
            patch(
                "modules.auth.password_reset_tokens.service.password_reset_email_messages.get_password_reset_email",
                return_value=("subject", "html", "text"),
            ) as build_email,
            factory() as db,
        ):
            result = password_reset_service.prepare_password_reset_email(
                payload, "event-1", "https://example.test", MemoryState(), db
            )

        assert result == ("test@example.test", "subject", "html", "text")
        name, link, host, locale = build_email.call_args.args
        assert name == "Ana"
        assert link.startswith("https://example.test/reset-password?token=")
        assert self._claim(factory, link.split("token=")[1]) == 5
        assert host == "https://example.test"
        assert locale == core_i18n.normalize_locale("pt")

    def test_a_retry_mails_the_same_link_and_it_still_works(self, factory):
        first = self._prepare(factory, "event-1")
        second = self._prepare(factory, "event-1")

        assert second == first
        assert self._claim(factory, first) == 5

    def test_a_new_request_replaces_the_earlier_link(self, factory):
        first = self._prepare(factory, "event-1")
        second = self._prepare(factory, "event-2")

        assert second != first
        assert self._claim(factory, first) is None
        assert self._claim(factory, second) == 5

    def test_a_retry_of_an_older_request_does_not_revoke_the_newer_link(self, factory):
        self._prepare(factory, "event-1")
        newer = self._prepare(factory, "event-2")

        self._prepare(factory, "event-1")

        assert self._claim(factory, newer) == 5


class TestValidateToken:
    """Validation reports usability without consuming the token or revealing why it failed."""

    @pytest.fixture
    def factory(self):
        session_factory = create_sqlite_session_factory()
        ensure_user(session_factory, 5)
        yield session_factory
        session_factory.kw["bind"].dispose()

    def _store(self, factory, token: str, *, used: bool = False, expires_in: timedelta = timedelta(hours=1)) -> None:
        now = datetime.now(UTC)
        with factory() as db:
            password_reset_crud.create_password_reset_token(
                password_reset_schema.PasswordResetToken(
                    id=token,
                    user_id=5,
                    token_hash=token_hashing.sha256_hex(token),
                    created_at=now,
                    expires_at=now + expires_in,
                    used=used,
                ),
                db,
            )
            db.commit()

    def test_a_usable_token_validates_and_can_still_be_claimed(self, factory):
        self._store(factory, "good")

        user = MagicMock(id=5, active=True, access_type="regular")
        with (
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            patch("modules.auth.password_reset_tokens.service._may_reset_password", return_value=True),
            factory() as db,
        ):
            password_reset_service.validate_password_reset_token("good", db)
            password_reset_service.validate_password_reset_token("good", db)
            assert password_reset_crud.claim_password_reset_token(token_hashing.sha256_hex("good"), db) == 5

    @pytest.mark.parametrize("state", ["used", "expired", "unknown"])
    def test_every_unusable_token_fails_with_the_same_error(self, factory, state):
        if state == "used":
            self._store(factory, "tok", used=True)
        elif state == "expired":
            self._store(factory, "tok", expires_in=timedelta(seconds=-5))

        with factory() as db, pytest.raises(core_exceptions.InvalidInputError) as raised:
            password_reset_service.validate_password_reset_token("tok", db)

        assert str(raised.value) == "Invalid or expired password reset token"

    @pytest.mark.parametrize("reason", ["inactive", "no_local_password"])
    def test_a_token_confirm_would_refuse_fails_the_same_and_stays_unconsumed(self, factory, reason):
        self._store(factory, "tok")
        user = MagicMock(id=5, active=reason != "inactive", access_type="regular")

        with (
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.has_local_password",
                return_value=reason != "no_local_password",
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.allows_password_sign_in",
                return_value=True,
            ),
            patch("modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings"),
            patch("modules.auth.password_reset_tokens.service.jasil_audit.record_detached") as record,
            factory() as db,
        ):
            with pytest.raises(core_exceptions.InvalidInputError) as raised:
                password_reset_service.validate_password_reset_token("tok", db)

            assert str(raised.value) == "Invalid or expired password reset token"
            record.assert_not_called()
            assert password_reset_crud.get_usable_password_reset_token_user_id(token_hashing.sha256_hex("tok"), db) == 5

    def test_validation_records_no_audit_row(self, factory):
        with (
            patch("modules.auth.password_reset_tokens.service.jasil_audit.record_detached") as record,
            factory() as db,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            password_reset_service.validate_password_reset_token("nope", db)

        record.assert_not_called()
