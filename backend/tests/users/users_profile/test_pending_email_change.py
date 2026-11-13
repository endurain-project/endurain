"""Tests for a pending email change from the profile and the admin edit, against a real database."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import core.exceptions as core_exceptions
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_profile.service as profile_service

_SID_9 = uuid.UUID(int=109)
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_MAIL = "modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured"
_STEP_UP = "modules.auth.account_security.integration_service.verify_step_up"
_OTHER_SESSIONS = "modules.auth.account_security.integration_service.delete_other_user_sessions"
_ALL_SESSIONS = "modules.auth.account_security.integration_service.delete_all_user_sessions"
_EVENT = "auth.email_change_verification_requested"
_TAKEN_EVENT = "auth.email_change_address_taken"
_REQUESTED_EVENT = "auth.email_change_requested"
_PROFILE = "modules.users.users_profile.service.get_profile"
_USER_ID = uuid.UUID(int=7)
_OTHER_USER_ID = uuid.UUID(int=8)
_ADMIN_ID = uuid.UUID(int=9)
_EMAIL = f"user{_USER_ID.hex}@example.com"
_OTHER_EMAIL = f"user{_OTHER_USER_ID.hex}@example.com"
_NAME = f"User {_USER_ID.hex[-12:]}"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    for user_id in (_USER_ID, _OTHER_USER_ID, _ADMIN_ID):
        ensure_user(factory, user_id)
    session.query(users_models.Users).update({"preferred_language": "en", "email_verified": True})
    session.commit()
    yield session
    session.close()


@pytest.fixture
def mail():
    with patch(_MAIL, return_value=True):
        yield


@pytest.fixture
def no_mail():
    with patch(_MAIL, return_value=False):
        yield


@pytest.fixture
def publish():
    with patch(_PUBLISH) as publish:
        yield publish


def _user(db, user_id=_USER_ID):
    db.expire_all()
    return db.get(users_models.Users, user_id)


def _unused_tokens(db, user_id=_USER_ID):
    db.expire_all()
    return db.query(sign_up_models.SignUpToken).filter_by(user_id=user_id, used=False).all()


def _change_email(db, email, *, user_id=_USER_ID, revoke_other_sessions=False, state=None):
    change = users_schema.EmailChange(
        email=email, step_up={"current_password": "pw"}, revoke_other_sessions=revoke_other_sessions
    )
    with patch(_STEP_UP), patch(_OTHER_SESSIONS) as other_sessions, patch(_PROFILE):
        profile_service.change_email(user_id, change, "sid", MagicMock(), state or MemoryState(), db)
    return other_sessions


class TestSelfServiceEmailChange:
    def test_the_address_and_verified_flag_stay_and_a_token_and_event_are_staged(self, db, mail, publish):
        _change_email(db, "New@Example.com")

        user = _user(db)
        assert (user.email, user.email_verified) == (_EMAIL, True)
        tokens = _unused_tokens(db)
        assert [(t.email, t.previous_email) for t in tokens] == [("new@example.com", _EMAIL)]
        assert [(call.args[0], call.args[1]) for call in publish.call_args_list] == [
            (_REQUESTED_EVENT, {"user_id": str(_USER_ID)}),
            (_EVENT, {"user_id": str(_USER_ID)}),
        ]

    def test_the_change_is_shown_as_pending_in_the_profile(self, db, mail, publish):
        _change_email(db, "new@example.com")

        with (
            patch("modules.users.users_profile.service.user_integrations_integration") as integrations,
            patch("modules.users.users_profile.service.users_privacy_settings_integration") as privacy,
            patch("modules.users.users_profile.service.credentials_integration") as credentials,
            patch("modules.users.users_profile.service.account_security_integration") as security,
        ):
            integrations.get_user_integrations.return_value = MagicMock(
                version=1, strava_token=None, garminconnect_token=None
            )
            privacy.get_privacy_settings.return_value = MagicMock(
                version=1,
                default_activity_visibility="public",
                discoverable=True,
                **{
                    f"hide_activity_{name}": False
                    for name in (
                        "start_time",
                        "location",
                        "map",
                        "hr",
                        "power",
                        "cadence",
                        "elevation",
                        "speed",
                        "pace",
                        "laps",
                        "workout_sets_steps",
                        "gear",
                    )
                },
            )
            credentials.has_local_password.return_value = True
            security.get_mfa_status.return_value = MagicMock(mfa_enabled=False)
            profile = profile_service.get_profile(_USER_ID, db)

        assert profile.pending_email == "new@example.com"
        assert profile.pending_email_expires_at is not None
        assert profile.email == _EMAIL

    def test_a_second_change_replaces_the_first(self, db, mail, publish):
        _change_email(db, "first@example.com")
        _change_email(db, "second@example.com")

        assert [t.email for t in _unused_tokens(db)] == ["second@example.com"]
        assert _user(db).email == _EMAIL

    def test_resubmitting_the_current_address_cancels_a_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        other_sessions = _change_email(db, _EMAIL.upper(), revoke_other_sessions=True)

        assert _unused_tokens(db) == []
        assert _user(db).email_verified is True
        other_sessions.assert_not_called()

    def test_an_address_of_another_account_is_pending_like_a_free_one_and_its_holder_is_told(self, db, mail, publish):
        _change_email(db, _OTHER_EMAIL.capitalize())

        assert [(t.email, t.previous_email) for t in _unused_tokens(db)] == [(_OTHER_EMAIL, _EMAIL)]
        assert _user(db).email == _EMAIL
        assert _user(db, _OTHER_USER_ID).email == _OTHER_EMAIL
        assert [(call.args[0], call.args[1]) for call in publish.call_args_list] == [
            (_REQUESTED_EVENT, {"user_id": str(_USER_ID)}),
            (_TAKEN_EVENT, {"user_id": str(_OTHER_USER_ID)}),
        ]

    def test_a_second_attempt_inside_the_hour_answers_the_same(self, db, mail, publish):
        state = MemoryState()

        _change_email(db, _OTHER_EMAIL, state=state)
        _change_email(db, _OTHER_EMAIL, state=state)

        assert [t.email for t in _unused_tokens(db)] == [_OTHER_EMAIL]
        assert [call.args[0] for call in publish.call_args_list] == [
            _REQUESTED_EVENT,
            _TAKEN_EVENT,
            _REQUESTED_EVENT,
        ]

    def test_a_taken_address_without_mail_is_a_conflict(self, db, no_mail, publish):
        with pytest.raises(core_exceptions.ConflictError):
            _change_email(db, _OTHER_EMAIL)

        assert _user(db).email == _EMAIL
        publish.assert_not_called()

    def test_without_mail_the_address_changes_at_once_unverified_and_tokens_are_revoked(self, db, publish):
        with patch(_MAIL, return_value=True):
            _change_email(db, "pending@example.com")
        assert len(_unused_tokens(db)) == 1
        publish.reset_mock()

        with patch(_MAIL, return_value=False):
            _change_email(db, "new@example.com")

        user = _user(db)
        assert (user.email, user.email_verified) == ("new@example.com", False)
        assert _unused_tokens(db) == []
        publish.assert_not_called()

    def test_a_requested_address_leaves_the_security_generation_alone(self, db, mail, publish, security_generations):
        _change_email(db, "new@example.com")

        assert security_generations.bumps == []

    def test_an_address_applied_at_once_advances_the_security_generation(
        self, db, no_mail, publish, security_generations
    ):
        _change_email(db, "new@example.com")

        assert security_generations.bumps == [_USER_ID]

    def test_other_sessions_are_revoked_when_asked(self, db, mail, publish):
        other_sessions = _change_email(db, "new@example.com", revoke_other_sessions=True)

        other_sessions.assert_called_once_with(_USER_ID, "sid", db)


class TestChangeEmailAnswersWithTheProfile:
    @staticmethod
    def _request(db, email):
        change = users_schema.EmailChange(email=email, step_up={"current_password": "pw"})
        with (
            patch(_STEP_UP),
            patch(_OTHER_SESSIONS),
            patch(_PROFILE) as get_profile,
        ):
            result = profile_service.change_email(_USER_ID, change, "sid", MagicMock(), MemoryState(), db)
        return result, get_profile

    def test_a_pending_change_returns_the_profile_read_after_the_commit(self, db, mail, publish):
        result, get_profile = self._request(db, "new@example.com")

        assert result is get_profile.return_value
        get_profile.assert_called_once_with(_USER_ID, db)
        assert len(_unused_tokens(db)) == 1

    def test_an_address_applied_without_mail_returns_the_profile(self, db, no_mail, publish):
        result, get_profile = self._request(db, "new@example.com")

        assert result is get_profile.return_value
        assert _user(db).email == "new@example.com"

    def test_the_current_address_cancelling_a_change_returns_the_profile(self, db, mail, publish):
        _change_email(db, "new@example.com")

        result, get_profile = self._request(db, _EMAIL)

        assert result is get_profile.return_value
        assert _unused_tokens(db) == []


class TestResendAndCancel:
    def test_cancelling_lapses_the_link_and_clears_the_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        profile_service.cancel_email_change(_USER_ID, db)

        assert _unused_tokens(db) == []
        assert _user(db).email == _EMAIL

    def test_resending_stages_the_event_once_per_cooldown(self, db, mail, publish):
        _change_email(db, "new@example.com")
        publish.reset_mock()
        state = MemoryState()

        profile_service.resend_email_change(_USER_ID, state, db)
        profile_service.resend_email_change(_USER_ID, state, db)

        publish.assert_called_once()
        assert publish.call_args.args[0] == _EVENT

    def test_resending_with_nothing_pending_does_nothing(self, db, mail, publish):
        profile_service.resend_email_change(_USER_ID, MemoryState(), db)

        publish.assert_not_called()


class TestPasswordResetWhilePending:
    def test_the_reset_still_targets_the_old_address(self, db, mail, publish):
        _change_email(db, "new@example.com")
        reset = "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_requested"

        with patch(reset) as requested:
            password_reset_service.request_password_reset_email("new@example.com", "203.0.113.7", "agent", db)
            password_reset_service.request_password_reset_email(_EMAIL, "203.0.113.7", "agent", db)

        assert [call.args[0] for call in requested.call_args_list] == [None, _USER_ID]


class TestAdminEmailEdit:
    @staticmethod
    def _edit(db, **overrides):
        current = users_service.require_user(_USER_ID, db)
        edit = users_schema.UserEdit.from_read(current).model_copy(update=overrides)
        with (
            patch(_ALL_SESSIONS) as sessions,
            patch("modules.users.users.service.account_security_integration.verify_step_up"),
        ):
            updated = users_service.edit_user(
                _USER_ID, edit, None, _ADMIN_ID, _SID_9, MagicMock(), db, if_match=str(current.version)
            )
        return updated, sessions

    def test_an_unchanged_email_edits_as_before(self, db, mail, publish):
        updated, sessions = self._edit(db, name="Renamed")

        assert updated.name == "Renamed"
        assert updated.pending_email is None
        publish.assert_not_called()
        sessions.assert_not_called()

    def test_a_changed_unverified_email_is_pending_and_ends_the_sessions(self, db, mail, publish):
        updated, sessions = self._edit(db, email="New@Example.com", email_verified=False)

        user = _user(db)
        assert (user.email, user.email_verified) == (_EMAIL, True)
        assert (updated.email, updated.email_verified) == (_EMAIL, True)
        assert updated.pending_email == "new@example.com"
        assert updated.pending_email_expires_at is not None
        assert [call.args[0] for call in publish.call_args_list] == ["auth.email_change_requested", _EVENT]
        sessions.assert_called_once_with(_USER_ID, db)

    def test_a_changed_email_marked_verified_applies_at_once_and_cancels_a_pending_change(self, db, mail, publish):
        _change_email(db, "pending@example.com")
        publish.reset_mock()

        updated, sessions = self._edit(db, email="New@Example.com", email_verified=True)

        user = _user(db)
        assert (user.email, user.email_verified) == ("new@example.com", True)
        assert updated.pending_email is None
        assert _unused_tokens(db) == []
        sessions.assert_called_once_with(_USER_ID, db)

    def test_an_applied_address_tells_the_previous_one(self, db, mail, publish):
        self._edit(db, email="New@Example.com", email_verified=True)

        notice = db.query(sign_up_models.SignUpToken).filter_by(user_id=_USER_ID).one()
        assert (notice.previous_email, notice.email, notice.used) == (_EMAIL, "new@example.com", True)
        publish.assert_called_once()
        assert publish.call_args.args[0] == "auth.email_changed"
        assert publish.call_args.args[1] == {"user_id": str(_USER_ID), "token_id": str(notice.id)}

    def test_without_mail_an_applied_address_stages_no_notice_and_voids_pending_links(self, db, no_mail, publish):
        with patch(_MAIL, return_value=True):
            _change_email(db, "pending@example.com")
        publish.reset_mock()

        self._edit(db, email="new@example.com", email_verified=True)

        assert _user(db).email == "new@example.com"
        assert _unused_tokens(db) == []
        publish.assert_not_called()

    def test_without_mail_a_changed_email_applies_unverified(self, db, no_mail, publish):
        updated, sessions = self._edit(db, email="new@example.com", email_verified=False)

        user = _user(db)
        assert (user.email, user.email_verified) == ("new@example.com", False)
        assert (updated.email, updated.email_verified) == ("new@example.com", False)
        assert updated.pending_email is None
        sessions.assert_called_once_with(_USER_ID, db)

    def test_deactivating_with_a_changed_email_leaves_no_link_that_could_reactivate(self, db, mail, publish):
        updated, _ = self._edit(db, email="new@example.com", email_verified=False, active=False)

        assert (_user(db).email, _user(db).active) == (_EMAIL, False)
        assert updated.pending_email is None
        assert _unused_tokens(db) == []

    def test_a_changed_email_of_another_account_is_a_conflict_and_changes_nothing(self, db, mail, publish):
        with pytest.raises(core_exceptions.ConflictError):
            self._edit(db, email=_OTHER_EMAIL, name="Renamed")

        assert _user(db).name == _NAME
        assert _unused_tokens(db) == []
        publish.assert_not_called()

    def test_the_admin_read_and_the_list_carry_the_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        assert users_service.require_user_with_pending_email(_USER_ID, db).pending_email == "new@example.com"
        listed = {user.id: user for user in users_service.list_users(db).items}
        assert listed[_USER_ID].pending_email == "new@example.com"
        assert listed[_OTHER_USER_ID].pending_email is None
