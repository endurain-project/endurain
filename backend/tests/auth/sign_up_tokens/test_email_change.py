"""Tests for the pending email change carried by sign-up tokens, against a real database."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.computation as token_hashing
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.models as users_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session, ensure_user
from tests.auth.sign_up_tokens.ids import tid

_OWNER_EMAIL = f"user{MOCK_USER_ID.hex}@example.com"
_OTHER_EMAIL = f"user{OTHER_USER_ID.hex}@example.com"

_USER_99 = uuid.UUID("00000000-0000-4000-8000-000000000099")

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, MOCK_USER_ID)
    ensure_user(factory, OTHER_USER_ID)
    session.query(users_models.Users).update({"preferred_language": "en"})
    session.commit()
    yield session
    session.close()


@pytest.fixture
def mail_configured():
    with patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True) as configured:
        yield configured


def _tokens(db, user_id=MOCK_USER_ID):
    return (
        db.query(sign_up_models.SignUpToken).filter_by(user_id=user_id).order_by(sign_up_models.SignUpToken.created_at)
    )


def _add_token(
    db,
    *,
    token_id,
    token,
    user_id=MOCK_USER_ID,
    email,
    previous_email,
    expires_in=timedelta(hours=1),
    used=False,
    security_generation=0,
):
    now = datetime.now(UTC)
    is_change = previous_email is not None
    db.add(
        sign_up_models.SignUpToken(
            id=token_id,
            user_id=user_id,
            token_hash=token_hashing.sha256_hex(token),
            created_at=now,
            expires_at=now + expires_in,
            used=used,
            email=email,
            previous_email=previous_email,
            security_generation=security_generation,
            change_id=token_id if is_change else None,
            revert_until=now + timedelta(days=7) if is_change else None,
            confirmed_at=now if used else None,
        )
    )
    db.commit()


class TestCreateSignUpTokenStoresAddresses:
    def test_a_pending_change_stores_both_addresses_and_uses_up_earlier_tokens(self, db):
        _add_token(db, token_id=tid("old"), token="old", email=_OWNER_EMAIL, previous_email=None)

        token = sign_up_service.create_sign_up_token(
            MOCK_USER_ID, "new@example.com", "event-1", db, previous_email=_OWNER_EMAIL
        )

        rows = {row.id: row for row in _tokens(db)}
        assert rows[tid("old")].used is True
        fresh = next(row for row in rows.values() if row.id != tid("old"))
        assert fresh.used is False
        assert (fresh.email, fresh.previous_email) == ("new@example.com", _OWNER_EMAIL)
        assert fresh.token_hash == token_hashing.sha256_hex(token)

    def test_a_sign_up_token_records_only_the_address_it_proves(self, db):
        sign_up_service.create_sign_up_token(MOCK_USER_ID, _OWNER_EMAIL, "event-1", db)

        row = _tokens(db).one()
        assert (row.email, row.previous_email) == (_OWNER_EMAIL, None)


class TestRequestEmailChange:
    def test_without_mail_nothing_is_staged(self, db):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(_PUBLISH) as publish,
        ):
            assert sign_up_service.request_email_change(MOCK_USER_ID, "new@example.com", _OWNER_EMAIL, db) is False

        assert _tokens(db).count() == 0
        publish.assert_not_called()

    def test_with_mail_the_pending_token_and_event_are_staged_without_committing(self, db, mail_configured):
        _add_token(db, token_id=tid("old"), token="old", email=_OWNER_EMAIL, previous_email=None)

        with patch(_PUBLISH) as publish:
            assert sign_up_service.request_email_change(MOCK_USER_ID, "new@example.com", _OWNER_EMAIL, db) is True
        db.rollback()

        assert [row.id for row in _tokens(db)] == [tid("old")]
        assert _tokens(db).one().used is False
        assert [call.args[:2] for call in publish.call_args_list] == [
            ("auth.email_change_requested", {"user_id": str(MOCK_USER_ID)}),
            ("auth.email_change_verification_requested", {"user_id": str(MOCK_USER_ID)}),
        ]

    def test_the_staged_token_replaces_the_earlier_one_once_committed(self, db, mail_configured):
        _add_token(db, token_id=tid("old"), token="old", email=_OWNER_EMAIL, previous_email=None)

        with patch(_PUBLISH):
            sign_up_service.request_email_change(MOCK_USER_ID, "new@example.com", _OWNER_EMAIL, db)
        db.commit()

        pending = sign_up_service.get_pending_email_changes([MOCK_USER_ID], db)
        assert pending[MOCK_USER_ID].email == "new@example.com"
        assert [row.used for row in _tokens(db)] == [True, False]


class TestPrepareEmailChangeVerificationEmail:
    def test_nothing_pending_returns_none_and_issues_no_token(self, db):
        assert sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db) is None
        assert _tokens(db).count() == 0

    def test_an_unknown_user_returns_none(self, db):
        assert sign_up_service.prepare_email_change_verification_email(_USER_99, "event-1", _HOST, db) is None

    def test_the_pending_token_is_reissued_to_the_pending_address(self, db):
        _add_token(db, token_id=tid("pending"), token="p", email="new@example.com", previous_email=_OWNER_EMAIL)

        message = sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db)

        assert message is not None
        recipient, _subject, html_content, _text = message
        assert recipient == "new@example.com"
        rows = {row.id: row for row in _tokens(db)}
        assert rows[tid("pending")].used is True
        fresh = next(row for row in rows.values() if row.id != tid("pending"))
        assert fresh.used is False
        assert (fresh.email, fresh.previous_email) == ("new@example.com", _OWNER_EMAIL)
        assert f"{_HOST}/confirm-email-change?token=" in html_content

    def test_an_expired_pending_change_is_not_reissued(self, db):
        _add_token(
            db,
            token_id=tid("gone"),
            token="g",
            email="new@example.com",
            previous_email=_OWNER_EMAIL,
            expires_in=timedelta(hours=-1),
        )

        assert sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db) is None


def _link_token(message) -> str:
    return message[2].split("?token=")[1].split('"')[0].split("<")[0].split("&")[0]


class TestRetriedMailEvent:
    """The event is delivered at least once, so preparing it again must not break the link already mailed."""

    def _claim(self, db, token: str):
        claimed = sign_up_crud.claim_sign_up_token(token_hashing.sha256_hex(token), db)
        db.commit()
        return claimed

    def test_a_retried_email_change_mails_the_same_link_and_it_still_works(self, db):
        _add_token(db, token_id=tid("pending"), token="p", email="new@example.com", previous_email=_OWNER_EMAIL)

        first = _link_token(sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db))
        second = _link_token(
            sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db)
        )

        assert second == first
        assert self._claim(db, first) is not None

    def test_a_retried_sign_up_verification_mails_the_same_link_and_it_still_works(self, db):
        first = _link_token(sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-1", _HOST, db))
        second = _link_token(sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-1", _HOST, db))

        assert second == first
        assert self._claim(db, first) is not None

    def test_a_new_request_replaces_the_earlier_link(self, db):
        first = _link_token(sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-1", _HOST, db))
        second = _link_token(sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-2", _HOST, db))

        assert second != first
        assert self._claim(db, first) is None
        assert self._claim(db, second) is not None

    def test_a_retry_of_an_older_request_does_not_revoke_the_newer_link(self, db):
        sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-1", _HOST, db)
        newer = _link_token(sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-2", _HOST, db))

        sign_up_service.prepare_sign_up_verification_email(MOCK_USER_ID, "event-1", _HOST, db)

        assert self._claim(db, newer) is not None


class TestVerifyEmailOfAPendingChange:
    @pytest.fixture(autouse=True)
    def settings(self):
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
        with patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings):
            yield

    @staticmethod
    def _activate(db, user_id=MOCK_USER_ID):
        user = db.get(users_models.Users, user_id)
        user.active = True
        user.email_verified = False
        db.commit()

    def test_the_address_is_switched_and_verified_and_the_notice_carries_ids_only(self, db):
        self._activate(db)
        _add_token(db, token_id=tid("t1"), token="plain", email="New@Example.com", previous_email=_OWNER_EMAIL)

        with patch(_PUBLISH) as publish:
            result = sign_up_service.confirm_email_change("plain", db)

        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN
        db.expire_all()
        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.email, user.email_verified) == ("new@example.com", True)
        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_changed"
        assert publish.call_args.args[1] == {"user_id": str(MOCK_USER_ID), "token_id": str(tid("t1"))}

    def test_an_address_claimed_by_another_account_conflicts_and_the_claim_is_rolled_back(self, db):
        self._activate(db)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OTHER_EMAIL, previous_email=_OWNER_EMAIL)

        with patch(_PUBLISH) as publish, pytest.raises(core_exceptions.ConflictError):
            sign_up_service.confirm_email_change("plain", db)
        # get_db rolls the session back on an unhandled exception.
        db.rollback()

        assert _tokens(db).one().used is False
        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL
        publish.assert_not_called()

    def test_an_expired_pending_token_cannot_be_confirmed(self, db):
        self._activate(db)
        _add_token(
            db,
            token_id=tid("t1"),
            token="plain",
            email="new@example.com",
            previous_email=_OWNER_EMAIL,
            expires_in=timedelta(hours=-1),
        )

        with patch(_PUBLISH) as publish, pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.confirm_email_change("plain", db)

        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL
        publish.assert_not_called()

    def test_a_sign_up_token_is_refused_and_left_usable(self, db):
        self._activate(db)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)

        with patch(_PUBLISH) as publish, pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.confirm_email_change("plain", db)
        db.rollback()

        assert _tokens(db).one().used is False
        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL
        publish.assert_not_called()


class TestVerifyEmailOnAnInactiveAccount:
    """A link never activates an account an administrator deactivated, and never takes the sign-up path."""

    @staticmethod
    def _settings(*, verification, approval, enabled=True):
        return patch(
            f"{_SERVICE}.server_settings_integration.get_server_settings",
            return_value=MagicMock(
                signup_enabled=enabled,
                signup_require_email_verification=verification,
                signup_require_admin_approval=approval,
                password_length_regular_users=8,
                password_length_admin_users=12,
            ),
        )

    @staticmethod
    def _make_inactive(db, *, deactivated, email_verified=False, pending_approval=False):
        user = db.get(users_models.Users, MOCK_USER_ID)
        user.active = False
        user.email_verified = email_verified
        user.pending_admin_approval = pending_approval
        user.deactivated_at = datetime.now(UTC) if deactivated else None
        db.commit()

    @pytest.mark.parametrize(("verification", "approval"), [(False, False), (True, False), (True, True)])
    def test_an_email_change_link_switches_the_address_and_keeps_a_deactivated_account_inactive(
        self, db, mail_configured, verification, approval
    ):
        self._make_inactive(db, deactivated=True, email_verified=True)
        _add_token(db, token_id=tid("t1"), token="plain", email="New@Example.com", previous_email=_OWNER_EMAIL)

        with (
            self._settings(verification=verification, approval=approval),
            patch(_PUBLISH) as publish,
        ):
            result = sign_up_service.confirm_email_change("plain", db)

        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN
        db.expire_all()
        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.email, user.email_verified, user.active) == ("new@example.com", True, False)
        assert user.deactivated_at is not None
        assert [call.args[0] for call in publish.call_args_list] == ["auth.email_changed"]

    def test_a_sign_up_link_of_a_deactivated_account_is_refused_and_leaves_the_account_alone(self, db, mail_configured):
        self._make_inactive(db, deactivated=True)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)

        with (
            self._settings(verification=True, approval=False),
            patch(_PUBLISH) as publish,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)
        db.rollback()

        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.email_verified, user.active) == (False, False)
        assert _tokens(db).one().used is False
        publish.assert_not_called()

    def test_a_sign_up_awaiting_verification_is_activated_without_admin_approval(self, db, mail_configured):
        self._make_inactive(db, deactivated=False)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)

        with (
            self._settings(verification=True, approval=False),
            patch(_PUBLISH) as publish,
        ):
            result = sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)

        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN
        db.expire_all()
        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.active, user.email_verified, user.pending_admin_approval) == (True, True, False)
        publish.assert_not_called()

    def test_a_sign_up_awaiting_verification_goes_to_admin_approval_when_required(self, db, mail_configured):
        self._make_inactive(db, deactivated=False, pending_approval=True)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)

        with (
            self._settings(verification=True, approval=True),
            patch(f"{_SERVICE}.request_sign_up_admin_approval_emails") as approval_emails,
        ):
            result = sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)

        assert result.next_step is sign_up_schema.SignUpNextStep.AWAIT_APPROVAL
        db.expire_all()
        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.active, user.email_verified, user.pending_admin_approval) == (False, True, True)
        approval_emails.assert_called_once_with(MOCK_USER_ID, db)

    def test_a_sign_up_refused_while_sign_up_is_off_confirms_with_the_same_link_once_it_is_on(
        self, db, mail_configured
    ):
        self._make_inactive(db, deactivated=False)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)

        with (
            self._settings(verification=True, approval=False, enabled=False),
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)

        db.expire_all()
        assert _tokens(db).one().used is False
        assert db.get(users_models.Users, MOCK_USER_ID).active is False

        with self._settings(verification=True, approval=False), patch(_PUBLISH):
            result = sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)

        assert result.next_step is sign_up_schema.SignUpNextStep.SIGN_IN
        db.expire_all()
        user = db.get(users_models.Users, MOCK_USER_ID)
        assert (user.active, user.email_verified) == (True, True)
        assert _tokens(db).one().used is True


class TestVerifyEmailVoidsPasswordResetTokens:
    @staticmethod
    def _reset_token(db, *, user_id=MOCK_USER_ID):
        now = datetime.now(UTC)
        db.add(
            password_reset_models.PasswordResetToken(
                id=tid("reset-1"),
                user_id=user_id,
                token_hash="reset-hash",
                created_at=now,
                expires_at=now + timedelta(hours=1),
                used=False,
            )
        )
        db.commit()

    @staticmethod
    def _reset_used(db):
        db.expire_all()
        return db.get(password_reset_models.PasswordResetToken, tid("reset-1")).used

    def test_a_sign_up_confirmation_that_sets_a_password_voids_the_reset_token(self, db, mail_configured):
        user = db.get(users_models.Users, MOCK_USER_ID)
        user.active = False
        user.email_verified = False
        db.commit()
        self._reset_token(db)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)
        settings = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(_PUBLISH),
        ):
            sign_up_service.confirm_sign_up("plain", "ChosenPass1!", db)

        assert self._reset_used(db) is True

    def test_a_confirmed_email_change_voids_the_reset_token(self, db):
        user = db.get(users_models.Users, MOCK_USER_ID)
        user.active = True
        user.email_verified = False
        db.commit()
        self._reset_token(db)
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email="old@example.com")
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)

        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(_PUBLISH),
        ):
            sign_up_service.confirm_email_change("plain", db)

        assert self._reset_used(db) is True


class TestGetPendingEmailChanges:
    def test_returns_each_users_unexpired_pending_address(self, db):
        _add_token(
            db,
            token_id=tid("a"),
            token="a",
            user_id=MOCK_USER_ID,
            email="n7@example.com",
            previous_email=_OWNER_EMAIL,
        )
        _add_token(db, token_id=tid("b"), token="b", user_id=OTHER_USER_ID, email=_OTHER_EMAIL, previous_email=None)

        pending = sign_up_service.get_pending_email_changes([MOCK_USER_ID, OTHER_USER_ID], db)

        assert set(pending) == {MOCK_USER_ID}
        assert pending[MOCK_USER_ID].email == "n7@example.com"
        assert pending[MOCK_USER_ID].expires_at is not None

    def test_an_expired_or_used_token_is_not_pending(self, db):
        _add_token(
            db,
            token_id=tid("a"),
            token="a",
            user_id=MOCK_USER_ID,
            email="n@example.com",
            previous_email=_OWNER_EMAIL,
            expires_in=timedelta(hours=-1),
        )
        _add_token(
            db,
            token_id=tid("b"),
            token="b",
            user_id=OTHER_USER_ID,
            email="n@example.com",
            previous_email=_OTHER_EMAIL,
            used=True,
        )

        assert sign_up_service.get_pending_email_changes([MOCK_USER_ID, OTHER_USER_ID], db) == {}

    def test_no_users_is_an_empty_result(self, db):
        assert sign_up_service.get_pending_email_changes([], db) == {}


class TestRequestEmailChangeResend:
    @pytest.fixture
    def pending(self, db):
        _add_token(db, token_id=tid("a"), token="a", email="new@example.com", previous_email=_OWNER_EMAIL)

    def test_stages_the_verification_event_once_per_cooldown(self, db, pending, mail_configured):
        state = MemoryState()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)

        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_change_verification_requested"
        assert publish.call_args.args[1] == {"user_id": str(MOCK_USER_ID)}

    def test_is_a_no_op_when_nothing_is_pending(self, db, mail_configured):
        state = MemoryState()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)
            # The cooldown was not spent, so a later pending change can still be resent.
            _add_token(db, token_id=tid("a"), token="a", email="new@example.com", previous_email=_OWNER_EMAIL)
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)

        publish.assert_called_once()

    def test_is_a_no_op_without_mail(self, db, pending):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(_PUBLISH) as publish,
        ):
            sign_up_service.request_email_change_resend(MOCK_USER_ID, MemoryState(), db)

        publish.assert_not_called()

    def test_an_unreachable_state_store_skips_the_resend(self, db, pending, mail_configured):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(MOCK_USER_ID, broken, db)

        publish.assert_not_called()


class TestPrepareEmailChangedEmail:
    def test_goes_to_the_previous_address_and_masks_the_new_one(self, db):
        _add_token(
            db,
            token_id=tid("t1"),
            token="t",
            email="alice@example.org",
            previous_email=_OWNER_EMAIL,
            used=True,
        )

        message = sign_up_service.prepare_email_changed_email(MOCK_USER_ID, tid("t1"), _HOST, db)

        assert message is not None
        recipient, _subject, html_content, text_content = message
        assert recipient == _OWNER_EMAIL
        assert "a***@example.org" in html_content
        assert "a***@example.org" in text_content
        assert "alice@example.org" not in html_content + text_content

    def test_a_missing_token_or_user_is_skipped(self, db):
        assert sign_up_service.prepare_email_changed_email(MOCK_USER_ID, tid("missing"), _HOST, db) is None
        _add_token(db, token_id=tid("t1"), token="t", email="a@example.org", previous_email=_OWNER_EMAIL, used=True)
        assert sign_up_service.prepare_email_changed_email(_USER_99, tid("t1"), _HOST, db) is None

    def test_a_token_that_replaced_no_address_is_skipped(self, db):
        _add_token(db, token_id=tid("t1"), token="t", email=_OWNER_EMAIL, previous_email=None, used=True)

        assert sign_up_service.prepare_email_changed_email(MOCK_USER_ID, tid("t1"), _HOST, db) is None


class TestIntegrationService:
    def test_delegates_to_the_service(self, db):
        state = MagicMock()
        with (
            patch.object(sign_up_service, "request_email_change", return_value=True) as request,
            patch.object(sign_up_service, "get_pending_email_changes", return_value={}) as pending,
            patch.object(sign_up_service, "request_email_change_resend") as resend,
        ):
            assert sign_up_integration.request_email_change(MOCK_USER_ID, "n@example.com", "o@example.com", db) is True
            assert sign_up_integration.get_pending_email_changes([MOCK_USER_ID], db) == {}
            sign_up_integration.request_email_change_resend(MOCK_USER_ID, state, db)

        request.assert_called_once_with(MOCK_USER_ID, "n@example.com", "o@example.com", db)
        pending.assert_called_once_with([MOCK_USER_ID], db)
        resend.assert_called_once_with(MOCK_USER_ID, state, db)


def test_get_sign_up_token_by_id(db):
    _add_token(db, token_id=tid("t1"), token="t", email="a@example.org", previous_email=_OWNER_EMAIL, used=True)

    assert sign_up_crud.get_sign_up_token_by_id(tid("t1"), db).previous_email == _OWNER_EMAIL
    assert sign_up_crud.get_sign_up_token_by_id(tid("nope"), db) is None


class TestATokenServesOnlyItsOwnKind:
    """A link of the other kind is refused like an unknown token, and stays usable for its own route."""

    @staticmethod
    def _confirm_sign_up(db):
        return sign_up_service.confirm_sign_up("raw", "ChosenPass1!", db)

    @staticmethod
    def _confirm_change(db):
        return sign_up_service.confirm_email_change("raw", db)

    @pytest.mark.parametrize(
        ("previous_email", "confirm"),
        [(_OWNER_EMAIL, "_confirm_sign_up"), (None, "_confirm_change")],
        ids=["change-token-on-sign-up", "sign-up-token-on-change"],
    )
    def test_the_refusal_is_the_unknown_token_problem_and_nothing_is_consumed(self, db, previous_email, confirm):
        _add_token(db, token_id=tid("t"), token="raw", email="new@example.com", previous_email=previous_email)
        settings = MagicMock(signup_require_email_verification=True, signup_require_admin_approval=False)

        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(f"{_SERVICE}.security_generation_integration.stage_bump") as bump,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError) as refused,
        ):
            getattr(self, confirm)(db)
        db.rollback()

        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
            pytest.raises(core_exceptions.InvalidInputError) as unknown,
        ):
            sign_up_service.confirm_sign_up("never-issued", "ChosenPass1!", db)
        assert (refused.value.status_code, refused.value.code, refused.value.detail) == (
            unknown.value.status_code,
            unknown.value.code,
            unknown.value.detail,
        )
        assert _tokens(db).one().used is False
        bump.assert_not_called()
        audit.assert_audited("auth.sign_up.confirm", outcome="failure")


class TestSignUpPrehijack:
    def test_the_confirming_user_password_replaces_a_hash_staged_at_sign_up(self, db):
        """Whoever staged the account cannot keep a password: confirming sets the owner's."""
        user = db.get(users_models.Users, MOCK_USER_ID)
        user.active = False
        credentials_integration.set_local_password_hash(
            MOCK_USER_ID,
            credentials_integration.get_password_hasher().hash_password("AttackerPass1!"),
            db,
            change_required=False,
        )
        _add_token(db, token_id=tid("t1"), token="plain", email=_OWNER_EMAIL, previous_email=None)
        db.commit()
        settings = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
            patch(f"{_SERVICE}.sessions_integration") as sessions,
        ):
            sign_up_service.confirm_sign_up("plain", "OwnerChosen1!", db)

        db.expire_all()
        stored = credentials_integration.get_password_hash(MOCK_USER_ID, db)
        hasher = credentials_integration.get_password_hasher()
        assert credentials_integration.verify_and_update_password("OwnerChosen1!", stored, hasher)[0]
        assert not credentials_integration.verify_and_update_password("AttackerPass1!", stored, hasher)[0]
        assert db.get(users_models.Users, MOCK_USER_ID).active is True
        sessions.delete_sessions_by_user.assert_called_once_with(MOCK_USER_ID, db)


