"""Tests for a pending email change from the profile and the admin edit, against a real database."""

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

_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_MAIL = "modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured"
_STEP_UP = "modules.auth.account_security.integration_service.verify_step_up"
_OTHER_SESSIONS = "modules.auth.account_security.integration_service.delete_other_user_sessions"
_ALL_SESSIONS = "modules.auth.account_security.integration_service.delete_all_user_sessions"
_EVENT = "auth.email_change_verification_requested"
_PROFILE = "modules.users.users_profile.service.get_profile"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    for user_id in (7, 8, 9):
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


def _user(db, user_id=7):
    db.expire_all()
    return db.get(users_models.Users, user_id)


def _unused_tokens(db, user_id=7):
    db.expire_all()
    return db.query(sign_up_models.SignUpToken).filter_by(user_id=user_id, used=False).all()


def _change_email(db, email, *, user_id=7, revoke_other_sessions=False):
    change = users_schema.EmailChange(
        email=email, current_password="pw", mfa_code=None, revoke_other_sessions=revoke_other_sessions
    )
    with patch(_STEP_UP), patch(_OTHER_SESSIONS) as other_sessions, patch(_PROFILE):
        profile_service.change_email(user_id, change, "sid", MagicMock(), db)
    return other_sessions


class TestSelfServiceEmailChange:
    def test_the_address_and_verified_flag_stay_and_a_token_and_event_are_staged(self, db, mail, publish):
        _change_email(db, "New@Example.com")

        user = _user(db)
        assert (user.email, user.email_verified) == ("user7@example.com", True)
        tokens = _unused_tokens(db)
        assert [(t.email, t.previous_email) for t in tokens] == [("new@example.com", "user7@example.com")]
        publish.assert_called_once()
        assert (publish.call_args.args[0], publish.call_args.args[1]) == (_EVENT, {"user_id": 7})

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
            profile = profile_service.get_profile(7, db)

        assert profile.pending_email == "new@example.com"
        assert profile.pending_email_expires_at is not None
        assert profile.email == "user7@example.com"

    def test_a_second_change_replaces_the_first(self, db, mail, publish):
        _change_email(db, "first@example.com")
        _change_email(db, "second@example.com")

        assert [t.email for t in _unused_tokens(db)] == ["second@example.com"]
        assert _user(db).email == "user7@example.com"

    def test_resubmitting_the_current_address_cancels_a_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        other_sessions = _change_email(db, "USER7@example.com", revoke_other_sessions=True)

        assert _unused_tokens(db) == []
        assert _user(db).email_verified is True
        other_sessions.assert_not_called()

    def test_an_address_of_another_account_is_a_conflict_and_stages_nothing(self, db, mail, publish):
        with pytest.raises(core_exceptions.ConflictError):
            _change_email(db, "user8@example.com")

        assert _unused_tokens(db) == []
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

    def test_other_sessions_are_revoked_when_asked(self, db, mail, publish):
        other_sessions = _change_email(db, "new@example.com", revoke_other_sessions=True)

        other_sessions.assert_called_once_with(7, "sid", db)


class TestChangeEmailAnswersWithTheProfile:
    @staticmethod
    def _request(db, email):
        change = users_schema.EmailChange(email=email, current_password="pw", mfa_code=None)
        with (
            patch(_STEP_UP),
            patch(_OTHER_SESSIONS),
            patch(_PROFILE) as get_profile,
        ):
            result = profile_service.change_email(7, change, "sid", MagicMock(), db)
        return result, get_profile

    def test_a_pending_change_returns_the_profile_read_after_the_commit(self, db, mail, publish):
        result, get_profile = self._request(db, "new@example.com")

        assert result is get_profile.return_value
        get_profile.assert_called_once_with(7, db)
        assert len(_unused_tokens(db)) == 1

    def test_an_address_applied_without_mail_returns_the_profile(self, db, no_mail, publish):
        result, get_profile = self._request(db, "new@example.com")

        assert result is get_profile.return_value
        assert _user(db).email == "new@example.com"

    def test_the_current_address_cancelling_a_change_returns_the_profile(self, db, mail, publish):
        _change_email(db, "new@example.com")

        result, get_profile = self._request(db, "user7@example.com")

        assert result is get_profile.return_value
        assert _unused_tokens(db) == []


