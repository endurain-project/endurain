"""Tests for sign-up token services."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.service as sign_up_service


class TestCreateSignUpToken:
    @patch("modules.auth.sign_up_tokens.service.sign_up_crud.create_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.sign_up_crud.mark_user_sign_up_tokens_used")
    @patch(
        "modules.auth.sign_up_tokens.service.token_hashing.generate_token_and_hash", return_value=("plain", "hashed")
    )
    def test_invalidates_old_tokens_then_stages_new_one(self, _generate, invalidate, create, mock_db):
        order = MagicMock()
        order.attach_mock(invalidate, "invalidate")
        order.attach_mock(create, "create")

        assert sign_up_service.create_sign_up_token(7, mock_db) == "plain"

        assert [call[0] for call in order.mock_calls] == ["invalidate", "create"]
        assert create.call_args.args[0].token_hash == "hashed"
        invalidate.assert_called_once_with(7, mock_db)
        mock_db.commit.assert_called_once()


class TestRevokePendingTokens:
    @patch("modules.auth.sign_up_tokens.service.sign_up_crud.mark_user_sign_up_tokens_used")
    def test_marks_the_users_unused_tokens_used_without_committing(self, invalidate, mock_db):
        sign_up_integration.revoke_pending_tokens(7, mock_db)

        invalidate.assert_called_once_with(7, mock_db)
        mock_db.commit.assert_not_called()


class TestEmailRequests:
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=False)
    def test_required_email_configuration_is_a_domain_error(self, _configured, mock_db):
        for request in (
            lambda: sign_up_service.request_sign_up_verification_email(1, mock_db),
            lambda: sign_up_service.request_sign_up_admin_approval_emails(1, mock_db),
        ):
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                request()

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers.publish_sign_up_verification_requested")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=True)
    def test_verification_event_is_staged_for_its_caller(self, _configured, publish, mock_db):
        sign_up_service.request_sign_up_verification_email(5, mock_db)
        publish.assert_called_once_with(5, mock_db)
        mock_db.commit.assert_not_called()

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers.publish_sign_up_approval_requested")
    @patch(
        "modules.auth.sign_up_tokens.service.users_integration.require_admin_users",
        return_value=[MagicMock(id=10), MagicMock(id=11)],
    )
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=True)
    def test_admin_approval_events_are_staged_for_each_admin(self, _configured, admins, publish, mock_db):
        sign_up_service.request_sign_up_admin_approval_emails(5, mock_db)
        assert [call.args for call in publish.call_args_list] == [(5, 10, mock_db), (5, 11, mock_db)]

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers.publish_email_change_verification_requested")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=True)
    def test_reverification_stages_only_when_mail_is_configured(self, _configured, publish, mock_db):
        assert sign_up_service.request_email_reverification(5, mock_db) is True
        publish.assert_called_once_with(5, mock_db)
        mock_db.commit.assert_not_called()

    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=False)
    def test_reverification_skips_when_mail_is_unavailable(self, _configured, mock_db):
        assert sign_up_service.request_email_reverification(5, mock_db) is False
        mock_db.commit.assert_not_called()

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers.publish_sign_up_approved")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=True)
    def test_approval_event_stages_in_caller_transaction(self, _configured, publish, mock_db):
        assert sign_up_service.request_sign_up_approved_email(5, mock_db) is True
        publish.assert_called_once_with(5, mock_db)
        mock_db.commit.assert_not_called()


class TestEmailPreparation:
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user", return_value=None)
    def test_missing_records_are_skipped(self, _get_user, mock_db):
        assert sign_up_service.prepare_sign_up_verification_email(1, "https://example.test", mock_db) is None
        assert sign_up_service.prepare_email_change_verification_email(1, "https://example.test", mock_db) is None
        assert sign_up_service.prepare_sign_up_approved_email(1, "https://example.test", mock_db) is None

    @patch("modules.auth.sign_up_tokens.service.sign_up_email_messages.get_signup_confirmation_email")
    @patch("modules.auth.sign_up_tokens.service.create_sign_up_token", return_value="plain-token")
    @patch(
        "modules.auth.sign_up_tokens.service.users_integration.get_user",
        return_value=MagicMock(id=1, name="Test", email="test@example.test", preferred_language="en"),
    )
    def test_verification_prepares_message(self, _get_user, _create_token, build_email, mock_db):
        build_email.return_value = ("subject", "html", "text")

        result = sign_up_service.prepare_sign_up_verification_email(1, "https://example.test", mock_db)

        assert result == ("test@example.test", "subject", "html", "text")
        assert "verify-email?token=plain-token" in build_email.call_args.args[1]

    @patch("modules.auth.sign_up_tokens.service.sign_up_email_messages.get_email_change_confirmation_email")
    @patch("modules.auth.sign_up_tokens.service.create_sign_up_token", return_value="plain-token")
    @patch(
        "modules.auth.sign_up_tokens.service.users_integration.get_user",
        return_value=MagicMock(id=1, name="Test", email="new@example.test", preferred_language="en"),
    )
    def test_email_change_verification_prepares_its_own_message(self, _get_user, _create_token, build_email, mock_db):
        build_email.return_value = ("subject", "html", "text")

        result = sign_up_service.prepare_email_change_verification_email(1, "https://example.test", mock_db)

        assert result == ("new@example.test", "subject", "html", "text")
        assert "verify-email?token=plain-token" in build_email.call_args.args[1]

    @patch("modules.auth.sign_up_tokens.service.sign_up_email_messages.get_admin_signup_notification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    def test_approval_request_targets_admin(self, get_user, build_email, mock_db):
        user = MagicMock(name="New user", username="new-user", email="new@example.test", preferred_language="en")
        admin = MagicMock(name="Admin", email="admin@example.test", preferred_language="en")
        get_user.side_effect = (user, admin)
        build_email.return_value = ("subject", "html", "text")

        result = sign_up_service.prepare_sign_up_approval_request_email(1, 2, "https://example.test", mock_db)

        assert result == ("admin@example.test", "subject", "html", "text")


class TestVerifySignUpToken:
    @patch("modules.auth.sign_up_tokens.service.sign_up_crud.claim_sign_up_token", return_value=42)
    def test_consumes_token_and_returns_user_id(self, claim, mock_db):
        assert sign_up_service.verify_sign_up_token("plain-token", mock_db) == 42
        claim.assert_called_once_with(hashlib.sha256(b"plain-token").hexdigest(), mock_db)

    @patch("modules.auth.sign_up_tokens.service.sign_up_crud.claim_sign_up_token", return_value=None)
    def test_invalid_token_is_a_domain_error(self, _claim, mock_db):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired"):
            sign_up_service.verify_sign_up_token("invalid", mock_db)