_VERIFY_EVENT = "auth.email_change_verification_requested"
_TAKEN_EVENT = "auth.email_change_address_taken"
_REQUESTED_EVENT = "auth.email_change_requested"


class TestSelfServiceEmailChange:
    """A held address is staged and read back like a free one; only the holder is mailed, and never a link."""

    @staticmethod
    def _request(db, email, state=None):
        with patch(_PUBLISH) as publish:
            result = sign_up_service.request_self_service_email_change(
                MOCK_USER_ID, email, _OWNER_EMAIL, state or MemoryState(), db
            )
        db.commit()
        return result, publish

    @staticmethod
    def _events(publish):
        return [(call.args[0], call.args[1]) for call in publish.call_args_list]

    def test_a_free_address_is_staged_and_mailed_a_link(self, db, mail_configured):
        result, publish = self._request(db, "free@example.com")

        assert result is True
        assert sign_up_service.get_pending_email_changes([MOCK_USER_ID], db)[MOCK_USER_ID].email == "free@example.com"
        assert self._events(publish) == [
            (_REQUESTED_EVENT, {"user_id": str(MOCK_USER_ID)}),
            (_VERIFY_EVENT, {"user_id": str(MOCK_USER_ID)}),
        ]

    def test_a_held_address_is_staged_the_same_way_and_only_its_holder_is_told(self, db, mail_configured):
        result, publish = self._request(db, _OTHER_EMAIL)

        assert result is True
        pending = sign_up_service.get_pending_email_changes([MOCK_USER_ID], db)[MOCK_USER_ID]
        assert pending.email == _OTHER_EMAIL
        assert self._events(publish) == [
            (_REQUESTED_EVENT, {"user_id": str(MOCK_USER_ID)}),
            (_TAKEN_EVENT, {"user_id": str(OTHER_USER_ID)}),
        ]

    def test_a_second_attempt_inside_the_cooldown_answers_the_same_and_tells_nobody(self, db, mail_configured):
        state = MemoryState()
        first, first_publish = self._request(db, _OTHER_EMAIL, state)
        second, second_publish = self._request(db, _OTHER_EMAIL, state)

        assert first is second is True
        assert sign_up_service.get_pending_email_changes([MOCK_USER_ID], db)[MOCK_USER_ID].email == _OTHER_EMAIL
        assert self._events(first_publish) == [
            (_REQUESTED_EVENT, {"user_id": str(MOCK_USER_ID)}),
            (_TAKEN_EVENT, {"user_id": str(OTHER_USER_ID)}),
        ]
        assert self._events(second_publish) == [(_REQUESTED_EVENT, {"user_id": str(MOCK_USER_ID)})]

    def test_an_unreachable_state_store_answers_the_same_and_tells_nobody(self, db, mail_configured):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")

        result, publish = self._request(db, _OTHER_EMAIL, broken)

        assert result is True
        assert sign_up_service.get_pending_email_changes([MOCK_USER_ID], db)[MOCK_USER_ID].email == _OTHER_EMAIL
        assert self._events(publish) == [(_REQUESTED_EVENT, {"user_id": str(MOCK_USER_ID)})]

    def test_without_mail_nothing_is_staged(self, db):
        with patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False):
            result, publish = self._request(db, _OTHER_EMAIL)

        assert result is False
        assert sign_up_service.get_pending_email_changes([MOCK_USER_ID], db) == {}
        publish.assert_not_called()

    def test_resending_a_held_address_tells_the_holder_and_never_mails_a_link(self, db, mail_configured):
        _add_token(db, token_id=tid("a"), token="a", email=_OTHER_EMAIL, previous_email=_OWNER_EMAIL)
        state = MemoryState()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)

        assert self._events(publish) == [(_TAKEN_EVENT, {"user_id": str(OTHER_USER_ID)})]

    def test_a_request_and_a_resend_share_the_holders_cooldown(self, db, mail_configured):
        state = MemoryState()
        self._request(db, _OTHER_EMAIL, state)
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(MOCK_USER_ID, state, db)

        publish.assert_not_called()

    def test_no_confirmation_link_is_made_for_an_address_another_account_holds(self, db):
        _add_token(db, token_id=tid("a"), token="a", email=_OTHER_EMAIL, previous_email=_OWNER_EMAIL)

        assert sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db) is None

    def test_a_link_is_still_made_for_a_free_address(self, db):
        _add_token(db, token_id=tid("a"), token="a", email="free@example.com", previous_email=_OWNER_EMAIL)

        message = sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db)

        assert message is not None and message[0] == "free@example.com"

    def test_the_account_never_moves_to_a_held_address(self, db, mail_configured):
        import modules.users.users.service as users_service

        self._request(db, _OTHER_EMAIL)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_confirmed_email_change(MOCK_USER_ID, _OTHER_EMAIL, db)
        db.rollback()
        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL


