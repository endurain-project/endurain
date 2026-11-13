"""Tests for the sign-up workflow: a taken email gets the same answer as a new one."""

import contextlib
import uuid
from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.sign_up_tokens.audit_actions as sign_up_audit_actions
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema
from tests._helpers.auth import MOCK_USER_ID
from tests.auth.sign_up_tokens.ids import tid

_USER_3 = uuid.UUID("00000000-0000-4000-8000-000000000003")
_USER_4 = uuid.UUID("00000000-0000-4000-8000-000000000004")
_USER_10 = uuid.UUID("00000000-0000-4000-8000-000000000010")

_MODULE = "modules.auth.sign_up_tokens.service"
#: Configures a patched users module so that no account holds the username a sign-up asks for.
_FREE_USERNAME = {"get_user_by_username.return_value": None}


def _settings(*, verification=False, approval=False):
    return MagicMock(
        signup_enabled=True,
        signup_require_email_verification=verification,
        signup_require_admin_approval=approval,
        password_breach_check_enabled=False,
    )


def _signup_user(*, with_password: bool = True) -> users_schema.UserSignup:
    return users_schema.UserSignup(
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
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers"),
        ):
            body = _signup_user(with_password=not verification)
            users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID)
            created = sign_up_service.signup(body, state, mock_db)

            users.stage_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=_USER_3)
            taken = sign_up_service.signup(body, state, mock_db)

        assert taken == created

    def test_tells_the_existing_owner_and_creates_nothing(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.stage_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=_USER_3)

            sign_up_service.signup(_signup_user(), state, mock_db)

        users.get_user_by_email.assert_called_once_with("test@example.com", mock_db)
        publishers.publish_sign_up_existing_account.assert_called_once_with(_USER_3, mock_db)
        publishers.publish_sign_up_verification_requested.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_without_mail_there_is_no_notice_but_the_answer_is_the_same(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.stage_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            users.get_user_by_email.return_value = MagicMock(id=_USER_3)

            result = sign_up_service.signup(_signup_user(), state, mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()
        assert result.next_step


class TestSignupCommitsTheAccountAndItsEventTogether:
    @pytest.mark.parametrize("verification", [True, False])
    def test_one_commit_follows_the_staged_account_and_event(self, mock_db, state, verification):
        order = MagicMock()
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings",
                return_value=_settings(verification=verification),
            ),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID)
            order.attach_mock(users.stage_signup_user, "user")
            order.attach_mock(publishers.publish_sign_up_verification_requested, "event")
            order.attach_mock(mock_db.commit, "commit")

            sign_up_service.signup(_signup_user(with_password=not verification), state, mock_db)

        names = [call[0] for call in order.mock_calls]
        assert names[-1] == "commit"
        assert names.count("commit") == 1
        assert ("event" in names) is verification


class TestSignupAwaitingApproval:
    @pytest.mark.parametrize(
        ("verification", "approval", "asked"),
        [(False, True, True), (True, True, False), (False, False, False), (True, False, False)],
    )
    def test_the_administrators_are_asked_once_nothing_is_left_to_verify(
        self, mock_db, state, verification, approval, asked
    ):
        """A sign-up that must verify its email asks for approval when it verifies; one that need not asks now."""
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings",
                return_value=_settings(verification=verification, approval=approval),
            ),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID, pending_admin_approval=approval)
            users.require_admin_users.return_value = [MagicMock(id=_USER_10)]

            sign_up_service.signup(_signup_user(with_password=not verification), state, mock_db)

        if asked:
            publishers.publish_sign_up_approval_requested.assert_called_once_with(MOCK_USER_ID, _USER_10, mock_db)
        else:
            publishers.publish_sign_up_approval_requested.assert_not_called()
        mock_db.commit.assert_called_once()


