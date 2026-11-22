"""The Garmin sync writes its provenance through the internal schemas, never the client ones."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import modules.garmin.health_service as health_utils
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_weight.schema as health_weight_schema

DAY = datetime(2026, 9, 29, tzinfo=UTC)


def _sync(client: MagicMock, runner, integration: str, upsert_name: str, existing=None):
    module = getattr(health_utils, integration)
    getter = next(name for name in dir(module) if name.startswith("get_health_") and name.endswith("_by_date"))
    with (
        patch.object(health_utils.core_database, "SessionLocal"),
        patch.object(module, getter, return_value=existing),
        patch.object(module, upsert_name) as upsert,
    ):
        count = runner(client, DAY, DAY, 1)
    return count, upsert


def test_steps_are_written_as_garmin_through_the_import_schema():
    client = MagicMock()
    client.get_daily_steps.return_value = [{"calendarDate": "2026-09-29", "totalSteps": 10}]

    count, upsert = _sync(
        client, health_utils.fetch_and_process_ds_by_dates, "health_steps_integration", "upsert_health_steps"
    )

    record = upsert.call_args.args[1]
    assert count == 1
    assert isinstance(record, health_steps_schema.HealthStepsImport)
    assert record.source == "garmin"


def test_weight_is_written_as_garmin_through_the_import_schema():
    client = MagicMock()
    client.get_body_composition.return_value = {
        "dateWeightList": [
            {
                "calendarDate": "2026-09-29",
                "weight": 70000,
                "bmi": 22.0,
                "bodyFat": None,
                "bodyWater": None,
                "boneMass": None,
                "muscleMass": None,
                "physiqueRating": None,
                "visceralFat": None,
                "metabolicAge": None,
            }
        ]
    }

    count, upsert = _sync(
        client, health_utils.fetch_and_process_bc_by_dates, "health_weight_integration", "upsert_health_weight"
    )

    record = upsert.call_args.args[1]
    assert count == 1
    assert isinstance(record, health_weight_schema.HealthWeightImport)
    assert record.source == "garmin"


def test_sleep_is_written_with_its_garmin_id_through_the_import_schema():
    client = MagicMock()
    client.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "id": 1759000000000,
            "calendarDate": "2026-09-29",
            "sleepTimeSeconds": 28800,
            "sleepStartTimestampGMT": 1759100000000,
            "sleepEndTimestampGMT": 1759128800000,
        }
    }

    count, upsert = _sync(
        client, health_utils.fetch_and_process_sleep_by_dates, "health_sleep_integration", "upsert_health_sleep"
    )

    record = upsert.call_args.args[1]
    assert count == 1
    assert isinstance(record, health_sleep_schema.HealthSleepImport)
    assert (record.source, record.garminconnect_sleep_id) == ("garmin", "1759000000000")


def test_a_manual_sleep_record_is_still_kept():
    client = MagicMock()
    client.get_sleep_data.return_value = {
        "dailySleepDTO": {"id": 1, "calendarDate": "2026-09-29", "sleepTimeSeconds": 28800}
    }
    manual = MagicMock(source=None, garminconnect_sleep_id=None)

    count, upsert = _sync(
        client, health_utils.fetch_and_process_sleep_by_dates, "health_sleep_integration", "upsert_health_sleep", manual
    )

    assert count == 0
    upsert.assert_not_called()


def test_a_body_composition_entry_without_a_weight_is_skipped():
    client = MagicMock()
    client.get_body_composition.return_value = {"dateWeightList": [{"calendarDate": "2026-09-29", "weight": None}]}

    count, upsert = _sync(
        client, health_utils.fetch_and_process_bc_by_dates, "health_weight_integration", "upsert_health_weight"
    )

    assert count == 0
    upsert.assert_not_called()
