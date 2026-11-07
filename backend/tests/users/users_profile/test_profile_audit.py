"""Audit rows of the user's own profile, privacy, email change, export and import."""

import io
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.audit import Outcome
from jasil.backends.state_memory import MemoryState
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.schema as auth_schema
import modules.users.users.schema as users_schema
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.export_job_service as export_job_service
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.import_job_service as import_job_service
import modules.users.users_profile.import_state_store as import_state_store
import modules.users.users_profile.service as profile_service

_SERVICE = "modules.users.users_profile.service"
_EXPORT = "modules.users.users_profile.export_job_service"
_IMPORT = "modules.users.users_profile.import_job_service"
_TARGET = {"target_type": "user", "target_id": "7", "target_owner_id": "7"}


def _request_export(states, db):
    return export_job_service.request_export(
        7, "session-1", auth_schema.StepUpVerification(current_password="pw"), MagicMock(), states, db
    )


def _user(**overrides) -> users_schema.UserRead:
    fields = {
        "id": 7,
        "name": "Old Name",
        "username": "user7",
        "email": "user7@example.com",
        "active": True,
        "access_type": "regular",
        "city": "Porto",
    }
    fields.update(overrides)
    return users_schema.UserRead(**fields)


class TestProfileUpdate:
    def _edit(self, mock_db, profile, after):
        with (
            patch(f"{_SERVICE}.users_integration.require_user", return_value=_user()),
            patch(f"{_SERVICE}.users_integration.edit_profile", return_value=after),
            patch(f"{_SERVICE}.get_profile"),
        ):
            profile_service.edit_profile(7, profile, mock_db, if_match='"1"')

    def test_names_the_fields_whose_value_changed(self, mock_db):
        profile = users_schema.ProfileUpdate(name="New Name", city="Porto")

        with jasil_testing.capture_audit() as audit:
            self._edit(mock_db, profile, _user(name="New Name"))

        entry = audit.assert_audited(profile_audit_actions.PROFILE_UPDATE.id, **_TARGET)
        assert entry.details == {"changed_fields": ["name"]}
        mock_db.commit.assert_called_once()

    def test_an_edit_that_changes_nothing_writes_no_row(self, mock_db):
        profile = users_schema.ProfileUpdate(name="Old Name", city="Porto")

        with jasil_testing.capture_audit() as audit:
            self._edit(mock_db, profile, _user())

        audit.assert_not_audited(profile_audit_actions.PROFILE_UPDATE.id)

    def test_a_refused_edit_writes_no_row(self, mock_db):
        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_SERVICE}.users_integration.require_user", return_value=_user()),
            patch(f"{_SERVICE}.users_integration.edit_profile", side_effect=core_exceptions.ConflictError("taken")),
            pytest.raises(core_exceptions.ConflictError),
        ):
            profile_service.edit_profile(7, users_schema.ProfileUpdate(name="x"), mock_db, if_match='"1"')

        audit.assert_not_audited(profile_audit_actions.PROFILE_UPDATE.id)


class TestPrivacyUpdate:
    def _edit(self, mock_db, update, after):
        before = privacy_schema.UserPrivacySettingsRead(id=1, user_id=7)
        with (
            patch(f"{_SERVICE}.users_privacy_settings_integration.get_privacy_settings", return_value=before),
            patch(f"{_SERVICE}.users_privacy_settings_integration.edit_privacy_settings", return_value=after),
        ):
            profile_service.edit_privacy_settings(7, update, mock_db, if_match='"1"')

    def test_names_the_settings_whose_value_changed(self, mock_db):
        update = privacy_schema.UserPrivacySettingsUpdate(hide_activity_map=True, hide_activity_hr=False)
        after = privacy_schema.UserPrivacySettingsRead(id=1, user_id=7, hide_activity_map=True)

        with jasil_testing.capture_audit() as audit:
            self._edit(mock_db, update, after)

        entry = audit.assert_audited(profile_audit_actions.PRIVACY_UPDATE.id, **_TARGET)
        assert entry.details == {"changed_fields": ["hide_activity_map"]}

    def test_an_edit_that_changes_nothing_writes_no_row(self, mock_db):
        update = privacy_schema.UserPrivacySettingsUpdate(hide_activity_hr=False)
        after = privacy_schema.UserPrivacySettingsRead(id=1, user_id=7)

        with jasil_testing.capture_audit() as audit:
            self._edit(mock_db, update, after)

        audit.assert_not_audited(profile_audit_actions.PRIVACY_UPDATE.id)


