"""The integrations surface forwards to its CRUD."""

from unittest.mock import MagicMock, patch

import modules.users.users_integrations.integration_service as user_integrations_integration


def test_garmin_operations_reach_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with (
        patch.object(crud, "link_garminconnect_account") as link,
        patch.object(crud, "unlink_garminconnect_account") as unlink,
        patch.object(crud, "unlink_garminconnect_account_if_token", return_value=True),
        patch.object(crud, "set_user_garminconnect_sync_gear") as sync_gear,
        patch.object(crud, "list_user_ids_with_garminconnect_linked", return_value=[3]) as linked,
    ):
        user_integrations_integration.link_garminconnect_account(1, {"di_token": "enc"}, db)
        user_integrations_integration.unlink_garminconnect_account(1, db)
        assert user_integrations_integration.unlink_garminconnect_account_if_token(1, {"di_token": "enc"}, db) is True
        user_integrations_integration.set_garminconnect_sync_gear(1, True, db)
        ids = user_integrations_integration.list_user_ids_with_garminconnect_linked(0, 10, db)

    link.assert_called_once_with(1, {"di_token": "enc"}, db)
    unlink.assert_called_once_with(1, db)
    sync_gear.assert_called_once_with(1, True, db)
    linked.assert_called_once_with(0, 10, db)
    assert ids == [3]
