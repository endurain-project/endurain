"""The users surface delegates to the owning service and CRUD."""

from unittest.mock import MagicMock, patch

import modules.users.users.integration_service as users_integration


def test_reads_reach_the_crud():
    db = MagicMock()
    crud = users_integration.users_crud
    with (
        patch.object(crud, "get_user_by_id", return_value="user") as by_id,
        patch.object(crud, "get_user_by_email", return_value="email-user") as by_email,
        patch.object(crud, "get_user_by_username", return_value="name-user") as by_name,
        patch.object(crud, "get_users_admin", return_value=["admin"]) as admins,
    ):
        assert users_integration.get_user(1, db) == "user"
        assert users_integration.get_user_by_email("a@b.c", db) == "email-user"
        assert users_integration.get_user_by_username("a", db) == "name-user"
        assert users_integration.list_admin_users(db) == ["admin"]

    by_id.assert_called_once_with(1, db)
    by_email.assert_called_once_with("a@b.c", db)
    by_name.assert_called_once_with("a", db)
    admins.assert_called_once_with(db)


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
        patch.object(service, "create_signup_user") as signup,
    ):
        users_integration.require_user(1, db)
        users_integration.require_active_user("user")
        users_integration.require_admin_users(db)
        users_integration.edit_user(1, "user", db, if_match="*")
        users_integration.edit_profile(1, "profile", db, if_match="*")
        users_integration.stage_email_verification(1, "settings", db)
        users_integration.create_signup_user("signup", "settings", "identity", db, False)

    require_user.assert_called_once_with(1, db)
    require_active.assert_called_once_with("user")
    require_admins.assert_called_once_with(db)
    edit.assert_called_once_with(1, "user", db, if_match="*")
    profile.assert_called_once_with(1, "profile", db, if_match="*")
    verify.assert_called_once_with(1, "settings", db)
    signup.assert_called_once_with("signup", "settings", "identity", db, False)
