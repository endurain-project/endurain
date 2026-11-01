"""Audit rows of the account lifecycle an administrator or the owner drives."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.deletion_job_service as job_service
import modules.users.users.deletion_state_store as deletion_state_store
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_CRUD = "modules.users.users.service.users_crud"
_SETTINGS = "modules.users.users.service.server_settings_integration"
_JOBS = "modules.users.users.deletion_job_service"


def _user(user_id: int = 1, **overrides) -> users_schema.UsersRead:
    fields = {
        "id": user_id,
        "name": "User",
        "username": f"user{user_id}",
        "email": f"user{user_id}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UsersRead(**fields)


@pytest.fixture(autouse=True)
def boundaries():
    """Replace the boundaries the lifecycle functions reach through."""
    with (
        patch("modules.users.users.service.sign_up_tokens_integration") as sign_up,
        patch("modules.users.users.service.credentials_integration"),
        patch("modules.users.users.service.account_security_integration"),
        patch("modules.users.users.service.health_weight_integration"),
        patch("modules.users.users.service._stage_default_data"),
        patch(_SETTINGS),
    ):
        sign_up.get_pending_email_changes.return_value = {}
        sign_up.request_email_change.return_value = True
        yield


class TestAccountCreation:
    def _create(self, mock_db, *, first_admin: bool):
        with patch(_CRUD) as crud:
            crud.create_user.return_value = _user(7, access_type="admin" if first_admin else "regular")
            if first_admin:
                crud.any_user_exists.return_value = False
                return users_service.stage_first_admin(
                    users_schema.FirstAdminCreate(
                        name="Owner", username="owner", email="owner@example.com", password="SecurePass1!"
                    ),
                    mock_db,
                )
            return users_service.create_user(
                users_schema.UsersCreate(
                    name="N",
                    username="NewUser",
                    email="new@example.com",
                    active=True,
                    access_type="regular",
                    password="password123",
                ),
                mock_db,
            )

    def test_an_admin_created_account_is_audited(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._create(mock_db, first_admin=False)

        entry = audit.assert_audited(
            users_audit_actions.USER_CREATE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"access_type": "regular"}

    def test_the_first_admin_is_audited(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._create(mock_db, first_admin=True)

        entry = audit.assert_audited(users_audit_actions.USER_CREATE.id, target_id="7")
        assert entry.details == {"access_type": "admin"}

    def test_a_sign_up_is_not_audited(self, mock_db):
        with patch(_CRUD) as crud, jasil_testing.capture_audit() as audit:
            crud.create_user.return_value = _user(7)
            users_service.create_signup_user(
                users_schema.UsersSignup(name="N", username="NewUser", email="n@example.com", password="SecurePass1!"),
                MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False),
                mock_db,
            )

        audit.assert_not_audited(users_audit_actions.USER_CREATE.id)


class TestAdminEdit:
    def _edit(self, mock_db, before, after, requested):
        with patch(_CRUD) as crud, jasil_testing.capture_audit() as audit:
            crud.get_user_by_id.return_value = before
            crud.update_user.return_value = after
            crud.lock_active_admin_ids.return_value = [1, 2]
            users_service.edit_user(before.id, users_schema.UsersEdit.from_read(requested), 9, mock_db, if_match="*")
        return audit

    def test_names_the_fields_that_changed_and_never_their_values(self, mock_db):
        before = _user(1)
        after = _user(1, name="Renamed", height=180)

        audit = self._edit(mock_db, before, after, after)

        entry = audit.assert_audited(
            users_audit_actions.USER_UPDATE.id, target_type="user", target_id="1", target_owner_id="1"
        )
        assert sorted(entry.details["changed_fields"]) == ["height", "name"]
        assert "Renamed" not in repr(entry.details)

    def test_an_edit_that_changes_nothing_writes_no_row(self, mock_db):
        before = _user(1)

        audit = self._edit(mock_db, before, before, before)

        audit.assert_not_audited(users_audit_actions.USER_UPDATE.id)


class TestApprove:
    def test_approval_is_audited(self, mock_db):
        with (
            patch(_CRUD) as crud,
            patch(_SETTINGS) as settings,
            jasil_testing.capture_audit() as audit,
        ):
            settings.get_server_settings.return_value = MagicMock(signup_require_email_verification=False)
            crud.get_user_by_id.return_value = _user(1)
            users_service.approve_user(1, mock_db)

        audit.assert_audited(
            users_audit_actions.USER_APPROVE.id, target_type="user", target_id="1", target_owner_id="1"
        )


class TestDeletion:
    def test_an_accepted_deletion_is_audited_in_the_request_transaction(self, mock_db):
        states = deletion_state_store.UserDeletionStateStore(MemoryState())
        with (
            patch(f"{_JOBS}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_JOBS}.account_security_integration"),
            patch(f"{_JOBS}.sign_up_tokens_integration"),
            patch(f"{_JOBS}.users_service"),
            patch(f"{_JOBS}.users_crud"),
            patch(f"{_JOBS}._deletion_pool"),
            jasil_testing.capture_audit() as audit,
        ):
            job_service.request_deletion(4, states, MagicMock(), mock_db, if_match="*")

        audit.assert_audited(users_audit_actions.USER_DELETE.id, target_type="user", target_id="4", target_owner_id="4")