class TestSignUpVerificationResend:
    def _resend(self, state, db, *, user, mail=True, verification=True, deactivated=False):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings",
                return_value=_settings(verification=verification),
            ),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=mail),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
            patch(f"{_MODULE}._stage_sign_up_token") as stage_token,
        ):
            users.get_user_by_email.return_value = user
            users.is_deactivated.return_value = deactivated
            body = sign_up_service.resend_sign_up_verification_email("u@example.com", state, db)
        self.stage_token = stage_token
        return body, publishers.publish_sign_up_verification_requested

    def test_sends_a_new_email_to_an_account_awaiting_verification(self, mock_db, state):
        _, publish = self._resend(
            state, mock_db, user=MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com")
        )

        publish.assert_called_once_with(MOCK_USER_ID, mock_db)
        self.stage_token.assert_called_once_with(MOCK_USER_ID, "u@example.com", None, mock_db)
        mock_db.commit.assert_called_once()

    def test_a_second_request_within_the_cooldown_sends_nothing(self, mock_db, state):
        user = MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com")
        self._resend(state, mock_db, user=user)
        _, publish = self._resend(state, mock_db, user=user)

        publish.assert_not_called()

    @pytest.mark.parametrize(
        "user",
        [
            None,
            MagicMock(id=MOCK_USER_ID, active=True, email_verified=True),
            MagicMock(id=MOCK_USER_ID, active=False, email_verified=True),
        ],
    )
    def test_an_address_that_is_not_awaiting_verification_sends_nothing(self, mock_db, state, user):
        _, publish = self._resend(state, mock_db, user=user)

        publish.assert_not_called()

    def test_a_deactivated_account_gets_nothing(self, mock_db, state):
        _, publish = self._resend(
            state,
            mock_db,
            user=MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com"),
            deactivated=True,
        )

        publish.assert_not_called()

    @pytest.mark.parametrize(("mail", "verification"), [(False, True), (True, False)])
    def test_nothing_is_sent_without_mail_or_without_verification(self, mock_db, state, mail, verification):
        _, publish = self._resend(
            state,
            mock_db,
            user=MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com"),
            mail=mail,
            verification=verification,
        )

        publish.assert_not_called()

    def test_an_unreachable_cooldown_store_skips_the_send(self, mock_db):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        _, publish = self._resend(
            state, mock_db, user=MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com")
        )

        publish.assert_not_called()

    def test_every_outcome_answers_the_same(self, mock_db, state):
        sent, _ = self._resend(
            state, mock_db, user=MagicMock(id=MOCK_USER_ID, active=False, email_verified=False, email="u@example.com")
        )
        unknown, _ = self._resend(MemoryState(), mock_db, user=None)

        assert sent == unknown


class TestExistingAccountNoticeCooldown:
    def _signup_with_a_taken_email(self, state, db, *, owner_id=_USER_3):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.stage_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
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
        self._signup_with_a_taken_email(state, mock_db, owner_id=_USER_3)
        _, other = self._signup_with_a_taken_email(state, mock_db, owner_id=_USER_4)

        other.publish_sign_up_existing_account.assert_called_once()

    def test_an_unreachable_state_store_skips_the_notice_without_changing_the_answer(self, mock_db):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")

        result, publishers = self._signup_with_a_taken_email(broken, mock_db)

        publishers.publish_sign_up_existing_account.assert_not_called()
        assert result.next_step


class TestSignupWithATakenUsername:
    @staticmethod
    def _signup(state, db, *, username_holder, email_holder, insert_conflicts=True, username_holder_after_race=None):
        """Run a sign-up against a mocked users module and return it, with the users mock and the publishers."""
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            users.get_user_by_username.side_effect = [username_holder, username_holder_after_race]
            users.get_user_by_email.return_value = email_holder
            if insert_conflicts:
                users.stage_signup_user.side_effect = core_exceptions.ConflictError("Unable to create user.")
            else:
                users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID)
            try:
                result = sign_up_service.signup(_signup_user(), state, db)
            finally:
                captured = (users, publishers)
        return result, captured

    def test_a_taken_username_is_refused_whatever_the_email(self, mock_db, state):
        for email_holder in (None, MagicMock(id=_USER_3)):
            with pytest.raises(core_exceptions.ConflictError, match="That username is already taken"):
                self._signup(state, mock_db, username_holder=MagicMock(id=_USER_4), email_holder=email_holder)

    def test_a_taken_username_does_not_tell_the_email_owner_or_create_anything(self, mock_db, state):
        publishers = MagicMock()
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers", publishers),
            pytest.raises(core_exceptions.ConflictError),
        ):
            users.get_user_by_username.return_value = MagicMock(id=_USER_4)
            users.get_user_by_email.return_value = MagicMock(id=_USER_3)
            sign_up_service.signup(_signup_user(), state, mock_db)

        users.get_user_by_email.assert_not_called()
        users.stage_signup_user.assert_not_called()
        publishers.publish_sign_up_existing_account.assert_not_called()

    def test_a_free_username_with_a_registered_email_answers_200_and_stages_the_notice(self, mock_db, state):
        result, (_users, publishers) = self._signup(
            state, mock_db, username_holder=None, email_holder=MagicMock(id=_USER_3)
        )

        assert result.next_step
        publishers.publish_sign_up_existing_account.assert_called_once_with(_USER_3, mock_db)

    def test_a_username_taken_while_the_insert_raced_is_refused(self, mock_db, state):
        with pytest.raises(core_exceptions.ConflictError, match="That username is already taken"):
            self._signup(
                state,
                mock_db,
                username_holder=None,
                email_holder=MagicMock(id=_USER_3),
                username_holder_after_race=MagicMock(id=_USER_4),
            )


