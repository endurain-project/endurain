"""The "this wasn't me" link of an email change: valid for 7 days, before and after the change is confirmed."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session, ensure_user

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"
_ACTION = "auth.email_change.cancel"
_OLD = "user7@example.com"
_NEW = "new@example.com"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, 7)
    ensure_user(factory, 8)
    session.query(users_models.Users).update({"preferred_language": "en", "active": True, "email_verified": False})
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def platform():
    """Mail is configured, the sign-up policy needs no verification and sessions and keys are counted."""
    settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
    with (
        patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True),
        patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
        patch(f"{_SERVICE}.sessions_integration.delete_sessions_by_user", return_value=2) as sessions,
        patch(f"{_SERVICE}.api_keys_integration.revoke_user_api_keys", return_value=1) as keys,
    ):
        yield MagicMock(sessions=sessions, keys=keys)


def _user(db, user_id=7):
    db.expire_all()
    return db.get(users_models.Users, user_id)


def _extract(html_body: str) -> str:
    return html_body.split("cancel-email-change?token=")[1].split('"')[0].split("<")[0].split("&")[0]


def _request(db, new=_NEW, previous=_OLD) -> str:
    """Request a change as the owner and return the link mailed to the current address."""
    with patch(_PUBLISH):
        sign_up_service.request_self_service_email_change(7, new, previous, MemoryState(), db)
    db.commit()
    message = sign_up_service.prepare_email_change_requested_email(7, _HOST, db)
    assert message is not None
    return _extract(message[2])


def _confirm(db, event="event-1") -> str:
    """Deliver the confirmation mail and open its link; return the id of the notice's token."""
    message = sign_up_service.prepare_email_change_verification_email(7, event, _HOST, db)
    assert message is not None
    raw = message[2].split("verify-email?token=")[1].split('"')[0].split("<")[0].split("&")[0]
    with patch(_PUBLISH) as publish:
        sign_up_service.verify_email(raw, None, db)
    return publish.call_args.args[1]["token_id"]


def _revert(db, token):
    return sign_up_service.cancel_email_change(token, db)


class TestTheLinkSurvivesConfirmation:
    def test_confirming_then_using_the_link_reverts_the_change(self, db, platform, security_generations):
        link = _request(db)
        _confirm(db)
        assert _user(db).email == _NEW

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert result.email_restored is True
        user = _user(db)
        assert (user.email, user.email_verified) == (_OLD, True)
        assert set(security_generations.bumps) == {7}
        platform.sessions.assert_called_once_with(7, db)
        platform.keys.assert_called_once_with(7, db)
        entry = audit.assert_audited(_ACTION, target_type="user", target_id="7", target_owner_id="7")
        assert entry.details["email_restored"] is True
        assert entry.details["change_applied"] is True

    def test_the_link_mailed_before_a_resend_still_works(self, db):
        link = _request(db)
        sign_up_service.prepare_email_change_verification_email(7, "first-delivery", _HOST, db)

        result = _revert(db, link)

        assert result.email_restored is False
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0

    def test_the_confirmation_notice_carries_the_same_link(self, db):
        link = _request(db)
        token_id = _confirm(db)

        message = sign_up_service.prepare_email_changed_email(7, token_id, _HOST, db)

        assert message is not None
        recipient, _subject, html_body, text_body = message
        assert recipient == _OLD
        assert _extract(html_body) == link
        assert f"{_HOST}/cancel-email-change?token={link}" in text_body

    def test_works_six_days_after_the_request_and_not_after_seven(self, db):
        link = _request(db)
        _confirm(db)

        with patch(f"{_SERVICE}.datetime") as clock, pytest.raises(core_exceptions.InvalidInputError):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=7, minutes=1)
            _revert(db, link)
        db.rollback()
        assert _user(db).email == _NEW

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=6)
            assert _revert(db, link).email_restored is True

    def test_works_once(self, db):
        link = _request(db)
        _confirm(db)
        _revert(db, link)

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, link)

    def test_a_change_purged_before_the_locked_read_is_refused(self, db, platform):
        # The purge job can delete the change's rows between the link check and the read under the generation lock.
        link = _request(db)
        _confirm(db)

        real = sign_up_service.sign_up_crud.get_email_change_tokens
        reads = iter([real, lambda *_: []])
        with (
            patch(f"{_SERVICE}.sign_up_crud.get_email_change_tokens", side_effect=lambda *a: next(reads)(*a)),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            _revert(db, link)

        platform.sessions.assert_not_called()

    def test_a_revert_after_a_later_change_is_refused(self, db, platform):
        first = _request(db)
        _confirm(db)
        second = _request(db, new="third@example.com", previous=_NEW)
        _confirm(db, event="event-2")

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, first)
        db.rollback()

        assert _user(db).email == "third@example.com"
        platform.sessions.assert_not_called()
        assert _revert(db, second).email_restored is True
        assert _user(db).email == _NEW

    def test_a_revert_while_a_later_change_is_pending_is_refused_and_leaves_it_alone(self, db, platform):
        first = _request(db)
        _confirm(db)
        _request(db, new="third@example.com", previous=_NEW)

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, first)
        db.rollback()

        assert _user(db).email == _NEW
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).one().email == "third@example.com"
        platform.sessions.assert_not_called()

    def test_a_revert_after_a_round_trip_back_to_the_same_address_is_refused(self, db, platform):
        first = _request(db)
        _confirm(db)
        _request(db, new="third@example.com", previous=_NEW)
        _confirm(db, event="event-2")
        _request(db, new=_NEW, previous="third@example.com")
        _confirm(db, event="event-3")

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, first)
        db.rollback()

        assert _user(db).email == _NEW
        platform.sessions.assert_not_called()

    def test_an_address_taken_meanwhile_is_not_restored_but_the_account_is_secured(
        self, db, platform, security_generations
    ):
        link = _request(db)
        _confirm(db)
        db.query(users_models.Users).filter_by(id=8).update({"email": _OLD})
        db.commit()

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert result.email_restored is False
        assert _user(db).email == _NEW
        assert 7 in security_generations.bumps
        platform.sessions.assert_called_once_with(7, db)
        platform.keys.assert_called_once_with(7, db)
        assert audit.assert_audited(_ACTION, target_id="7").details["email_restored"] is False


