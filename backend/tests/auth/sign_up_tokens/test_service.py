"""Tests for the sign-up workflow: a taken email gets the same answer as a new one."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema

_MODULE = "modules.auth.sign_up_tokens.service"


def _settings(*, verification=False, approval=False):
    return MagicMock(
        signup_enabled=True,
        signup_require_email_verification=verification,
        signup_require_admin_approval=approval,
    )


def _signup_user() -> users_schema.UsersSignup:
    return users_schema.UsersSignup(
        name="Test User",
        username="testuser",
        email="test@example.com",
        password="SecurePass1!",
        preferred_language="en",
    )


@pytest.fixture
def mock_db():
    return MagicMock()


class TestSignupWithATakenEmail:
    @pytest.mark.parametrize(("verification", "approval"), [(False, False), (True, False), (False, True), (True, True)])
    def test_answers_exactly_like_a_new_account(self, mock_db, verification, approval):
        settings = _settings(verification=verification, approval=approval)
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers"),
        ):
            users.create_signup_user.return_value = MagicMock(id=7)
            created = sign_up_service.signup(_signup_user(), mock_db)

            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)
            taken = sign_up_service.signup(_signup_user(), mock_db)

        assert taken == created

    def test_tells_the_existing_owner_and_creates_nothing(self, mock_db):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)

            sign_up_service.signup(_signup_user(), mock_db)

        users.get_user_by_email.assert_called_once_with("test@example.com", mock_db)
        publishers.publish_sign_up_existing_account.assert_called_once_with(3, mock_db)
        publishers.publish_sign_up_verification_requested.assert_not_called()
        mock_db.commit.assert_called_once()

    def test_without_mail_there_is_no_notice_but_the_answer_is_the_same(self, mock_db):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)

            result = sign_up_service.signup(_signup_user(), mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()
        assert result.message


class TestSignupWithATakenUsername:
    def test_a_new_email_with_a_taken_username_is_refused(self, mock_db):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
            pytest.raises(core_exceptions.ConflictError),
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = None

            sign_up_service.signup(_signup_user(), mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()


class TestExistingAccountEmail:
    def test_is_addressed_to_the_existing_owner(self, mock_db):
        owner = MagicMock(email="owner@example.com", preferred_language="en")
        owner.name = "Owner"
        with patch(f"{_MODULE}.users_integration.get_user", return_value=owner):
            message = sign_up_service.prepare_sign_up_existing_account_email(3, "https://app.example", mock_db)

        assert message is not None
        recipient, _subject, html_content, text_content = message
        assert recipient == "owner@example.com"
        assert "https://app.example/login" in html_content
        assert "https://app.example/login" in text_content

    def test_a_missing_owner_sends_nothing(self, mock_db):
        with patch(f"{_MODULE}.users_integration.get_user", return_value=None):
            assert sign_up_service.prepare_sign_up_existing_account_email(3, "https://app.example", mock_db) is None
