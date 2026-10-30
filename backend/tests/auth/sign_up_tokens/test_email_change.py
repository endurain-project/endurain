"""Tests for the pending email change carried by sign-up tokens, against a real database."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.computation as token_hashing
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session, ensure_user

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, 7)
    ensure_user(factory, 8)
    session.query(users_models.Users).update({"preferred_language": "en"})
    session.commit()
    yield session
    session.close()


@pytest.fixture
def mail_configured():
    with patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True) as configured:
        yield configured


def _tokens(db, user_id=7):
    return (
        db.query(sign_up_models.SignUpToken).filter_by(user_id=user_id).order_by(sign_up_models.SignUpToken.created_at)
    )


def _add_token(db, *, token_id, token, user_id=7, email, previous_email, expires_in=timedelta(hours=1), used=False):
    now = datetime.now(UTC)
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
        )
    )
    db.commit()


class TestCreateSignUpTokenStoresAddresses:
    def test_a_pending_change_stores_both_addresses_and_uses_up_earlier_tokens(self, db):
        _add_token(db, token_id="old", token="old", email="user7@example.com", previous_email=None)

        token = sign_up_service.create_sign_up_token(
            7, "new@example.com", "event-1", db, previous_email="user7@example.com"
        )

        rows = {row.id: row for row in _tokens(db)}
        assert rows["old"].used is True
        fresh = next(row for row in rows.values() if row.id != "old")
        assert fresh.used is False
        assert (fresh.email, fresh.previous_email) == ("new@example.com", "user7@example.com")
        assert fresh.token_hash == token_hashing.sha256_hex(token)

    def test_a_sign_up_token_records_only_the_address_it_proves(self, db):
        sign_up_service.create_sign_up_token(7, "user7@example.com", "event-1", db)

        row = _tokens(db).one()
        assert (row.email, row.previous_email) == ("user7@example.com", None)


class TestRequestEmailChange:
    def test_without_mail_nothing_is_staged(self, db):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(_PUBLISH) as publish,
        ):
            assert sign_up_service.request_email_change(7, "new@example.com", "user7@example.com", db) is False

        assert _tokens(db).count() == 0
        publish.assert_not_called()

    def test_with_mail_the_pending_token_and_event_are_staged_without_committing(self, db, mail_configured):
        _add_token(db, token_id="old", token="old", email="user7@example.com", previous_email=None)

        with patch(_PUBLISH) as publish:
            assert sign_up_service.request_email_change(7, "new@example.com", "user7@example.com", db) is True
        db.rollback()

        assert [row.id for row in _tokens(db)] == ["old"]
        assert _tokens(db).one().used is False
        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_change_verification_requested"
        assert publish.call_args.args[1] == {"user_id": 7}

    def test_the_staged_token_replaces_the_earlier_one_once_committed(self, db, mail_configured):
        _add_token(db, token_id="old", token="old", email="user7@example.com", previous_email=None)

        with patch(_PUBLISH):
            sign_up_service.request_email_change(7, "new@example.com", "user7@example.com", db)
        db.commit()

        pending = sign_up_service.get_pending_email_changes([7], db)
        assert pending[7].email == "new@example.com"
        assert [row.used for row in _tokens(db)] == [True, False]


class TestPrepareEmailChangeVerificationEmail:
    def test_nothing_pending_returns_none_and_issues_no_token(self, db):
        assert sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db) is None
        assert _tokens(db).count() == 0

    def test_an_unknown_user_returns_none(self, db):
        assert sign_up_service.prepare_email_change_verification_email(99, "event-1", _HOST, db) is None

    def test_the_pending_token_is_reissued_to_the_pending_address(self, db):
        _add_token(db, token_id="pending", token="p", email="new@example.com", previous_email="user7@example.com")

        message = sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db)

        assert message is not None
        recipient, _subject, html_content, _text = message
        assert recipient == "new@example.com"
        rows = {row.id: row for row in _tokens(db)}
        assert rows["pending"].used is True
        fresh = next(row for row in rows.values() if row.id != "pending")
        assert fresh.used is False
        assert (fresh.email, fresh.previous_email) == ("new@example.com", "user7@example.com")
        assert f"{_HOST}/verify-email?token=" in html_content

    def test_an_expired_pending_change_is_not_reissued(self, db):
        _add_token(
            db,
            token_id="gone",
            token="g",
            email="new@example.com",
            previous_email="user7@example.com",
            expires_in=timedelta(hours=-1),
        )

        assert sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db) is None


def _link_token(message) -> str:
    return message[2].split("verify-email?token=")[1].split('"')[0].split("<")[0].split("&")[0]


class TestRetriedMailEvent:
    """The event is delivered at least once, so preparing it again must not break the link already mailed."""

    def _claim(self, db, token: str):
        claimed = sign_up_crud.claim_sign_up_token(token_hashing.sha256_hex(token), db)
        db.commit()
        return claimed

    def test_a_retried_email_change_mails_the_same_link_and_it_still_works(self, db):
        _add_token(db, token_id="pending", token="p", email="new@example.com", previous_email="user7@example.com")

        first = _link_token(sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db))
        second = _link_token(sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db))

        assert second == first
        assert self._claim(db, first) is not None

    def test_a_retried_sign_up_verification_mails_the_same_link_and_it_still_works(self, db):
        first = _link_token(sign_up_service.prepare_sign_up_verification_email(7, "event-1", _HOST, db))
        second = _link_token(sign_up_service.prepare_sign_up_verification_email(7, "event-1", _HOST, db))

        assert second == first
        assert self._claim(db, first) is not None

    def test_a_new_request_replaces_the_earlier_link(self, db):
        first = _link_token(sign_up_service.prepare_sign_up_verification_email(7, "event-1", _HOST, db))
        second = _link_token(sign_up_service.prepare_sign_up_verification_email(7, "event-2", _HOST, db))

        assert second != first
        assert self._claim(db, first) is None
        assert self._claim(db, second) is not None

    def test_a_retry_of_an_older_request_does_not_revoke_the_newer_link(self, db):
        sign_up_service.prepare_sign_up_verification_email(7, "event-1", _HOST, db)
        newer = _link_token(sign_up_service.prepare_sign_up_verification_email(7, "event-2", _HOST, db))

        sign_up_service.prepare_sign_up_verification_email(7, "event-1", _HOST, db)

        assert self._claim(db, newer) is not None


class TestVerifyEmailOfAPendingChange:
    @pytest.fixture(autouse=True)
    def settings(self):
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
        with patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings):
            yield

    @staticmethod
    def _activate(db, user_id=7):
        user = db.get(users_models.Users, user_id)
        user.active = True
        user.email_verified = False
        db.commit()

    def test_the_address_is_switched_and_verified_and_the_notice_carries_ids_only(self, db):
        self._activate(db)
        _add_token(db, token_id="t1", token="plain", email="New@Example.com", previous_email="user7@example.com")

        with patch(_PUBLISH) as publish:
            result = sign_up_service.verify_email("plain", db)

        assert result.message == "Email verified successfully."
        db.expire_all()
        user = db.get(users_models.Users, 7)
        assert (user.email, user.email_verified) == ("new@example.com", True)
        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_changed"
        assert publish.call_args.args[1] == {"user_id": 7, "token_id": "t1"}

    def test_an_address_claimed_by_another_account_conflicts_and_the_claim_is_rolled_back(self, db):
        self._activate(db)
        _add_token(db, token_id="t1", token="plain", email="user8@example.com", previous_email="user7@example.com")

        with patch(_PUBLISH) as publish, pytest.raises(core_exceptions.ConflictError):
            sign_up_service.verify_email("plain", db)
        # get_db rolls the session back on an unhandled exception.
        db.rollback()

        assert _tokens(db).one().used is False
        assert db.get(users_models.Users, 7).email == "user7@example.com"
        publish.assert_not_called()

    def test_an_expired_pending_token_cannot_be_confirmed(self, db):
        self._activate(db)
        _add_token(
            db,
            token_id="t1",
            token="plain",
            email="new@example.com",
            previous_email="user7@example.com",
            expires_in=timedelta(hours=-1),
        )

        with patch(_PUBLISH) as publish, pytest.raises(core_exceptions.InvalidInputError):
            sign_up_service.verify_email("plain", db)

        assert db.get(users_models.Users, 7).email == "user7@example.com"
        publish.assert_not_called()

    def test_a_sign_up_token_leaves_the_address_alone_and_sends_no_notice(self, db):
        self._activate(db)
        _add_token(db, token_id="t1", token="plain", email="user7@example.com", previous_email=None)

        with patch(_PUBLISH) as publish:
            sign_up_service.verify_email("plain", db)

        assert db.get(users_models.Users, 7).email == "user7@example.com"
        publish.assert_not_called()


class TestVerifyEmailOnAnInactiveAccount:
    """A link never activates an account an administrator deactivated, and never takes the sign-up path."""

    @staticmethod
    def _settings(*, verification, approval):
        return patch(
            f"{_SERVICE}.server_settings_integration.get_server_settings",
            return_value=MagicMock(
                signup_require_email_verification=verification, signup_require_admin_approval=approval
            ),
        )

    @staticmethod
    def _make_inactive(db, *, deactivated, email_verified=False, pending_approval=False):
        user = db.get(users_models.Users, 7)
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
        _add_token(db, token_id="t1", token="plain", email="New@Example.com", previous_email="user7@example.com")

        with (
            self._settings(verification=verification, approval=approval),
            patch(_PUBLISH) as publish,
            patch(f"{_SERVICE}.notifications_integration") as notifications,
        ):
            result = sign_up_service.verify_email("plain", db)

        assert result.message == "Email verified successfully."
        assert result.admin_approval_required is None
        db.expire_all()
        user = db.get(users_models.Users, 7)
        assert (user.email, user.email_verified, user.active) == ("new@example.com", True, False)
        assert user.deactivated_at is not None
        assert [call.args[0] for call in publish.call_args_list] == ["auth.email_changed"]
        notifications.create_admin_sign_up_approval_notifications.assert_not_called()
        notifications.push_notification.assert_not_called()

    def test_a_verification_link_marks_a_deactivated_account_verified_without_activating_it(self, db, mail_configured):
        self._make_inactive(db, deactivated=True)
        _add_token(db, token_id="t1", token="plain", email="user7@example.com", previous_email=None)

        with (
            self._settings(verification=False, approval=False),
            patch(_PUBLISH) as publish,
            patch(f"{_SERVICE}.notifications_integration") as notifications,
        ):
            result = sign_up_service.verify_email("plain", db)

        assert result.message == "Email verified successfully."
        db.expire_all()
        user = db.get(users_models.Users, 7)
        assert (user.email_verified, user.active) == (True, False)
        publish.assert_not_called()
        notifications.create_admin_sign_up_approval_notifications.assert_not_called()

    def test_a_sign_up_awaiting_verification_is_activated_without_admin_approval(self, db, mail_configured):
        self._make_inactive(db, deactivated=False)
        _add_token(db, token_id="t1", token="plain", email="user7@example.com", previous_email=None)

        with (
            self._settings(verification=True, approval=False),
            patch(_PUBLISH) as publish,
            patch(f"{_SERVICE}.notifications_integration") as notifications,
        ):
            result = sign_up_service.verify_email("plain", db)

        assert result.message == "Email verified successfully. You can now log in."
        db.expire_all()
        user = db.get(users_models.Users, 7)
        assert (user.active, user.email_verified, user.pending_admin_approval) == (True, True, False)
        publish.assert_not_called()
        notifications.create_admin_sign_up_approval_notifications.assert_not_called()

    def test_a_sign_up_awaiting_verification_goes_to_admin_approval_when_required(self, db, mail_configured):
        self._make_inactive(db, deactivated=False, pending_approval=True)
        _add_token(db, token_id="t1", token="plain", email="user7@example.com", previous_email=None)

        with (
            self._settings(verification=True, approval=True),
            patch(f"{_SERVICE}.request_sign_up_admin_approval_emails") as approval_emails,
            patch(f"{_SERVICE}.notifications_integration") as notifications,
        ):
            notifications.create_admin_sign_up_approval_notifications.return_value = []
            result = sign_up_service.verify_email("plain", db)

        assert result.admin_approval_required is True
        db.expire_all()
        user = db.get(users_models.Users, 7)
        assert (user.active, user.email_verified, user.pending_admin_approval) == (False, True, True)
        approval_emails.assert_called_once_with(7, db)
        notifications.create_admin_sign_up_approval_notifications.assert_called_once()


class TestGetPendingEmailChanges:
    def test_returns_each_users_unexpired_pending_address(self, db):
        _add_token(db, token_id="a", token="a", user_id=7, email="n7@example.com", previous_email="user7@example.com")
        _add_token(db, token_id="b", token="b", user_id=8, email="user8@example.com", previous_email=None)

        pending = sign_up_service.get_pending_email_changes([7, 8], db)

        assert set(pending) == {7}
        assert pending[7].email == "n7@example.com"
        assert pending[7].expires_at is not None

    def test_an_expired_or_used_token_is_not_pending(self, db):
        _add_token(
            db,
            token_id="a",
            token="a",
            user_id=7,
            email="n@example.com",
            previous_email="user7@example.com",
            expires_in=timedelta(hours=-1),
        )
        _add_token(
            db, token_id="b", token="b", user_id=8, email="n@example.com", previous_email="user8@example.com", used=True
        )

        assert sign_up_service.get_pending_email_changes([7, 8], db) == {}

    def test_no_users_is_an_empty_result(self, db):
        assert sign_up_service.get_pending_email_changes([], db) == {}


class TestRequestEmailChangeResend:
    @pytest.fixture
    def pending(self, db):
        _add_token(db, token_id="a", token="a", email="new@example.com", previous_email="user7@example.com")

    def test_stages_the_verification_event_once_per_cooldown(self, db, pending, mail_configured):
        state = MemoryState()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(7, state, db)
            sign_up_service.request_email_change_resend(7, state, db)

        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_change_verification_requested"
        assert publish.call_args.args[1] == {"user_id": 7}

    def test_is_a_no_op_when_nothing_is_pending(self, db, mail_configured):
        state = MemoryState()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(7, state, db)
            # The cooldown was not spent, so a later pending change can still be resent.
            _add_token(db, token_id="a", token="a", email="new@example.com", previous_email="user7@example.com")
            sign_up_service.request_email_change_resend(7, state, db)

        publish.assert_called_once()

    def test_is_a_no_op_without_mail(self, db, pending):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            patch(_PUBLISH) as publish,
        ):
            sign_up_service.request_email_change_resend(7, MemoryState(), db)

        publish.assert_not_called()

    def test_an_unreachable_state_store_skips_the_resend(self, db, pending, mail_configured):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(7, broken, db)

        publish.assert_not_called()


class TestPrepareEmailChangedEmail:
    def test_goes_to_the_previous_address_and_masks_the_new_one(self, db):
        _add_token(
            db,
            token_id="t1",
            token="t",
            email="alice@example.org",
            previous_email="user7@example.com",
            used=True,
        )

        message = sign_up_service.prepare_email_changed_email(7, "t1", _HOST, db)

        assert message is not None
        recipient, _subject, html_content, text_content = message
        assert recipient == "user7@example.com"
        assert "a***@example.org" in html_content
        assert "a***@example.org" in text_content
        assert "alice@example.org" not in html_content + text_content

    def test_a_missing_token_or_user_is_skipped(self, db):
        assert sign_up_service.prepare_email_changed_email(7, "missing", _HOST, db) is None
        _add_token(db, token_id="t1", token="t", email="a@example.org", previous_email="user7@example.com", used=True)
        assert sign_up_service.prepare_email_changed_email(99, "t1", _HOST, db) is None

    def test_a_token_that_replaced_no_address_is_skipped(self, db):
        _add_token(db, token_id="t1", token="t", email="user7@example.com", previous_email=None, used=True)

        assert sign_up_service.prepare_email_changed_email(7, "t1", _HOST, db) is None


class TestIntegrationService:
    def test_delegates_to_the_service(self, db):
        state = MagicMock()
        with (
            patch.object(sign_up_service, "request_email_change", return_value=True) as request,
            patch.object(sign_up_service, "get_pending_email_changes", return_value={}) as pending,
            patch.object(sign_up_service, "request_email_change_resend") as resend,
        ):
            assert sign_up_integration.request_email_change(7, "n@example.com", "o@example.com", db) is True
            assert sign_up_integration.get_pending_email_changes([7], db) == {}
            sign_up_integration.request_email_change_resend(7, state, db)

        request.assert_called_once_with(7, "n@example.com", "o@example.com", db)
        pending.assert_called_once_with([7], db)
        resend.assert_called_once_with(7, state, db)


def test_get_sign_up_token_by_id(db):
    _add_token(db, token_id="t1", token="t", email="a@example.org", previous_email="user7@example.com", used=True)

    assert sign_up_crud.get_sign_up_token_by_id("t1", db).previous_email == "user7@example.com"
    assert sign_up_crud.get_sign_up_token_by_id("nope", db) is None