class TestEmailChangeSecurityGeneration:
    """A pending email change is a proof: a security change after the request ends it."""

    @pytest.fixture(autouse=True)
    def settings(self):
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
        with patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings):
            yield

    @staticmethod
    def _pending(db, *, security_generation):
        _add_token(
            db,
            token_id=tid("t1"),
            token="plain",
            email="new@example.com",
            previous_email=_OWNER_EMAIL,
            security_generation=security_generation,
        )

    def test_a_requested_change_is_stamped_with_the_current_generation(self, db, mail_configured, security_generations):
        security_generations.generations[MOCK_USER_ID] = 3

        with patch(_PUBLISH):
            sign_up_service.request_email_change(MOCK_USER_ID, "new@example.com", _OWNER_EMAIL, db)

        assert _tokens(db).one().security_generation == 3

    def test_a_sign_up_token_carries_no_stamp(self, db):
        sign_up_service.create_sign_up_token(MOCK_USER_ID, _OWNER_EMAIL, "event-1", db)

        assert _tokens(db).one().security_generation is None

    def test_a_change_requested_before_a_security_change_cannot_be_confirmed(self, db, security_generations):
        self._pending(db, security_generation=0)
        security_generations.stage_bump(MOCK_USER_ID, db)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.confirm_email_change("plain", db)

        db.expire_all()
        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL
        entry = audit.assert_audited("auth.sign_up.confirm", outcome="failure")
        assert entry.details == {"password_set": None, "reason": "security_changed"}

    def test_a_change_with_no_stamp_cannot_be_confirmed(self, db):
        self._pending(db, security_generation=None)

        with pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.confirm_email_change("plain", db)

        assert db.get(users_models.Users, MOCK_USER_ID).email == _OWNER_EMAIL

    def test_a_change_requested_after_the_security_change_is_confirmed(self, db, security_generations):
        security_generations.stage_bump(MOCK_USER_ID, db)
        self._pending(db, security_generation=1)

        with patch(_PUBLISH):
            sign_up_service.confirm_email_change("plain", db)

        db.expire_all()
        assert db.get(users_models.Users, MOCK_USER_ID).email == "new@example.com"

    def test_the_mailed_token_keeps_the_stamp_of_the_request(self, db):
        self._pending(db, security_generation=0)

        sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db)

        fresh = _tokens(db).filter_by(used=False).one()
        assert fresh.security_generation == 0

    def test_a_change_made_stale_is_not_mailed(self, db, security_generations):
        self._pending(db, security_generation=0)
        security_generations.stage_bump(MOCK_USER_ID, db)

        assert sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db) is None
        assert _tokens(db).filter_by(used=False).count() == 1
