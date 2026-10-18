"""Tests for the Strava bulk import endpoint."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import strava.router as strava_router


@pytest.fixture
def mock_loop(monkeypatch):
    """Patch the event loop used to queue the import and return it."""
    loop = Mock()
    monkeypatch.setattr(strava_router.asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(
        strava_router.strava_bulk_import_utils,
        "iterate_over_activities_csv",
        lambda: {"123": {"Activity ID": "123"}},
    )
    return loop


async def _import(db):
    return await strava_router.import_activities_and_media_from_strava_export(
        token_user_id=1,
        _check_scopes=None,
        db=db,
        ws_manager=Mock(),
    )


async def test_import_is_queued_when_user_has_no_gear(mock_loop, monkeypatch):
    """An empty gear dictionary (user without gear) must not abort the import."""
    monkeypatch.setattr(
        strava_router.strava_bulk_import_utils,
        "create_gear_dictionary_for_bulk_import",
        lambda user_id, db: {},
    )

    await _import(Mock())

    mock_loop.run_in_executor.assert_called_once()
    queued = mock_loop.run_in_executor.call_args.args[1]
    assert queued.func is strava_router.strava_bulk_import_utils.queue_bulk_export_activities_for_import
    assert queued.args[4] == {}


async def test_import_is_aborted_when_gear_dictionary_fails(mock_loop, monkeypatch):
    """A None gear dictionary (user not found) aborts the import."""
    monkeypatch.setattr(
        strava_router.strava_bulk_import_utils,
        "create_gear_dictionary_for_bulk_import",
        lambda user_id, db: None,
    )

    await _import(Mock())

    mock_loop.run_in_executor.assert_not_called()
