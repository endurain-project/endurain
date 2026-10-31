"""Tests for the sign-up workflow: a taken email gets the same answer as a new one."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema

_MODULE = "modules.auth.sign_up_tokens.service"


def _settings(*, verification=False, approval=False):
    return MagicMock(
        signup_enabled=True,
        signup_require_email_verification=verification,
        signup_require_admin_approval=approval,
    )


def _signup_user(*, with_password: bool = True) -> users_schema.UsersSignup:
    return users_schema.UsersSignup(
        name="Test User",
        username="testuser",
        email="test@example.com",
        password="SecurePass1!" if with_password else None,
        preferred_language="en",
    )


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def state():
    return MemoryState()


class TestSignupWithATakenEmail:
    @pytest.mark.parametrize(("verification", "approval"), [(False, False), (True, False), (False, True), (True, True)])
    def test_answers_exactly_like_a_new_account(self, mock_db, state, verification, approval):
        settings = _settings(verification=verification, approval=approval)
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers"),
        ):
            body = _signup_user(with_password=not verification)
            users.create_signup_user.return_value = MagicMock(id=7)
            created = sign_up_service.signup(body, state, mock_db)

            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)
            taken = sign_up_service.signup(body, state, mock_db)

        assert taken == created

    def test_tells_the_existing_owner_and_creates_nothing(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)

            sign_up_service.signup(_signup_user(), state, mock_db)

        users.get_user_by_email.assert_called_once_with("test@example.com", mock_db)
        publishers.publish_sign_up_existing_account.assert_called_once_with(3, mock_db)
        publishers.publish_sign_up_verification_requested.assert_not_called()
        mock_db.commit.assert_called_once()

    def test_without_mail_there_is_no_notice_but_the_answer_is_the_same(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=3)

            result = sign_up_service.signup(_signup_user(), state, mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()
        assert result.message


class TestExistingAccountNoticeCooldown:
    def _signup_with_a_taken_email(self, state, db, *, owner_id=3):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=owner_id)
            result = sign_up_service.signup(_signup_user(), state, db)
        return result, publishers

    def test_the_owner_is_told_once_per_cooldown(self, mock_db, state):
        first, publishers = self._signup_with_a_taken_email(state, mock_db)
        second, repeat = self._signup_with_a_taken_email(state, mock_db)

        publishers.publish_sign_up_existing_account.assert_called_once()
        repeat.publish_sign_up_existing_account.assert_not_called()
        assert second == first

    def test_each_owner_has_their_own_cooldown(self, mock_db, state):
        self._signup_with_a_taken_email(state, mock_db, owner_id=3)
        _, other = self._signup_with_a_taken_email(state, mock_db, owner_id=4)

        other.publish_sign_up_existing_account.assert_called_once()

    def test_an_unreachable_state_store_skips_the_notice_without_changing_the_answer(self, mock_db):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")

        result, publishers = self._signup_with_a_taken_email(broken, mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()
        assert result.message


class TestSignupWithATakenUsername:
    def test_a_new_email_with_a_taken_username_is_refused(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
            pytest.raises(core_exceptions.ConflictError),
        ):
            users.create_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = None

            sign_up_service.signup(_signup_user(), state, mock_db)

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


class TestSignupPasswordPolicy:
    def test_a_password_is_refused_when_the_address_must_be_verified(self, mock_db, state):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(verification=True)
            ),
            patch(f"{_MODULE}.users_integration") as users,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            sign_up_service.signup(_signup_user(), state, mock_db)

        users.create_signup_user.assert_not_called()

    def test_a_missing_password_is_refused_when_verification_is_off(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.users_integration") as users,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            sign_up_service.signup(_signup_user(with_password=False), state, mock_db)

        users.create_signup_user.assert_not_called()

    def test_a_disabled_registration_is_refused_before_the_password_is_judged(self, mock_db, state):
        settings = _settings(verification=True)
        settings.signup_enabled = False
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=settings),
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            sign_up_service.signup(_signup_user(), state, mock_db)

    def test_a_passwordless_sign_up_with_verification_creates_the_user(self, mock_db, state):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(verification=True)
            ),
            patch(f"{_MODULE}.users_integration") as users,
            patch(f"{_MODULE}.request_sign_up_verification_email"),
        ):
            users.create_signup_user.return_value = MagicMock(id=7)
            sign_up_service.signup(_signup_user(with_password=False), state, mock_db)

        assert users.create_signup_user.call_args.args[0].password is None


def _claim(*, previous_email=None):
    return MagicMock(id="t1", user_id=7, email="u@example.com", previous_email=previous_email)


class TestVerifyEmailPassword:
    @pytest.fixture
    def deps(self):
        names = ["credentials_integration", "sessions_integration", "mfa_integration", "users_integration"]
        mocks = {name: MagicMock() for name in names}
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(verification=True)
            ),
            patch(f"{_MODULE}.verify_sign_up_token") as verify_token,
            patch.multiple(_MODULE, **mocks),
            patch(f"{_MODULE}.sign_up_event_publishers"),
        ):
            verify_token.return_value = _claim()
            mocks["users_integration"].get_user.return_value = MagicMock(id=7, active=False, access_type="regular")
            mocks["users_integration"].is_deactivated.return_value = False
            mocks["credentials_integration"].validate_and_hash_password_for_user.return_value = "hashed"
            yield mocks | {"verify_token": verify_token}

    def test_a_sign_up_token_without_a_password_asks_for_one_and_commits_nothing(self, deps, mock_db):
        with pytest.raises(core_exceptions.PasswordRequiredError):
            sign_up_service.verify_email("tok", None, mock_db)

        mock_db.commit.assert_not_called()
        deps["credentials_integration"].set_local_password_hash.assert_not_called()
        deps["users_integration"].stage_email_verification.assert_not_called()

    def test_the_password_replaces_any_existing_hash_and_ends_sessions(self, deps, mock_db):
        result = sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)

        creds = deps["credentials_integration"]
        creds.validate_and_hash_password_for_user.assert_called_once()
        assert creds.validate_and_hash_password_for_user.call_args.args[2] == "ChosenPass1!"
        creds.set_local_password_hash.assert_called_once_with(7, "hashed", mock_db)
        deps["sessions_integration"].delete_sessions_by_user.assert_called_once_with(7, mock_db)
        deps["mfa_integration"].clear_pending_mfa_for_user.assert_called_once_with(7)
        deps["users_integration"].stage_email_verification.assert_called_once()
        assert "log in" in result.message

    def test_a_password_failing_the_policy_is_a_policy_error(self, deps, mock_db):
        deps[
            "credentials_integration"
        ].validate_and_hash_password_for_user.side_effect = core_exceptions.InvalidInputError("too weak")

        with pytest.raises(credentials_contracts.PasswordPolicyError):
            sign_up_service.verify_email("tok", "weakweak", mock_db)

        mock_db.commit.assert_not_called()
        deps["credentials_integration"].set_local_password_hash.assert_not_called()

    def test_an_activated_account_without_a_password_still_chooses_one(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(id=7, active=True, access_type="regular")
        deps["credentials_integration"].has_local_password.return_value = False

        with pytest.raises(core_exceptions.PasswordRequiredError):
            sign_up_service.verify_email("tok", None, mock_db)
        mock_db.commit.assert_not_called()

        sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)
        deps["credentials_integration"].set_local_password_hash.assert_called_once_with(7, "hashed", mock_db)

    def test_an_activated_account_with_a_password_verifies_without_one(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(id=7, active=True, access_type="regular")
        deps["credentials_integration"].has_local_password.return_value = True

        sign_up_service.verify_email("tok", None, mock_db)

        deps["credentials_integration"].set_local_password_hash.assert_not_called()
        mock_db.commit.assert_called_once()

    def test_an_email_change_token_refuses_a_password(self, deps, mock_db):
        deps["verify_token"].return_value = _claim(previous_email="old@example.com")

        with pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)

        deps["credentials_integration"].set_local_password_hash.assert_not_called()

    def test_an_email_change_token_without_a_password_works_as_before(self, deps, mock_db):
        deps["verify_token"].return_value = _claim(previous_email="old@example.com")
        deps["users_integration"].get_user.return_value = MagicMock(id=7, active=True)

        result = sign_up_service.verify_email("tok", None, mock_db)

        deps["sessions_integration"].delete_sessions_by_user.assert_not_called()
        mock_db.commit.assert_called_once()
        assert "verified" in result.message.lower()

    def test_a_sign_up_token_with_verification_disabled_stays_a_precondition_failure(self, deps, mock_db):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            pytest.raises(core_exceptions.PreconditionFailedError),
        ):
            sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)