class TestResendAndCancel:
    def test_cancelling_lapses_the_link_and_clears_the_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        profile_service.cancel_email_change(7, db)

        assert _unused_tokens(db) == []
        assert _user(db).email == "user7@example.com"

    def test_resending_stages_the_event_once_per_cooldown(self, db, mail, publish):
        _change_email(db, "new@example.com")
        publish.reset_mock()
        state = MemoryState()

        profile_service.resend_email_change(7, state, db)
        profile_service.resend_email_change(7, state, db)

        publish.assert_called_once()
        assert publish.call_args.args[0] == _EVENT

    def test_resending_with_nothing_pending_does_nothing(self, db, mail, publish):
        profile_service.resend_email_change(7, MemoryState(), db)

        publish.assert_not_called()


class TestPasswordResetWhilePending:
    def test_the_reset_still_targets_the_old_address(self, db, mail, publish):
        _change_email(db, "new@example.com")
        state = MemoryState()
        reset = "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_requested"

        with patch.object(password_reset_service, "_may_reset_password", return_value=True), patch(reset) as requested:
            password_reset_service.request_password_reset_email("new@example.com", state, db)
            requested.assert_not_called()
            password_reset_service.request_password_reset_email("user7@example.com", state, db)

        requested.assert_called_once_with(7, db)


class TestAdminEmailEdit:
    @staticmethod
    def _edit(db, **overrides):
        current = users_service.require_user(7, db)
        edit = users_schema.UsersEdit.from_read(current).model_copy(update=overrides)
        with patch(_ALL_SESSIONS) as sessions:
            updated = users_service.edit_user(7, edit, 9, db, if_match=str(current.version))
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
        assert (user.email, user.email_verified) == ("user7@example.com", True)
        assert (updated.email, updated.email_verified) == ("user7@example.com", True)
        assert updated.pending_email == "new@example.com"
        assert updated.pending_email_expires_at is not None
        publish.assert_called_once()
        sessions.assert_called_once_with(7, db)

    def test_a_changed_email_marked_verified_applies_at_once_and_cancels_a_pending_change(self, db, mail, publish):
        _change_email(db, "pending@example.com")
        publish.reset_mock()

        updated, sessions = self._edit(db, email="New@Example.com", email_verified=True)

        user = _user(db)
        assert (user.email, user.email_verified) == ("new@example.com", True)
        assert updated.pending_email is None
        assert _unused_tokens(db) == []
        publish.assert_not_called()
        sessions.assert_called_once_with(7, db)

    def test_without_mail_a_changed_email_applies_unverified(self, db, no_mail, publish):
        updated, sessions = self._edit(db, email="new@example.com", email_verified=False)

        user = _user(db)
        assert (user.email, user.email_verified) == ("new@example.com", False)
        assert (updated.email, updated.email_verified) == ("new@example.com", False)
        assert updated.pending_email is None
        sessions.assert_called_once_with(7, db)

    def test_deactivating_with_a_changed_email_leaves_no_link_that_could_reactivate(self, db, mail, publish):
        updated, _ = self._edit(db, email="new@example.com", email_verified=False, active=False)

        assert (_user(db).email, _user(db).active) == ("user7@example.com", False)
        assert updated.pending_email is None
        assert _unused_tokens(db) == []

    def test_a_changed_email_of_another_account_is_a_conflict_and_changes_nothing(self, db, mail, publish):
        with pytest.raises(core_exceptions.ConflictError):
            self._edit(db, email="user8@example.com", name="Renamed")

        assert _user(db).name == "User 7"
        assert _unused_tokens(db) == []
        publish.assert_not_called()

    def test_the_admin_read_and_the_list_carry_the_pending_change(self, db, mail, publish):
        _change_email(db, "new@example.com")

        assert users_service.require_user_with_pending_email(7, db).pending_email == "new@example.com"
        listed = {user.id: user for user in users_service.list_users(db).items}
        assert listed[7].pending_email == "new@example.com"
        assert listed[8].pending_email is None