class TestExistingAccountEmail:
    def test_is_addressed_to_the_existing_owner(self, mock_db):
        owner = MagicMock(email="owner@example.com", preferred_language="en")
        owner.name = "Owner"
        with patch(f"{_MODULE}.users_integration.get_user", return_value=owner):
            message = sign_up_service.prepare_sign_up_existing_account_email(_USER_3, "https://app.example", mock_db)

        assert message is not None
        recipient, _subject, html_content, text_content = message
        assert recipient == "owner@example.com"
        assert "https://app.example/login" in html_content
        assert "https://app.example/login" in text_content

    def test_a_missing_owner_sends_nothing(self, mock_db):
        with patch(f"{_MODULE}.users_integration.get_user", return_value=None):
            assert (
                sign_up_service.prepare_sign_up_existing_account_email(_USER_3, "https://app.example", mock_db) is None
            )


class TestSignupPasswordPolicy:
    def test_a_password_is_refused_when_the_address_must_be_verified(self, mock_db, state):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(verification=True)
            ),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            sign_up_service.signup(_signup_user(), state, mock_db)

        users.stage_signup_user.assert_not_called()

    def test_a_missing_password_is_refused_when_verification_is_off(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            pytest.raises(core_exceptions.PasswordRequiredError) as refused,
        ):
            sign_up_service.signup(_signup_user(with_password=False), state, mock_db)

        assert refused.value.status_code == 400
        assert refused.value.code == "password-required"

        users.stage_signup_user.assert_not_called()

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
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.request_sign_up_verification_email"),
        ):
            users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID)
            sign_up_service.signup(_signup_user(with_password=False), state, mock_db)

        assert users.stage_signup_user.call_args.args[0].password is None


def _claim(*, previous_email=None):
    return MagicMock(id=tid("t1"), user_id=MOCK_USER_ID, email="u@example.com", previous_email=previous_email)


