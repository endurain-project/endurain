"""Tests for the Garmin Connect sleep sync: empty days and rows from other sources."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import modules.garmin.health_utils as health_utils
import modules.health.health_sleep.schema as health_sleep_schema

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


def _run(payload: dict, existing: MagicMock | None) -> tuple[int, MagicMock, MagicMock]:
    """Sync one day and return the count with the edit and create mocks."""
    client = MagicMock()
    client.get_sleep_data.return_value = payload
    with (
        patch.object(health_utils.health_sleep_crud, "get_health_sleep_by_date_and_user_id", return_value=existing),
        patch.object(health_utils.health_sleep_crud, "edit_health_sleep") as edit,
        patch.object(health_utils.health_sleep_crud, "create_health_sleep") as create,
    ):
        count = health_utils.fetch_and_process_sleep_by_dates(client, DAY, DAY, 1, MagicMock())
    return count, edit, create


def _existing(source, garminconnect_sleep_id) -> MagicMock:
    row = MagicMock()
    row.id = 7
    row.source = source
    row.garminconnect_sleep_id = garminconnect_sleep_id
    return row


class TestEmptySleepDay:
    """A DTO of nulls must be skipped like a missing DTO."""

    def test_dto_without_id_is_skipped(self):
        existing = _existing(None, None)
        count, edit, create = _run(_sleep_payload(id=None), existing)
        assert count == 0
        edit.assert_not_called()
        create.assert_not_called()

    def test_dto_without_sleep_time_is_skipped(self):
        count, edit, create = _run(_sleep_payload(sleepTimeSeconds=None), None)
        assert count == 0
        edit.assert_not_called()
        create.assert_not_called()


class TestExistingRowOwnership:
    """The sync only overwrites rows that Garmin wrote."""

    def test_row_from_another_source_is_kept(self):
        count, edit, create = _run(_sleep_payload(), _existing(None, None))
        assert count == 0
        edit.assert_not_called()
        create.assert_not_called()

    def test_garmin_row_is_updated(self):
        count, edit, _ = _run(_sleep_payload(), _existing(health_sleep_schema.Source.GARMIN, "123"))
        assert count == 1
        edit.assert_called_once()

    def test_legacy_row_with_garmin_sleep_id_is_updated(self):
        count, edit, _ = _run(_sleep_payload(), _existing(None, "123"))
        assert count == 1
        edit.assert_called_once()

    def test_missing_row_is_created(self):
        count, edit, create = _run(_sleep_payload(), None)
        assert count == 1
        create.assert_called_once()
        edit.assert_not_called()
