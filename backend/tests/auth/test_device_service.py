"""Tests for listing and forgetting a user's known devices through account security."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.device_service as device_service
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.schema as auth_schema

_STEP_UP = auth_schema.StepUpVerification(current_password="pw")


def _forget(mock_db):
    device_service.forget_user_device(5, 7, "sid", _STEP_UP, MagicMock(), mock_db)


def test_the_list_marks_the_device_the_request_names(mock_db):
    page = core_pagination.PageParams(1, 25)
    expected = known_devices_schema.KnownDevicePage.build([], 0, 1, 25)
    with patch.object(device_service.known_devices_integration, "list_devices", return_value=expected) as listing:
        assert device_service.list_user_devices(7, "device-id", page, mock_db) is expected

    listing.assert_called_once_with(7, "device-id", page, mock_db)


class TestForget:
    def test_step_up_is_verified_for_the_forget_action_before_the_device_is_touched(self, mock_db):
        calls = MagicMock()
        calls.forget.return_value = 0
        with (
            patch.object(device_service.step_up_service, "verify_step_up_credentials", calls.verify),
            patch.object(device_service.known_devices_integration, "forget_device", calls.forget),
        ):
            _forget(mock_db)

        assert [call[0] for call in calls.mock_calls] == ["verify", "forget"]
        assert (
            calls.verify.call_args.kwargs["action"] == identity_providers_constants.StepUpAction.PROFILE_DEVICE_FORGET
        )
        assert calls.verify.call_args.kwargs["session_id"] == "sid"
        calls.forget.assert_called_once_with(5, 7, mock_db)

    def test_a_forgotten_device_is_audited_and_committed(self, mock_db):
        with (
            patch.object(device_service.step_up_service, "verify_step_up_credentials"),
            patch.object(device_service.known_devices_integration, "forget_device", return_value=3),
            jasil_testing.capture_audit() as audit,
        ):
            _forget(mock_db)

        row = audit.assert_audited(
            account_security_audit_actions.DEVICE_FORGET.id,
            target_type="device",
            target_id="5",
            target_owner_id="7",
        )
        assert row.details == {"sessions_revoked": 3}
        mock_db.commit.assert_called_once()

    def test_a_refused_step_up_forgets_and_audits_nothing(self, mock_db):
        with (
            patch.object(
                device_service.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.StepUpFailedError(),
            ),
            patch.object(device_service.known_devices_integration, "forget_device") as forget,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            _forget(mock_db)

        forget.assert_not_called()
        audit.assert_not_audited(account_security_audit_actions.DEVICE_FORGET.id)
        mock_db.commit.assert_not_called()

    def test_an_unknown_device_is_not_found_and_audits_nothing(self, mock_db):
        with (
            patch.object(device_service.step_up_service, "verify_step_up_credentials"),
            patch.object(
                device_service.known_devices_integration,
                "forget_device",
                side_effect=core_exceptions.NotFoundError("Device not found"),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            _forget(mock_db)

        audit.assert_not_audited(account_security_audit_actions.DEVICE_FORGET.id)
        mock_db.commit.assert_not_called()


class TestForgetOthers:
    def _forget_others(self, mock_db):
        device_service.forget_other_user_devices(7, "sid", "device-id", _STEP_UP, MagicMock(), mock_db)

    def test_step_up_is_verified_for_its_own_action_before_any_device_is_touched(self, mock_db):
        calls = MagicMock()
        calls.forget.return_value = 0
        with (
            patch.object(device_service.step_up_service, "verify_step_up_credentials", calls.verify),
            patch.object(device_service.known_devices_integration, "forget_other_devices", calls.forget),
        ):
            self._forget_others(mock_db)

        assert [call[0] for call in calls.mock_calls] == ["verify", "forget"]
        assert (
            calls.verify.call_args.kwargs["action"]
            == identity_providers_constants.StepUpAction.PROFILE_DEVICES_FORGET_OTHERS
        )
        assert calls.verify.call_args.kwargs["session_id"] == "sid"
        calls.forget.assert_called_once_with(7, "device-id", mock_db)

    def test_the_change_is_audited_with_the_sessions_ended_and_committed(self, mock_db):
        with (
            patch.object(device_service.step_up_service, "verify_step_up_credentials"),
            patch.object(device_service.known_devices_integration, "forget_other_devices", return_value=4),
            jasil_testing.capture_audit() as audit,
        ):
            self._forget_others(mock_db)

        row = audit.assert_audited(
            account_security_audit_actions.DEVICES_FORGET_OTHERS.id,
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert row.details == {"sessions_revoked": 4}
        mock_db.commit.assert_called_once()

    def test_a_refused_step_up_forgets_and_audits_nothing(self, mock_db):
        with (
            patch.object(
                device_service.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.StepUpFailedError(),
            ),
            patch.object(device_service.known_devices_integration, "forget_other_devices") as forget,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            self._forget_others(mock_db)

        forget.assert_not_called()
        audit.assert_not_audited(account_security_audit_actions.DEVICES_FORGET_OTHERS.id)
        mock_db.commit.assert_not_called()