class TestConfirmSignUp:
    @pytest.fixture
    def deps(self):
        names = [
            "credentials_integration",
            "sessions_integration",
            "users_integration",
            "password_reset_tokens_integration",
            "security_generation_integration",
        ]
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
            mocks["users_integration"].get_user.return_value = MagicMock(
                id=MOCK_USER_ID, active=False, access_type="regular"
            )
            mocks["users_integration"].is_deactivated.return_value = False
            mocks["credentials_integration"].validate_and_hash_password_for_user.return_value = "hashed"
            yield mocks | {"verify_token": verify_token}

    def test_the_password_replaces_any_existing_hash_and_ends_sessions(self, deps, mock_db):
        result = sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        creds = deps["credentials_integration"]
        creds.validate_and_hash_password_for_user.assert_called_once()
        assert creds.validate_and_hash_password_for_user.call_args.args[2] == "ChosenPass1!"
        assert creds.validate_and_hash_password_for_user.call_args.kwargs == {
            "username": deps["users_integration"].get_user.return_value.username,
            "email": deps["users_integration"].get_user.return_value.email,
        }
        creds.set_local_password_hash.assert_called_once_with(MOCK_USER_ID, "hashed", mock_db, change_required=False)
        deps["sessions_integration"].delete_sessions_by_user.assert_called_once_with(MOCK_USER_ID, mock_db)
        deps["password_reset_tokens_integration"].revoke_unused_tokens.assert_called_once_with(MOCK_USER_ID, mock_db)
        deps["users_integration"].stage_email_verification.assert_called_once()
        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN

    def test_a_sign_up_pending_approval_awaits_it(self, deps, mock_db):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings",
                return_value=_settings(verification=True, approval=True),
            ),
            patch(f"{_MODULE}.request_sign_up_admin_approval"),
        ):
            result = sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        assert result.next_step is sign_up_schema.SignUpNextStep.AWAIT_APPROVAL

    def test_the_token_is_verified_as_a_sign_up_token(self, deps, mock_db):
        sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        deps["verify_token"].assert_called_once_with("tok", mock_db, email_change=False)

    def test_a_password_failing_the_policy_is_a_policy_error(self, deps, mock_db):
        deps[
            "credentials_integration"
        ].validate_and_hash_password_for_user.side_effect = credentials_contracts.PasswordTooCommonError()

        with pytest.raises(credentials_contracts.PasswordTooCommonError):
            sign_up_service.confirm_sign_up("tok", "weakweak", mock_db)

        mock_db.commit.assert_not_called()
        deps["credentials_integration"].set_local_password_hash.assert_not_called()

    def test_an_activated_account_without_a_password_chooses_one(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(id=MOCK_USER_ID, active=True, access_type="regular")
        deps["credentials_integration"].has_local_password.return_value = False

        sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        deps["credentials_integration"].set_local_password_hash.assert_called_once_with(
            MOCK_USER_ID, "hashed", mock_db, change_required=False
        )

    @pytest.mark.parametrize("active", [True, False])
    def test_an_account_that_does_not_take_a_password_refuses_one(self, deps, mock_db, active):
        deps["users_integration"].get_user.return_value = MagicMock(
            id=MOCK_USER_ID, active=active, access_type="regular"
        )
        deps["users_integration"].is_deactivated.return_value = not active
        deps["credentials_integration"].has_local_password.return_value = True

        with pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        deps["credentials_integration"].set_local_password_hash.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_sign_up_token_with_verification_disabled_is_refused(self, deps, mock_db):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            pytest.raises(core_exceptions.EmailVerificationDisabledError),
        ):
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)