class TestEmailChangeRequest:
    def _change(self, mock_db, email, *, queued=True, revoke=False, current="user7@example.com"):
        change = users_schema.EmailChange(email=email, step_up={"current_password": "pw"}, revoke_other_sessions=revoke)
        with (
            patch(f"{_SERVICE}.account_security_integration"),
            patch(f"{_SERVICE}.users_integration") as users,
            patch(f"{_SERVICE}.sign_up_tokens_integration") as tokens,
            patch(f"{_SERVICE}.get_profile"),
        ):
            users.require_user.return_value = _user(email=current)
            tokens.request_self_service_email_change.return_value = queued
            profile_service.change_email(7, change, "sid", MagicMock(), MagicMock(), mock_db)

    def test_a_queued_change_records_that_a_confirmation_is_required(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._change(mock_db, "New@Example.com")

        entry = audit.assert_audited(profile_audit_actions.EMAIL_CHANGE_REQUEST.id, **_TARGET)
        assert entry.details == {"confirmation_required": True, "other_sessions_revoked": False}

    def test_a_change_applied_at_once_and_revoked_sessions_are_recorded(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._change(mock_db, "new@example.com", queued=False, revoke=True)

        entry = audit.assert_audited(profile_audit_actions.EMAIL_CHANGE_REQUEST.id, **_TARGET)
        assert entry.details == {"confirmation_required": False, "other_sessions_revoked": True}

    def test_resubmitting_the_current_address_writes_no_row(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._change(mock_db, "USER7@example.com")

        audit.assert_not_audited(profile_audit_actions.EMAIL_CHANGE_REQUEST.id)

    def test_cancel_and_resend_write_no_row(self, mock_db):
        with jasil_testing.capture_audit() as audit, patch(f"{_SERVICE}.sign_up_tokens_integration"):
            profile_service.cancel_email_change(7, mock_db)
            profile_service.resend_email_change(7, MagicMock(), mock_db)

        audit.assert_not_audited(profile_audit_actions.EMAIL_CHANGE_REQUEST.id)


class TestProfileExport:
    @pytest.fixture
    def states(self):
        return export_state_store.ProfileExportStateStore(MemoryState())

    def test_the_request_is_recorded_in_the_queueing_transaction(self, states, mock_db):
        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_EXPORT}.profile_event_publishers.publish_export_requested"),
            patch(f"{_EXPORT}.account_security_integration.verify_step_up"),
        ):
            _request_export(states, mock_db)

        entry = audit.assert_audited(profile_audit_actions.PROFILE_EXPORT_REQUEST.id, **_TARGET)
        assert entry.details is None

    def test_a_refused_request_writes_no_row(self, states, mock_db):
        states.begin(7)

        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_EXPORT}.account_security_integration.verify_step_up"),
            pytest.raises(core_exceptions.ConflictError),
        ):
            _request_export(states, mock_db)

        audit.assert_not_audited(profile_audit_actions.PROFILE_EXPORT_REQUEST.id)

    def test_a_download_is_recorded_once_the_archive_is_found(self, states):
        states.begin(7)
        states.set_status(7, profile_constants.ExportStatus.SUCCEEDED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.return_value = io.BytesIO(b"zip-data")

        with jasil_testing.capture_audit() as audit:
            export_job_service.open_export(7, states, storage)

        entry = audit.assert_audited(profile_audit_actions.PROFILE_EXPORT_DOWNLOAD.id, **_TARGET)
        assert entry.outcome == Outcome.SUCCESS
        assert entry.details is None

    def test_no_download_without_a_finished_export_writes_no_row(self, states):
        states.begin(7)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.NotFoundError):
            export_job_service.open_export(7, states, MagicMock())

        audit.assert_not_audited(profile_audit_actions.PROFILE_EXPORT_DOWNLOAD.id)

    def test_a_missing_archive_writes_no_row(self, states):
        states.begin(7)
        states.set_status(7, profile_constants.ExportStatus.SUCCEEDED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.side_effect = FileNotFoundError

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.NotFoundError):
            export_job_service.open_export(7, states, storage)

        audit.assert_not_audited(profile_audit_actions.PROFILE_EXPORT_DOWNLOAD.id)


def _saver(*, kind, upload_dir, filename):
    path = f"{upload_dir}/{filename}"
    with open(path, "wb") as out:
        out.write(b"zip")
    return path


