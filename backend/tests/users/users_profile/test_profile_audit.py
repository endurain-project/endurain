"""Audit rows of the user's own profile, privacy and email-change requests, read back from the database."""

import pytest
from jasil.audit.models import AuditLog
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.auth.account_security.integration_service as account_security_integration
import modules.users.users.schema as users_schema
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.service as profile_service
from tests._factories.server_settings import edit_mail_settings
from tests._factories.users import PASSWORD, make_user


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, name="Old Name", city="Porto")
        db.commit()
    return created


def _rows(committed_sessions, action):
    with committed_sessions() as db:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.action_id == action.id)))
        db.expunge_all()
    return rows


class TestProfileUpdate:
    def test_the_row_names_the_fields_whose_value_changed(self, committed_sessions, owner):
        with committed_sessions() as db:
            profile_service.edit_profile(
                owner.id, users_schema.ProfileUpdate(name="New Name", city="Porto"), db, if_match='"1"'
            )

        (row,) = _rows(committed_sessions, profile_audit_actions.PROFILE_UPDATE)
        assert row.details == {"changed_fields": ["name"]}
        assert (row.target_type, row.target_id, row.target_owner_id) == ("user", str(owner.id), str(owner.id))

    def test_an_edit_that_changes_nothing_writes_no_row(self, committed_sessions, owner):
        with committed_sessions() as db:
            profile_service.edit_profile(
                owner.id, users_schema.ProfileUpdate(name="Old Name", city="Porto"), db, if_match='"1"'
            )

        assert _rows(committed_sessions, profile_audit_actions.PROFILE_UPDATE) == []

    def test_a_refused_edit_writes_no_row(self, committed_sessions, owner):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            profile_service.edit_profile(owner.id, users_schema.ProfileUpdate(name="x"), db, if_match='"7"')

        assert _rows(committed_sessions, profile_audit_actions.PROFILE_UPDATE) == []


class TestPrivacyUpdate:
    def test_the_row_names_the_settings_whose_value_changed_and_not_their_values(self, committed_sessions, owner):
        update = privacy_schema.UserPrivacySettingsUpdate(hide_activity_map=True, hide_activity_hr=False)
        with committed_sessions() as db:
            profile_service.edit_privacy_settings(owner.id, update, db, if_match='"1"')

        (row,) = _rows(committed_sessions, profile_audit_actions.PRIVACY_UPDATE)
        assert row.details == {"changed_fields": ["hide_activity_map"]}

    def test_an_edit_that_changes_nothing_writes_no_row(self, committed_sessions, owner):
        with committed_sessions() as db:
            profile_service.edit_privacy_settings(
                owner.id, privacy_schema.UserPrivacySettingsUpdate(hide_activity_hr=False), db, if_match='"1"'
            )

        assert _rows(committed_sessions, profile_audit_actions.PRIVACY_UPDATE) == []


class TestEmailChangeRequest:
    def _change(self, committed_sessions, platform, owner, email, *, revoke=False):
        store = account_security_integration.get_step_up_attempts(platform.state)
        change = users_schema.EmailChange(
            email=email, step_up={"current_password": PASSWORD}, revoke_other_sessions=revoke
        )
        with committed_sessions() as db:
            profile_service.change_email(owner.id, change, owner.id, store, platform.state, db)

    def test_a_queued_change_records_that_a_confirmation_is_required(self, committed_sessions, platform, owner):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()

        self._change(committed_sessions, platform, owner, "new@example.com")

        (row,) = _rows(committed_sessions, profile_audit_actions.EMAIL_CHANGE_REQUEST)
        assert row.details == {"confirmation_required": True, "other_sessions_revoked": False}
        assert "new@example.com" not in str(row.details)

    def test_a_change_applied_at_once_and_revoked_sessions_are_recorded(self, committed_sessions, platform, owner):
        self._change(committed_sessions, platform, owner, "new@example.com", revoke=True)

        (row,) = _rows(committed_sessions, profile_audit_actions.EMAIL_CHANGE_REQUEST)
        assert row.details == {"confirmation_required": False, "other_sessions_revoked": True}

    def test_resubmitting_the_current_address_writes_no_row(self, committed_sessions, platform, owner):
        self._change(committed_sessions, platform, owner, owner.email)

        assert _rows(committed_sessions, profile_audit_actions.EMAIL_CHANGE_REQUEST) == []

    def test_cancel_and_resend_write_no_row(self, committed_sessions, platform, owner):
        with committed_sessions() as db:
            profile_service.cancel_email_change(owner.id, db)
            profile_service.resend_email_change(owner.id, platform.state, db)

        assert _rows(committed_sessions, profile_audit_actions.EMAIL_CHANGE_REQUEST) == []