class TestSignUpOff:
    """With sign-up off, a resend and a real sign-up's confirmation are refused; an activated account still confirms."""

    @pytest.fixture
    def deps(self):
        names = [
            "credentials_integration",
            "users_integration",
            "sign_up_event_publishers",
            "core_email_cooldown",
            "sessions_integration",
            "password_reset_tokens_integration",
        ]
        mocks = {name: MagicMock() for name in names}
        settings = _settings(verification=True)
        settings.signup_enabled = False
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(f"{_MODULE}.verify_sign_up_token") as verify_token,
            patch.multiple(_MODULE, **mocks),
        ):
            verify_token.return_value = _claim()
            mocks["users_integration"].is_deactivated.return_value = False
            mocks["credentials_integration"].validate_and_hash_password_for_user.return_value = "hashed"
            mocks["credentials_integration"].has_local_password.return_value = False
            yield mocks | {"verify_token": verify_token}

    def test_a_real_sign_up_confirmation_is_refused_and_writes_nothing(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(
            id=MOCK_USER_ID, active=False, access_type="regular"
        )

        with pytest.raises(core_exceptions.PermissionDeniedError) as refused:
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        assert refused.value.status_code == 403
        deps["credentials_integration"].set_local_password_hash.assert_not_called()
        deps["sessions_integration"].delete_sessions_by_user.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_refused_real_sign_up_rolls_back_the_claim_and_audits_the_failure(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(
            id=MOCK_USER_ID, active=False, access_type="regular"
        )

        with (
            patch(f"{_MODULE}.jasil_audit.record_detached") as record,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        mock_db.rollback.assert_called_once()
        record.assert_called_once()
        assert record.call_args.args == (sign_up_audit_actions.SIGN_UP_CONFIRM,)
        assert record.call_args.kwargs == {
            "outcome": jasil_audit.Outcome.FAILURE,
            "target_type": "user",
            "target_id": str(MOCK_USER_ID),
            "target_owner_id": str(MOCK_USER_ID),
            "details": sign_up_audit_actions.SignUpConfirmDetails(reason="sign_up_disabled"),
        }

    def test_an_activated_passwordless_account_still_chooses_its_password(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(id=MOCK_USER_ID, active=True, access_type="regular")

        result = sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        deps["credentials_integration"].set_local_password_hash.assert_called_once_with(
            MOCK_USER_ID, "hashed", mock_db, change_required=False
        )
        mock_db.commit.assert_called_once()
        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN

    def test_the_breach_check_runs_before_the_claim_for_either_account(self, deps, mock_db):
        deps["users_integration"].get_user.return_value = MagicMock(
            id=MOCK_USER_ID, active=False, access_type="regular"
        )
        order: list[str] = []
        deps["credentials_integration"].reject_breached_password.side_effect = lambda *a, **k: order.append("breach")
        deps["verify_token"].side_effect = lambda *a, **k: (order.append("claim"), _claim())[1]

        with pytest.raises(core_exceptions.PermissionDeniedError):
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)

        assert order == ["breach", "claim"]

    def test_a_resend_is_refused_like_the_sign_up_request(self, deps, mock_db, state):
        with pytest.raises(core_exceptions.PermissionDeniedError) as refused:
            sign_up_service.resend_sign_up_verification_email("u@example.com", state, mock_db)

        assert refused.value.status_code == 403
        deps["users_integration"].get_user_by_email.assert_not_called()
        deps["sign_up_event_publishers"].publish_sign_up_verification_requested.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_the_refusal_is_the_one_the_sign_up_request_gives(self, deps, mock_db, state):
        with pytest.raises(core_exceptions.PermissionDeniedError) as signed_up:
            sign_up_service.signup(_signup_user(), state, mock_db)
        deps["users_integration"].get_user.return_value = MagicMock(
            id=MOCK_USER_ID, active=False, access_type="regular"
        )
        with pytest.raises(core_exceptions.PermissionDeniedError) as confirmed:
            sign_up_service.confirm_sign_up("tok", "ChosenPass1!", mock_db)
        with pytest.raises(core_exceptions.PermissionDeniedError) as resent:
            sign_up_service.resend_sign_up_verification_email("u@example.com", state, mock_db)

        assert signed_up.value.detail == confirmed.value.detail == resent.value.detail

    def test_an_email_change_confirmation_is_not_affected(self, deps, mock_db):
        deps["verify_token"].return_value = _claim(previous_email="old@example.com")
        deps["users_integration"].get_user.return_value = MagicMock(id=MOCK_USER_ID, active=True)

        result = sign_up_service.confirm_email_change("tok", mock_db)

        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN


class TestConfirmEmailChange:
    @pytest.fixture
    def deps(self):
        names = ["credentials_integration", "sessions_integration", "users_integration"]
        mocks = {name: MagicMock() for name in names}
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.verify_sign_up_token") as verify_token,
            patch.multiple(_MODULE, **mocks),
            patch(f"{_MODULE}.sign_up_event_publishers") as publishers,
        ):
            verify_token.return_value = _claim(previous_email="old@example.com")
            mocks["users_integration"].get_user.return_value = MagicMock(id=MOCK_USER_ID, active=True)
            yield mocks | {"verify_token": verify_token, "publishers": publishers}

    def test_the_address_is_switched_and_the_account_signs_in_again(self, deps, mock_db):
        result = sign_up_service.confirm_email_change("tok", mock_db)

        deps["verify_token"].assert_called_once_with("tok", mock_db, email_change=True)
        deps["users_integration"].stage_confirmed_email_change.assert_called_once_with(
            MOCK_USER_ID, "u@example.com", mock_db
        )
        deps["publishers"].publish_email_changed.assert_called_once_with(MOCK_USER_ID, tid("t1"), mock_db)
        deps["users_integration"].stage_email_verification.assert_called_once()
        deps["credentials_integration"].set_local_password_hash.assert_not_called()
        deps["sessions_integration"].delete_sessions_by_user.assert_not_called()
        mock_db.commit.assert_called_once()
        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN


class TestVerifySignUpTokenBump:
    """A sign-up confirmation or an email change bumps the generation before the claim writes."""

    @staticmethod
    def _plain():
        return sign_up_contracts.SignUpTokenClaim(
            id=tid("t"), user_id=MOCK_USER_ID, email="u@example.com", previous_email=None
        )

    @staticmethod
    def _change(generation=0):
        return sign_up_contracts.EmailChangeClaim(
            id=tid("t"),
            user_id=MOCK_USER_ID,
            email="new@example.com",
            previous_email="old@example.com",
            security_generation=generation,
        )

    @staticmethod
    def _verify(claim, *, email_change, usable=True):
        mocks = MagicMock()
        with (
            patch(f"{_MODULE}.sign_up_crud.get_usable_sign_up_token", return_value=claim if usable else None),
            patch(f"{_MODULE}.sign_up_crud.claim_sign_up_token", return_value=claim if usable else None) as claim_token,
            patch(f"{_MODULE}.security_generation_integration.stage_bump") as bump,
            patch(f"{_MODULE}.jasil_audit.record_detached"),
        ):
            mocks.attach_mock(bump, "bump")
            mocks.attach_mock(claim_token, "claim")
            with contextlib.suppress(core_exceptions.InvalidInputError):
                sign_up_service.verify_sign_up_token("tok", MagicMock(), email_change=email_change)
        return [call[0] for call in mocks.mock_calls], bump

    def test_a_sign_up_confirmation_bumps_before_the_claim(self):
        names, bump = self._verify(self._plain(), email_change=False)

        assert names == ["bump", "claim"]
        bump.assert_called_once()
        assert bump.call_args.args[0] == MOCK_USER_ID

    def test_an_email_change_bumps_before_the_claim(self):
        names, _ = self._verify(self._change(), email_change=True)

        assert names == ["bump", "claim"]

    def test_an_email_change_from_an_earlier_generation_neither_bumps_nor_claims(self, security_generations):
        security_generations.generations[MOCK_USER_ID] = 1

        names, bump = self._verify(self._change(0), email_change=True)

        assert names == []
        bump.assert_not_called()

    def test_an_unusable_token_does_not_bump(self):
        names, _ = self._verify(self._plain(), email_change=False, usable=False)

        assert names == ["claim"]

    @pytest.mark.parametrize(
        ("claim", "email_change"), [(_plain.__func__(), True), (_change.__func__(), False)], ids=["sign-up", "change"]
    )
    def test_a_token_of_the_other_kind_is_refused_untouched(self, claim, email_change):
        names, bump = self._verify(claim, email_change=email_change)

        assert names == []
        bump.assert_not_called()


class TestSignupNextStep:
    @pytest.mark.parametrize(
        ("verification", "approval", "expected"),
        [
            (False, False, sign_up_schema.SignUpNextStep.SIGN_IN),
            (True, False, sign_up_schema.SignUpNextStep.CHECK_EMAIL),
            (True, True, sign_up_schema.SignUpNextStep.CHECK_EMAIL),
            (False, True, sign_up_schema.SignUpNextStep.AWAIT_APPROVAL),
        ],
    )
    def test_the_next_step_follows_the_policy_alone(self, mock_db, state, verification, approval, expected):
        with (
            patch(
                f"{_MODULE}.server_settings_integration.get_server_settings",
                return_value=_settings(verification=verification, approval=approval),
            ),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_MODULE}.users_integration", **_FREE_USERNAME) as users,
            patch(f"{_MODULE}.sign_up_event_publishers"),
        ):
            users.stage_signup_user.return_value = MagicMock(id=MOCK_USER_ID, pending_admin_approval=approval)
            result = sign_up_service.signup(_signup_user(with_password=not verification), state, mock_db)

        assert result.next_step is expected

    def test_a_resend_always_says_to_check_the_email(self, mock_db, state):
        with (
            patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
            patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=False),
        ):
            result = sign_up_service.resend_sign_up_verification_email("a@example.com", state, mock_db)

        assert result.next_step is sign_up_schema.SignUpNextStep.CHECK_EMAIL