def _payload(user_id: int = 7) -> profile_events.ProfileImportRequestedPayload:
    return profile_events.ProfileImportRequestedPayload(user_id=user_id, staged_key=f"{user_id}/abc.zip")


class TestProfileImport:
    @pytest.fixture
    def states(self):
        return import_state_store.ProfileImportStateStore(MemoryState())

    @pytest.fixture
    def storage(self):
        store = MagicMock()
        store.get.return_value = b"zip"
        return store

    def _run(self, states, storage, outcome, *, will_retry=False):
        stage = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
        with patch(f"{_IMPORT}._run_importer", **stage):
            import_job_service.run_import(_payload(), states, storage, will_retry=will_retry)

    def test_the_request_is_recorded_in_the_queueing_transaction(self, states, storage, mock_db):
        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_IMPORT}.profile_event_publishers.publish_import_requested"),
        ):
            import_job_service.request_import(7, _saver, states, storage, mock_db)

        entry = audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_REQUEST.id, **_TARGET)
        assert entry.details is None

    def test_a_refused_request_writes_no_row(self, states, storage, mock_db):
        states.begin(7)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.ConflictError):
            import_job_service.request_import(7, _saver, states, storage, mock_db)

        audit.assert_not_audited(profile_audit_actions.PROFILE_IMPORT_REQUEST.id)

    def test_a_finished_import_records_success_once(self, states, storage):
        states.begin(7)

        with jasil_testing.capture_audit() as audit:
            self._run(states, storage, {"activities": 3})

        entries = audit.matching(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)
        assert len(entries) == 1
        assert (entries[0].outcome, entries[0].details) == (Outcome.SUCCESS, None)
        audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id, **_TARGET)

    def test_a_failed_import_records_failure_once(self, states, storage):
        states.begin(7)

        with jasil_testing.capture_audit() as audit:
            self._run(states, storage, RuntimeError("boom"))

        entries = audit.matching(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)
        assert [e.outcome for e in entries] == [Outcome.FAILURE]
        audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id, outcome=Outcome.FAILURE, **_TARGET)

    def test_a_retried_attempt_writes_nothing_until_the_import_ends(self, states, storage):
        states.begin(7)
        transient = OperationalError("stmt", {}, Exception("db down"))

        with jasil_testing.capture_audit() as audit:
            with pytest.raises(type(transient)):
                self._run(states, storage, transient, will_retry=True)
            audit.assert_not_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)
            self._run(states, storage, {"activities": 1})

        assert len(audit.matching(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)) == 1

    def test_a_missing_staged_archive_records_failure(self, states, storage):
        states.begin(7)
        storage.get.return_value = None

        with jasil_testing.capture_audit() as audit:
            self._run(states, storage, {})

        audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id, outcome=Outcome.FAILURE, **_TARGET)

    def test_a_redelivery_that_finds_the_import_already_finished_writes_nothing(self, states, storage):
        states.begin(7)
        states.set_status(7, profile_constants.ImportStatus.SUCCEEDED)

        with jasil_testing.capture_audit() as audit:
            self._run(states, storage, {})

        audit.assert_not_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)

    def test_an_import_that_died_writing_files_records_failure_once(self, states, storage):
        states.begin(7)
        states.set_status(7, profile_constants.ImportStatus.WRITING_FILES)

        with jasil_testing.capture_audit() as audit:
            self._run(states, storage, {})

        assert len(audit.matching(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)) == 1

    def test_a_dead_lettered_pending_import_records_failure_but_a_finished_one_does_not(self, states, storage):
        states.begin(7)
        with jasil_testing.capture_audit() as audit:
            import_job_service.close_dead_lettered_import(_payload(), states, storage)
        audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id, outcome=Outcome.FAILURE, **_TARGET)

        states.discard(7)
        states.begin(7)
        states.set_status(7, profile_constants.ImportStatus.SUCCEEDED)
        with jasil_testing.capture_audit() as audit:
            import_job_service.close_dead_lettered_import(_payload(), states, storage)
        audit.assert_not_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)

    def test_an_import_the_pool_could_not_take_records_failure(self, states, storage):
        states.begin(7)

        with jasil_testing.capture_audit() as audit:
            import_job_service.fail_unstarted_import(_payload(), states, storage)

        audit.assert_audited(profile_audit_actions.PROFILE_IMPORT_COMPLETE.id, outcome=Outcome.FAILURE, **_TARGET)
