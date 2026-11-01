"""Tests for the Garmin Connect sleep sync: empty days and rows from other sources."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import modules.garmin.health_service as health_utils
import modules.health.health_sleep.schema as health_sleep_schema
from tests._helpers import garmin as garmin_helpers

DAY = datetime(2026, 9, 29, tzinfo=UTC)


def _sleep_payload(**dto_overrides) -> dict:
    """Return a ``get_sleep_data`` payload for 2026-09-29."""
    dto = {
        "id": 1759000000000,
        "calendarDate": "2026-09-29",
        "sleepTimeSeconds": 28800,
        "sleepStartTimestampGMT": 1759100000000,
        "sleepEndTimestampGMT": 1759128800000,
    }
    dto.update(dto_overrides)
    return {"dailySleepDTO": dto}


def _run(payload: dict, existing: MagicMock | None) -> tuple[int, MagicMock]:
    """Sync one day and return the count with the upsert mock."""
    client = MagicMock()
    client.get_sleep_data.return_value = payload
    with (
        patch.object(health_utils.core_database, "SessionLocal"),
        patch.object(health_utils.health_sleep_integration, "get_health_sleep_by_date", return_value=existing),
        patch.object(health_utils.health_sleep_integration, "upsert_health_sleep") as upsert,
    ):
        count = health_utils.fetch_and_process_sleep_by_dates(client, DAY, DAY, 1)
    return count, upsert


def _existing(source, garminconnect_sleep_id) -> MagicMock:
    row = MagicMock()
    row.id = 7
    row.source = source
    row.garminconnect_sleep_id = garminconnect_sleep_id
    return row


class TestEmptySleepDay:
    """A DTO of nulls must be skipped like a missing DTO."""

    def test_dto_without_id_is_skipped(self):
        count, upsert = _run(_sleep_payload(id=None), _existing(None, None))
        assert count == 0
        upsert.assert_not_called()

    def test_dto_without_sleep_time_is_skipped(self):
        count, upsert = _run(_sleep_payload(sleepTimeSeconds=None), None)
        assert count == 0
        upsert.assert_not_called()


class TestExistingRowOwnership:
    """The sync only overwrites rows that Garmin wrote."""

    def test_row_from_another_source_is_kept(self):
        count, upsert = _run(_sleep_payload(), _existing(None, None))
        assert count == 0
        upsert.assert_not_called()

    def test_garmin_row_is_updated(self):
        count, upsert = _run(_sleep_payload(), _existing(health_sleep_schema.Source.GARMIN, "123"))
        assert count == 1
        upsert.assert_called_once()

    def test_legacy_row_with_garmin_sleep_id_is_updated(self):
        count, upsert = _run(_sleep_payload(), _existing(None, "123"))
        assert count == 1
        upsert.assert_called_once()

    def test_missing_row_is_stored(self):
        count, upsert = _run(_sleep_payload(), None)
        assert count == 1
        upsert.assert_called_once()


class TestNoSessionAcrossGarminCalls:
    """A pool connection must never be held while waiting on Garmin."""

    def test_sleep_fetch_runs_with_no_session_open(self):
        open_sessions = []
        client = MagicMock()
        client.get_sleep_data.side_effect = lambda _day: (
            open_sessions.append(session_factory.open_count) or _sleep_payload()
        )
        session_factory = _CountingSessions()

        with (
            patch.object(health_utils.core_database, "SessionLocal", session_factory),
            patch.object(health_utils.health_sleep_integration, "get_health_sleep_by_date", return_value=None),
            patch.object(health_utils.health_sleep_integration, "upsert_health_sleep"),
        ):
            health_utils.fetch_and_process_sleep_by_dates(client, DAY, DAY, 1)

        assert open_sessions == [0]


class _CountingSessions:
    def __init__(self):
        self.open_count = 0

    def __call__(self):
        return self

    def __enter__(self):
        self.open_count += 1
        return MagicMock()

    def __exit__(self, *exc):
        self.open_count -= 1


class TestExpiredToken:
    def test_an_expired_token_is_handed_to_the_rejected_token_handler(self):
        client = MagicMock()
        client.get_body_composition.side_effect = health_utils.garminconnect.GarminConnectAuthenticationError("401")

        session = health_utils.garmin_service.GarminSession(client, {"di_token": "enc"})
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=session),
            patch.object(health_utils.garmin_service, "handle_rejected_token") as unlink,
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1, garmin_helpers.rate_limits())

        unlink.assert_called_once()
        assert unlink.call_args.args[:2] == (1, session)

    def test_an_unlinked_user_is_skipped(self):
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=None),
            patch.object(health_utils, "fetch_and_process_bc_by_dates") as fetch,
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1, garmin_helpers.rate_limits())

        fetch.assert_not_called()


class TestFailuresPropagate:
    def test_an_unexpected_failure_reaches_the_caller_so_a_worker_retries(self):
        session = health_utils.garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=session),
            patch.object(health_utils, "fetch_and_process_bc_by_dates", side_effect=RuntimeError("boom")),
            patch.object(health_utils.garmin_service, "save_refreshed_token") as save,
            pytest.raises(RuntimeError),
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1, garmin_helpers.rate_limits())

        save.assert_called_once()


class TestStore:
    def test_the_record_is_handed_to_the_upsert_and_committed(self):
        record = health_utils.health_steps_schema.HealthStepsBase(
            date="2026-09-29", steps=10, source=health_utils.health_steps_schema.Source.GARMIN
        )
        upsert = MagicMock()
        with patch.object(health_utils.core_database, "SessionLocal") as session_local:
            stored = health_utils._store(
                1,
                record,
                label="Daily steps",
                upsert=upsert,
                create_schema=health_utils.health_steps_schema.HealthStepsCreate,
            )

        assert stored is True
        assert upsert.call_args.args[0] == 1
        assert upsert.call_args.args[1].steps == 10
        session_local.return_value.__enter__.return_value.commit.assert_called_once()

    def test_a_kept_record_is_not_written(self):
        record = health_utils.health_steps_schema.HealthStepsBase(
            date="2026-09-29", steps=10, source=health_utils.health_steps_schema.Source.GARMIN
        )
        upsert = MagicMock()
        with patch.object(health_utils.core_database, "SessionLocal"):
            stored = health_utils._store(
                1,
                record,
                label="Daily steps",
                upsert=upsert,
                create_schema=health_utils.health_steps_schema.HealthStepsCreate,
                keep_existing=lambda *_: True,
            )

        assert stored is False
        upsert.assert_not_called()


class TestBodyCompositionOwnership:
    """A weight record the user entered, or another source wrote, is never replaced."""

    @staticmethod
    def _run(existing):
        client = MagicMock()
        client.get_body_composition.return_value = {
            "dateWeightList": [
                {
                    "calendarDate": "2026-09-29",
                    "weight": 70000,
                    "bmi": 22.0,
                    "bodyFat": 15.0,
                    "bodyWater": 55.0,
                    "boneMass": 3000,
                    "muscleMass": 30000,
                    "physiqueRating": None,
                    "visceralFat": None,
                }
            ]
        }
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.health_weight_integration, "get_health_weight_by_date", return_value=existing),
            patch.object(health_utils.health_weight_integration, "upsert_health_weight") as upsert,
        ):
            count = health_utils.fetch_and_process_bc_by_dates(client, DAY, DAY, 1)
        return count, upsert

    def test_a_manual_record_is_kept(self):
        count, upsert = self._run(MagicMock(source=None))

        assert count == 0
        upsert.assert_not_called()

    def test_a_garmin_record_is_updated(self):
        count, upsert = self._run(MagicMock(source="garmin"))

        assert count == 1
        upsert.assert_called_once()

    def test_a_missing_record_is_stored(self):
        count, upsert = self._run(None)

        assert count == 1
        upsert.assert_called_once()


class TestDailyStepsOwnership:
    @staticmethod
    def _run(existing):
        client = MagicMock()
        client.get_daily_steps.return_value = [{"calendarDate": "2026-09-29", "totalSteps": 500}]
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.health_steps_integration, "get_health_steps_by_date", return_value=existing),
            patch.object(health_utils.health_steps_integration, "upsert_health_steps") as upsert,
        ):
            count = health_utils.fetch_and_process_ds_by_dates(client, DAY, DAY, 1)
        return count, upsert

    def test_a_manual_record_is_kept(self):
        count, upsert = self._run(MagicMock(source=None))

        assert count == 0
        upsert.assert_not_called()

    def test_a_garmin_record_is_updated(self):
        count, upsert = self._run(MagicMock(source="garmin"))

        assert count == 1
        upsert.assert_called_once()


class TestDailySteps:
    def test_a_zero_step_first_day_does_not_hide_the_rest_of_the_range(self):
        client = MagicMock()
        client.get_daily_steps.return_value = [
            {"calendarDate": "2026-09-28", "totalSteps": 0},
            {"calendarDate": "2026-09-29", "totalSteps": 500},
        ]
        with patch.object(health_utils, "_store", return_value=True) as upsert:
            count = health_utils.fetch_and_process_ds_by_dates(client, DAY, DAY, 1)

        assert count == 2
        assert upsert.call_count == 2


class TestFetchFailures:
    def test_a_garmin_error_reaches_the_caller_instead_of_reading_as_no_data(self):
        client = MagicMock()
        client.get_body_composition.side_effect = RuntimeError("429")

        with pytest.raises(RuntimeError):
            health_utils.fetch_and_process_bc_by_dates(client, DAY, DAY, 1)

    def test_a_sync_reports_whether_it_ran(self):
        session = health_utils.garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=session),
            patch.object(health_utils, "fetch_and_process_bc_by_dates", return_value=0),
            patch.object(health_utils, "fetch_and_process_ds_by_dates", return_value=0),
            patch.object(health_utils, "fetch_and_process_sleep_by_dates", return_value=0),
            patch.object(health_utils.garmin_service, "save_refreshed_token"),
        ):
            assert (
                health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1, garmin_helpers.rate_limits()) is True
            )

        with (
            patch.object(health_utils.core_database, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=None),
        ):
            assert (
                health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1, garmin_helpers.rate_limits()) is False
            )
