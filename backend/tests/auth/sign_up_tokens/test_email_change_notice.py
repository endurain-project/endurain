"""The notice sent to the current address when an email change is requested, and its "this wasn't me" link."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.event_publishers as sign_up_publishers
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session, ensure_user

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"
_ACTION = "auth.email_change.cancel"


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
    with patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True):
        yield


def _pending(db, *, security_generation=0, expires_in=timedelta(hours=24), email="new@example.com"):
    now = datetime.now(UTC)
    db.add(
        sign_up_models.SignUpToken(
            id="t1",
            user_id=7,
            token_hash="hash",
            created_at=now,
            expires_at=now + expires_in,
            used=False,
            email=email,
            previous_email="user7@example.com",
            security_generation=security_generation,
            change_id="t1",
            revert_until=now + timedelta(days=7),
        )
    )
    db.commit()


def _link_token(db) -> str:
    message = sign_up_service.prepare_email_change_requested_email(7, _HOST, db)
    assert message is not None
    _recipient, _subject, html_body, _text = message
    return html_body.split("cancel-email-change?token=")[1].split('"')[0].split("<")[0].split("&")[0]


class TestRequestPublishesTheNotice:
    @pytest.mark.parametrize("held", [False, True])
    def test_a_self_service_request_stages_the_notice_for_a_free_and_a_held_address(self, db, mail_configured, held):
        if held:
            db.query(users_models.Users).filter_by(id=8).update({"email": "new@example.com"})
            db.commit()
        with patch(_PUBLISH) as publish:
            sign_up_service.request_self_service_email_change(
                7, "new@example.com", "user7@example.com", MagicMock(), db
            )

        assert sign_up_events.EMAIL_CHANGE_REQUESTED in [call.args[0] for call in publish.call_args_list]
        call = next(c for c in publish.call_args_list if c.args[0] == sign_up_events.EMAIL_CHANGE_REQUESTED)
        assert call.args[1] == {"user_id": 7}

    def test_an_administrators_change_does_not_stage_it(self, db, mail_configured):
        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change(7, "new@example.com", "user7@example.com", db)

        assert sign_up_events.EMAIL_CHANGE_REQUESTED not in [call.args[0] for call in publish.call_args_list]

    def test_the_publisher_carries_the_user_id_only(self):
        db = MagicMock()
        with patch(_PUBLISH) as publish:
            sign_up_publishers.publish_email_change_requested(7, db)

        assert publish.call_args.args[:2] == (sign_up_events.EMAIL_CHANGE_REQUESTED, {"user_id": 7})


class TestPrepareTheNotice:
    def test_goes_to_the_current_address_and_masks_the_new_one(self, db):
        _pending(db)

        recipient, subject, html_body, text_body = sign_up_service.prepare_email_change_requested_email(7, _HOST, db)

        assert recipient == "user7@example.com"
        assert subject
        for body in (html_body, text_body):
            assert "new@example.com" not in body
            assert f"{_HOST}/cancel-email-change?token=" in body

    def test_nothing_pending_sends_nothing(self, db):
        assert sign_up_service.prepare_email_change_requested_email(7, _HOST, db) is None

    def test_an_unknown_user_sends_nothing(self, db):
        assert sign_up_service.prepare_email_change_requested_email(99, _HOST, db) is None

    def test_a_change_made_stale_by_a_security_change_sends_nothing(self, db, security_generations):
        _pending(db, security_generation=0)
        security_generations.stage_bump(7, db)

        assert sign_up_service.prepare_email_change_requested_email(7, _HOST, db) is None

    def test_a_retry_mails_the_same_link(self, db):
        _pending(db)

        assert _link_token(db) == _link_token(db)


class TestCancel:
    @staticmethod
    def _cancel(db, token, *, sessions=2, keys=1):
        with (
            patch(f"{_SERVICE}.sessions_integration.delete_sessions_by_user", return_value=sessions) as delete_sessions,
            patch(f"{_SERVICE}.api_keys_integration.revoke_user_api_keys", return_value=keys) as revoke_keys,
        ):
            sign_up_service.cancel_email_change(token, db)
        return delete_sessions, revoke_keys

    def test_ends_the_change_the_sessions_and_the_keys_and_is_audited(self, db, security_generations):
        _pending(db)
        token = _link_token(db)

        with jasil_testing.capture_audit() as audit:
            delete_sessions, revoke_keys = self._cancel(db, token)

        db.expire_all()
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        assert security_generations.bumps == [7]
        delete_sessions.assert_called_once_with(7, db)
        revoke_keys.assert_called_once_with(7, db)
        entry = audit.assert_audited(_ACTION, target_type="user", target_id="7", target_owner_id="7")
        assert entry.details == {
            "sessions_revoked": 2,
            "api_keys_revoked": 1,
            "change_applied": False,
            "email_restored": False,
        }
        assert token not in repr(entry)

    def test_the_link_works_once(self, db):
        _pending(db)
        token = _link_token(db)
        self._cancel(db, token)

        with pytest.raises(core_exceptions.InvalidInputError):
            self._cancel(db, token)

    @pytest.mark.parametrize("token", ["", "garbage", "7.9999999999.deadbeef", "x.1.2", "t1.", ".abc", "t1.\u00e9"])
    def test_a_malformed_or_forged_token_is_refused_and_changes_nothing(self, db, security_generations, token):
        _pending(db)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            self._cancel(db, token)

        assert security_generations.bumps == []
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 1
        audit.assert_audited(_ACTION, outcome="failure")
