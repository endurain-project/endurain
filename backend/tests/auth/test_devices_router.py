"""Tests for the ``/profile/devices`` routes."""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.known_devices.schema as known_devices_schema

_DEVICE_ID = "d" * 43
_ROW_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    with patch(
        "modules.auth.account_security.dependencies.server_settings_integration.get_session_policy",
        return_value=session_policy,
    ):
        yield


class TestListDevices:
    @patch("modules.auth.account_security.devices_router.device_service.list_user_devices")
    def test_lists_the_devices_with_the_one_the_request_names_marked(self, listing, fast_api_client):
        now = datetime.now(UTC)
        listing.return_value = known_devices_schema.KnownDevicePage.build(
            [
                known_devices_schema.KnownDeviceRead(
                    id=_ROW_ID,
                    browser="Firefox",
                    operating_system="Linux",
                    device_type="PC",
                    created_at=now,
                    last_seen_at=now,
                    current=True,
                )
            ],
            1,
            1,
            25,
        )

        response = fast_api_client.get(
            "/devices", headers={"Authorization": "Bearer mock_token", "X-Device-Id": _DEVICE_ID}
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert (item["id"], item["browser"], item["current"]) == (str(_ROW_ID), "Firefox", True)
        assert listing.call_args.args[1] == _DEVICE_ID

    @patch("modules.auth.account_security.devices_router.device_service.list_user_devices")
    def test_a_request_without_a_device_id_passes_none(self, listing, fast_api_client):
        listing.return_value = known_devices_schema.KnownDevicePage.build([], 0, 1, 25)

        response = fast_api_client.get("/devices", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert listing.call_args.args[1] is None


class TestForgetDevice:
    @patch("modules.auth.account_security.devices_router.device_service.forget_user_device")
    def test_answers_204(self, forget, fast_api_client):
        response = fast_api_client.post(
            f"/devices/{_ROW_ID}/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 204
        assert forget.call_args.args[0] == _ROW_ID

    @patch("modules.auth.account_security.devices_router.device_service.forget_user_device")
    def test_another_users_or_an_unknown_device_is_404(self, forget, fast_api_client):
        forget.side_effect = core_exceptions.NotFoundError("Device not found")

        response = fast_api_client.post(
            f"/devices/{_ROW_ID}/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 404

    @patch("modules.auth.account_security.devices_router.device_service.forget_user_device")
    def test_passes_the_requests_device_id(self, forget, fast_api_client):
        response = fast_api_client.post(
            f"/devices/{_ROW_ID}/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token", "X-Device-Id": _DEVICE_ID},
        )

        assert response.status_code == 204
        assert forget.call_args.args[3] == _DEVICE_ID

    @patch("modules.auth.account_security.devices_router.device_service.forget_user_device")
    def test_the_current_device_is_409(self, forget, fast_api_client):
        forget.side_effect = core_exceptions.ConflictError("The current device cannot be forgotten")

        response = fast_api_client.post(
            f"/devices/{_ROW_ID}/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token", "X-Device-Id": _DEVICE_ID},
        )

        assert response.status_code == 409

    def test_a_malformed_device_id_is_422(self, fast_api_client):
        response = fast_api_client.post(
            "/devices/3/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_a_body_without_step_up_is_refused(self, fast_api_client):
        response = fast_api_client.post(
            f"/devices/{_ROW_ID}/delete", json={}, headers={"Authorization": "Bearer mock_token"}
        )

        assert response.status_code == 422


class TestForgetOtherDevices:
    @patch("modules.auth.account_security.devices_router.device_service.forget_other_user_devices")
    def test_answers_204_and_passes_the_requests_device_id(self, forget, fast_api_client):
        response = fast_api_client.post(
            "/devices/revoke",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token", "X-Device-Id": _DEVICE_ID},
        )

        assert response.status_code == 204
        assert forget.call_args.args[2] == _DEVICE_ID

    @patch("modules.auth.account_security.devices_router.device_service.forget_other_user_devices")
    def test_a_request_without_a_device_id_passes_none(self, forget, fast_api_client):
        response = fast_api_client.post(
            "/devices/revoke",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 204
        assert forget.call_args.args[2] is None

    def test_a_malformed_device_id_is_422(self, fast_api_client):
        response = fast_api_client.post(
            "/devices/3/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_a_body_without_step_up_is_refused(self, fast_api_client):
        response = fast_api_client.post("/devices/revoke", json={}, headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 422


class TestForgetAllDevices:
    @patch("modules.auth.account_security.devices_router.device_service.forget_all_user_devices")
    def test_answers_204(self, forget, fast_api_client):
        response = fast_api_client.post(
            "/devices/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 204
        forget.assert_called_once()

    def test_a_malformed_device_id_is_422(self, fast_api_client):
        response = fast_api_client.post(
            "/devices/3/delete",
            json={"step_up": {"current_password": "pw"}},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_a_body_without_step_up_is_refused(self, fast_api_client):
        response = fast_api_client.post("/devices/delete", json={}, headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 422
