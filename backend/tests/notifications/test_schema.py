"""Tests for notification Pydantic schemas."""

import typing
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import modules.notifications.schema as notifications_schema


class TestNotificationReadCreatedAt:
    """created_at is normalized to UTC and serializes as a full ISO 8601 timestamp."""

    def _notification(self, created_at):
        return notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
            {
                "id": 1,
                "user_id": 1,
                "type": "new_activity",
                "options": {"activity_id": 5},
                "read": False,
                "created_at": created_at,
            }
        )

    def test_json_dump_is_full_iso_with_utc_offset(self):
        value = datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

        dumped = self._notification(value).model_dump(mode="json")

        assert dumped["created_at"] == "2026-07-16T10:30:00Z"

    def test_python_dump_keeps_datetime(self):
        value = datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

        dumped = self._notification(value).model_dump()

        assert dumped["created_at"] == value
        assert isinstance(dumped["created_at"], datetime)

    def test_naive_datetime_assumed_utc(self):
        value = datetime(2026, 7, 16, 10, 30, 0)

        notification = self._notification(value)

        assert notification.created_at == datetime(2026, 7, 16, 10, 30, 0, tzinfo=UTC)

    def test_non_utc_offset_normalized_to_utc(self):
        value = datetime(2026, 7, 16, 8, 19, 0, tzinfo=timezone(timedelta(hours=-7)))

        dumped = self._notification(value).model_dump(mode="json")

        assert dumped["created_at"] == "2026-07-16T15:19:00Z"


class TestTypedOptions:
    """Each type carries the options its producer stores, and only those."""

    @staticmethod
    def _read(notification_type, options):
        return notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
            {
                "id": 1,
                "user_id": 1,
                "type": notification_type,
                "options": options,
                "created_at": datetime(2026, 7, 16, tzinfo=UTC),
            }
        )

    @pytest.mark.parametrize(
        ("notification_type", "options"),
        [
            ("new_activity", {"activity_id": 3}),
            ("duplicate_activity", {"activity_id": 3}),
            ("new_follower_request", {"user_id": 2, "user_name": "A", "user_username": "a"}),
            ("new_follower_request_accepted", {"user_id": 2, "user_name": "A", "user_username": "a"}),
            ("admin_new_sign_up_approval_request", {"user_id": 2, "user_name": "A", "user_username": "a"}),
            ("garmin_token_expired", {}),
            ("strava_token_expired", {}),
            ("strava_token_expired", {"delete_on": "2026-12-01"}),
            ("strava_data_deleted", {}),
            ("idp_linked", {"idp_id": 4, "idp_name": None}),
            ("account_security_changed", {"change": "password"}),
            ("account_security_changed", {"change": "idp_unlinked", "idp_id": 4, "idp_name": "Keycloak"}),
            ("new_device_sign_in", {"browser": "Firefox", "operating_system": "Linux", "ip_address": "10.0.0.1"}),
        ],
    )
    def test_what_each_producer_stores_is_valid(self, notification_type, options):
        read = self._read(notification_type, options)

        assert read.model_dump(mode="json")["type"] == notification_type

    def test_every_notification_type_has_an_options_schema(self):
        import modules.notifications.constants as notifications_constants

        covered = {
            member
            for variant in typing.get_args(typing.get_args(notifications_schema.NotificationRead)[0])
            for member in typing.get_args(variant.model_fields["type"].annotation)
        }
        assert covered == set(notifications_constants.NotificationType)

    @pytest.mark.parametrize(
        ("notification_type", "options"),
        [("new_activity", {}), ("new_activity", {"activity_id": "x"}), ("new_follower_request", {"user_id": 2})],
    )
    def test_options_of_the_wrong_shape_are_refused(self, notification_type, options):
        with pytest.raises(ValidationError):
            self._read(notification_type, options)

    def test_the_type_decides_the_options(self):
        read = self._read("idp_linked", {"idp_id": 4, "idp_name": "Keycloak"})

        assert isinstance(read.options, notifications_schema.IdpLinkedNotificationOptions)
        assert read.options.idp_name == "Keycloak"

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(ValidationError):
            self._read("nope", {})
