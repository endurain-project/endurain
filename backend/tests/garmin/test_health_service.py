"""Tests for the Garmin Connect sleep sync: empty days and rows from other sources."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import modules.garmin.health_service as health_utils
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
        patch.object(health_utils, "SessionLocal"),
        patch.object(health_utils.health_sleep_integration, "get_health_sleep_by_date", return_value=existing),
        patch.object(health_utils.health_sleep_integration, "edit_health_sleep") as edit,
        patch.object(health_utils.health_sleep_integration, "create_health_sleep") as create,
    ):
        count = health_utils.fetch_and_process_sleep_by_dates(client, DAY, DAY, 1)
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
            patch.object(health_utils, "SessionLocal", session_factory),
            patch.object(health_utils.health_sleep_integration, "get_health_sleep_by_date", return_value=None),
            patch.object(health_utils.health_sleep_integration, "create_health_sleep"),
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
            patch.object(health_utils, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=session),
            patch.object(health_utils.garmin_service, "handle_rejected_token") as unlink,
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1)

        unlink.assert_called_once()
        assert unlink.call_args.args[:2] == (1, session)

    def test_an_unlinked_user_is_skipped(self):
        with (
            patch.object(health_utils, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=None),
            patch.object(health_utils, "fetch_and_process_bc_by_dates") as fetch,
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1)

        fetch.assert_not_called()


class TestFailuresPropagate:
    def test_an_unexpected_failure_reaches_the_caller_so_a_worker_retries(self):
        session = health_utils.garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(health_utils, "SessionLocal"),
            patch.object(health_utils.garmin_service, "get_user_garminconnect_session", return_value=session),
            patch.object(health_utils, "fetch_and_process_bc_by_dates", side_effect=RuntimeError("boom")),
            patch.object(health_utils.garmin_service, "save_refreshed_token") as save,
            pytest.raises(RuntimeError),
        ):
            health_utils.get_user_garminconnect_health_by_dates(DAY, DAY, 1)

        save.assert_called_once()


class TestUpsert:
    def test_an_existing_record_is_edited_and_a_missing_one_created(self):
        record = health_utils.health_steps_schema.HealthStepsBase(
            date="2026-09-29", steps=10, source=health_utils.health_steps_schema.Source.GARMIN
        )
        edit, create = MagicMock(), MagicMock()
        kwargs = {
            "label": "Daily steps",
            "edit": edit,
            "create": create,
            "update_schema": health_utils.health_steps_schema.HealthStepsUpdate,
            "create_schema": health_utils.health_steps_schema.HealthStepsCreate,
        }
        with patch.object(health_utils, "SessionLocal"):
            health_utils._upsert(1, record, get=lambda *_: MagicMock(id=7), **kwargs)
            health_utils._upsert(1, record, get=lambda *_: None, **kwargs)

        assert edit.call_args.args[1].id == 7
        create.assert_called_once()
