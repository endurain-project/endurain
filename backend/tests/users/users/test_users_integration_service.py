"""The users surface delegates to the owning service and CRUD."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from jasil.backends.state_memory import MemoryState

import modules.users.users.constants as users_constants
import modules.users.users.deletion_state_store as users_deletion_state_store
import modules.users.users.integration_service as users_integration


def test_reads_reach_the_crud():
    db = MagicMock()
    crud = users_integration.users_crud
    with (
        patch.object(crud, "get_user_by_id", return_value="user") as by_id,
        patch.object(crud, "get_user_by_email", return_value="email-user") as by_email,
        patch.object(crud, "get_user_by_username", return_value="name-user") as by_name,
    ):
        assert users_integration.get_user(1, db) == "user"
        assert users_integration.get_user_by_email("a@b.c", db) == "email-user"
        assert users_integration.get_user_by_username("a", db) == "name-user"

    by_id.assert_called_once_with(1, db)
    by_email.assert_called_once_with("a@b.c", db)
    by_name.assert_called_once_with("a", db)


def test_creation_time_check_reaches_the_crud():
    db = MagicMock()
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    with patch.object(users_integration.users_crud, "was_created_after", return_value=True) as created_after:
        assert users_integration.was_created_after(3, moment, db) is True

    created_after.assert_called_once_with(3, moment, db)


def test_public_profiles_reach_the_service():
    db = MagicMock()
    with patch.object(users_integration.users_service, "list_public_profiles", return_value={1: "profile"}) as profiles:
        assert users_integration.list_public_profiles({1, 2}, db) == {1: "profile"}

    profiles.assert_called_once_with({1, 2}, db)


def test_public_profile_reaches_the_service():
    db = MagicMock()
    with patch.object(users_integration.users_service, "get_public_profile", return_value="profile") as profile:
        assert users_integration.get_public_profile(7, db) == "profile"

    profile.assert_called_once_with(7, db)


def test_public_user_reaches_the_service():
    db = MagicMock()
    with patch.object(users_integration.users_service, "get_public_user", return_value="profile") as profile:
        assert users_integration.get_public_user(7, db) == "profile"

    profile.assert_called_once_with(7, db)


def test_decisions_reach_the_service():
    db = MagicMock()
    service = users_integration.users_service
    with (
        patch.object(service, "require_user") as require_user,
        patch.object(service, "require_active_user") as require_active,
        patch.object(service, "require_admin_users") as require_admins,
        patch.object(service, "stage_user_edit") as edit,
        patch.object(service, "stage_profile_edit") as profile,
        patch.object(service, "stage_email_verification") as verify,
        patch.object(service, "stage_confirmed_email_change") as confirmed,
        patch.object(service, "stage_signup_user") as signup,
    ):
        users_integration.require_user(1, db)
        users_integration.require_active_user("user")
        users_integration.require_admin_users(db)
        users_integration.edit_user(1, "user", db, if_match="*")
        users_integration.edit_profile(1, "profile", db, if_match="*")
        users_integration.stage_email_verification(1, "settings", db)
        users_integration.stage_confirmed_email_change(1, "new@example.com", db)
        users_integration.stage_signup_user("signup", "settings", db)

    require_user.assert_called_once_with(1, db)
    require_active.assert_called_once_with("user")
    require_admins.assert_called_once_with(db)
    edit.assert_called_once_with(1, "user", db, if_match="*")
    profile.assert_called_once_with(1, "profile", db, if_match="*")
    verify.assert_called_once_with(1, "settings", db)
    confirmed.assert_called_once_with(1, "new@example.com", db)
    signup.assert_called_once_with("signup", "settings", db)


def test_any_user_exists_reaches_the_crud():
    db = MagicMock()
    with patch.object(users_integration.users_crud, "any_user_exists", return_value=True) as exists:
        assert users_integration.any_user_exists(db) is True

    exists.assert_called_once_with(db)


def test_stage_first_admin_reaches_the_service():
    db = MagicMock()
    admin = MagicMock()
    with patch.object(users_integration.users_service, "stage_first_admin", return_value="admin") as stage:
        assert users_integration.stage_first_admin(admin, db) == "admin"

    stage.assert_called_once_with(admin, db)


def test_read_deletion_job_returns_the_current_deletion_with_its_id_and_kind():
    state = MemoryState()
    job = users_deletion_state_store.UserDeletionStateStore(state).begin(
        5, users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=9
    )

    status = users_integration.read_deletion_job(job, state)

    assert (status.id, status.kind, status.status) == (job.id, "user_deletion", "queued")


def test_read_deletion_job_is_none_for_an_earlier_job_and_once_expired():
    state = MemoryState()
    store = users_deletion_state_store.UserDeletionStateStore(state)
    first = store.begin(5, users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=9)
    store.set_status(5, users_constants.DeletionKind.ACCOUNT, users_constants.DeletionStatus.FAILED)
    store.begin(5, users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=9)

    assert users_integration.read_deletion_job(first, state) is None
    assert users_integration.read_deletion_job(first, MemoryState()) is None