class TestTheLinkBeforeConfirmation:
    def test_cancels_the_pending_change(self, db, platform, security_generations):
        link = _request(db)

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert (result.email_restored, result.change_applied) == (False, False)
        assert _user(db).email == _OLD
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        assert 7 in security_generations.bumps
        platform.sessions.assert_called_once_with(7, db)
        assert audit.assert_audited(_ACTION, target_id="7").details["change_applied"] is False

    def test_works_once(self, db):
        link = _request(db)
        _revert(db, link)

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, link)

    def test_an_earlier_requests_link_does_not_cancel_a_later_request(self, db, platform):
        first = _request(db)
        _request(db, new="other@example.com")

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, first)
        db.rollback()

        pending = db.query(sign_up_models.SignUpToken).filter_by(used=False).one()
        assert pending.email == "other@example.com"
        platform.sessions.assert_not_called()

    def test_an_expired_unconfirmed_change_has_nothing_to_cancel(self, db):
        link = _request(db)

        with patch(f"{_SERVICE}.datetime") as clock, pytest.raises(core_exceptions.InvalidInputError):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=2)
            _revert(db, link)


class TestChangesTheOwnerDidNotRequest:
    def test_an_applied_change_notice_has_no_revert_link_and_no_link_can_be_made_for_it(self, db, platform):
        sign_up_service.request_email_change(7, _NEW, _OLD, db)
        db.commit()
        message = sign_up_service.prepare_email_change_verification_email(7, "event-1", _HOST, db)
        assert message is not None
        raw = message[2].split("verify-email?token=")[1].split('"')[0].split("<")[0].split("&")[0]
        with patch(_PUBLISH) as publish:
            sign_up_service.verify_email(raw, None, db)

        notice = sign_up_service.prepare_email_changed_email(7, publish.call_args.args[1]["token_id"], _HOST, db)

        assert notice is not None
        assert "cancel-email-change" not in notice[2] + notice[3]
        rows = db.query(sign_up_models.SignUpToken).all()
        assert all(row.change_id is None and row.revert_until is None for row in rows)
        for row in rows:
            forged = f"{row.id}.{sign_up_service._revert_mac(row.id, datetime.now(UTC) + timedelta(days=7))}"
            with pytest.raises(core_exceptions.InvalidInputError):
                _revert(db, forged)
        assert _user(db).email == _NEW
        platform.sessions.assert_not_called()

    def test_a_synced_change_notice_has_no_revert_link(self, db):
        sign_up_service.stage_email_changed_notice(7, _NEW, _OLD, db)
        db.commit()
        row = db.query(sign_up_models.SignUpToken).one()

        notice = sign_up_service.prepare_email_changed_email(7, row.id, _HOST, db)

        assert notice is not None
        assert "cancel-email-change" not in notice[2] + notice[3]
        assert (row.change_id, row.revert_until) == (None, None)


class TestRefusals:
    @pytest.mark.parametrize("token", ["", "garbage", "a.b", "7.9999999999.deadbeef", "x.1.2"])
    def test_a_malformed_or_forged_link_is_refused_and_changes_nothing(self, db, platform, token):
        _request(db)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, token)

        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 1
        platform.sessions.assert_not_called()
        audit.assert_audited(_ACTION, outcome="failure")

    def test_a_link_with_a_forged_proof_is_refused(self, db, platform):
        link = _request(db)
        change_id = link.split(".")[0]

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, f"{change_id}.forged")

        platform.sessions.assert_not_called()


class TestRowsOutliveTheRevertWindow:
    def test_an_email_change_row_is_kept_for_seven_days(self, db):
        _request(db)
        _confirm(db)

        now = datetime.now(UTC)
        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = now + timedelta(days=2)
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 0
            clock.now.return_value = now + timedelta(days=8)
            assert sign_up_service.delete_expired_sign_up_tokens(db) > 0
        assert db.query(sign_up_models.SignUpToken).count() == 0

    def test_a_sign_up_token_is_still_deleted_when_it_expires(self, db):
        sign_up_service.create_sign_up_token(7, _OLD, "event-1", db)

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=2)
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 1
