"""Tests for the Garmin Connect gear sync."""

from unittest.mock import MagicMock, patch

import garminconnect

import modules.garmin.gear_service as garmin_gear_service


def _patched(client):
    session = garmin_gear_service.garmin_service.GarminSession(client, {"di_token": "enc"}) if client else None
    return (
        patch.object(garmin_gear_service.core_database, "SessionLocal"),
        patch.object(garmin_gear_service.garmin_service, "get_user_garminconnect_session", return_value=session),
        patch.object(garmin_gear_service.user_integrations_integration, "set_garminconnect_sync_gear"),
        patch.object(garmin_gear_service.garmin_service, "handle_rejected_token"),
    )


def _run(client):
    session, get_client, set_sync, unlink = _patched(client)
    with session, get_client, set_sync as sync_flag, unlink as unlink_mock:
        synced = garmin_gear_service.get_user_gear(1)
    return sync_flag, unlink_mock, synced


def test_gear_sync_stays_off_when_garmin_connect_is_not_linked():
    sync_flag, _, synced = _run(None)

    sync_flag.assert_not_called()
    assert synced is False


def test_an_expired_token_unlinks_the_account_and_leaves_gear_sync_off():
    client = MagicMock()
    client.get_device_last_used.side_effect = garminconnect.GarminConnectAuthenticationError("401")

    sync_flag, unlink, synced = _run(client)

    unlink.assert_called_once()
    sync_flag.assert_not_called()
    assert synced is False


def test_gear_sync_turns_on_once_the_gear_was_fetched():
    client = MagicMock()
    client.get_device_last_used.return_value = {"userProfileNumber": 5}
    client.get_gear.return_value = []

    session, get_client, set_sync, unlink = _patched(client)
    with (
        session,
        get_client,
        set_sync as sync_flag,
        unlink,
        patch.object(garmin_gear_service.gears_integration, "create_multiple_gears"),
        patch.object(garmin_gear_service, "set_activities_gear", return_value=0),
        patch.object(garmin_gear_service.garmin_service, "get_linked_user_integrations", return_value=MagicMock()),
    ):
        synced = garmin_gear_service.get_user_gear(1)

    assert synced is True
    sync_flag.assert_called_once()
    assert sync_flag.call_args.args[:2] == (1, True)


def test_gear_sync_stays_off_when_the_account_was_unlinked_meanwhile():
    client = MagicMock()
    client.get_device_last_used.return_value = {"userProfileNumber": 5}
    client.get_gear.return_value = []

    session, get_client, set_sync, unlink = _patched(client)
    with (
        session,
        get_client,
        set_sync as sync_flag,
        unlink,
        patch.object(garmin_gear_service.gears_integration, "create_multiple_gears"),
        patch.object(garmin_gear_service.garmin_service, "get_linked_user_integrations", return_value=None),
    ):
        synced = garmin_gear_service.get_user_gear(1)

    assert synced is False
    sync_flag.assert_not_called()


def test_only_gear_not_stored_yet_is_counted():
    client = MagicMock()
    client.get_device_last_used.return_value = {"userProfileNumber": 5}
    client.get_gear.return_value = [{"uuid": "known"}, {"uuid": "new"}]
    new_gear = MagicMock()

    with (
        patch.object(garmin_gear_service.core_database, "SessionLocal"),
        patch.object(garmin_gear_service, "process_gear", side_effect=[None, new_gear]),
        patch.object(garmin_gear_service.gears_integration, "create_multiple_gears") as create,
    ):
        count = garmin_gear_service.fetch_and_process_gear(client, 1)

    assert count == 1
    assert create.call_args.args[0] == [new_gear]
