"""Tests for the Garmin Connect activity sync: ZIP handling and session scoping."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

import modules.garmin.activity_utils as activity_utils


def _make_garminconnect_client(activity_id: int = 12345) -> Mock:
    """Return a garminconnect client mock with one downloadable activity."""
    client = Mock()
    client.get_activities_by_date.return_value = [
        {"activityId": activity_id, "activityName": "Morning Run"},
    ]
    client.get_activity_gear.return_value = []
    client.download_activity.return_value = b"zip-bytes"
    client.ActivityDownloadFormat.ORIGINAL = "ORIGINAL"
    return client


def _call(client: Mock, user_id: int = 1) -> list | None:
    return activity_utils.fetch_and_process_activities_by_dates(
        garminconnect_client=client,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 2, tzinfo=UTC),
        user_id=user_id,
    )


class _TrackingSession:
    """A ``SessionLocal`` stand-in that records how many sessions are open."""

    open_count = 0

    def __enter__(self):
        type(self).open_count += 1
        return Mock()

    def __exit__(self, *_exc):
        type(self).open_count -= 1
        return False


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch):
    """Patch dependencies shared by every test in this module."""
    _TrackingSession.open_count = 0
    monkeypatch.setattr(activity_utils, "SessionLocal", _TrackingSession)
    monkeypatch.setattr(
        activity_utils.activity_integration,
        "get_activity_by_garminconnect_id",
        Mock(return_value=None),
    )
    monkeypatch.setattr(activity_utils.garmin_gear_utils, "resolve_synced_gear_id", Mock(return_value=None))
    monkeypatch.setattr(
        activity_utils.file_uploads,
        "save_validated_bytes_sync",
        Mock(return_value="/work/12345.zip"),
    )
    monkeypatch.setattr(activity_utils, "logger", Mock())


class TestDownloadsRunWithoutASession:
    def test_garmin_round_trips_happen_with_no_session_open(self, monkeypatch):
        """The gear lookup and the file download are network calls; no transaction spans them."""
        client = _make_garminconnect_client()
        open_during: list[int] = []

        def _gear(_activity_id):
            open_during.append(_TrackingSession.open_count)
            return []

        def _download(*_args, **_kwargs):
            open_during.append(_TrackingSession.open_count)
            return b"zip-bytes"

        client.get_activity_gear.side_effect = _gear
        client.download_activity.side_effect = _download
        monkeypatch.setattr(activity_utils.file_uploads, "extract_validated_zip_sync", Mock(return_value=[]))

        _call(client)

        assert open_during == [0, 0]

    def test_the_store_gets_its_own_short_session(self, monkeypatch):
        client = _make_garminconnect_client()
        seen: list[int] = []
        monkeypatch.setattr(
            activity_utils.file_uploads, "extract_validated_zip_sync", Mock(return_value=[Path("/work/a.fit")])
        )

        def _ingest(**_kwargs):
            seen.append(_TrackingSession.open_count)
            return [Mock()]

        monkeypatch.setattr(activity_utils.activity_ingestion_integration, "ingest_activity_file", _ingest)

        result = _call(client)

        assert seen == [1]
        assert result is not None and len(result) == 1


class TestFailureIsolation:
    def test_one_failing_download_does_not_stop_the_next_activity(self, monkeypatch):
        client = _make_garminconnect_client()
        client.get_activities_by_date.return_value = [
            {"activityId": 1, "activityName": "Broken"},
            {"activityId": 2, "activityName": "Fine"},
        ]
        client.download_activity.side_effect = [RuntimeError("garmin 500"), b"zip-bytes"]
        monkeypatch.setattr(
            activity_utils.file_uploads, "extract_validated_zip_sync", Mock(return_value=[Path("/w/b.fit")])
        )
        monkeypatch.setattr(
            activity_utils.activity_ingestion_integration, "ingest_activity_file", lambda **_k: [Mock()]
        )

        result = _call(client)

        assert result is not None and len(result) == 1
        assert client.download_activity.call_count == 2

    def test_an_activity_already_stored_is_not_downloaded(self, monkeypatch):
        client = _make_garminconnect_client()
        monkeypatch.setattr(
            activity_utils.activity_integration, "get_activity_by_garminconnect_id", Mock(return_value=Mock())
        )

        assert _call(client) is None
        client.download_activity.assert_not_called()

    def test_a_failed_zip_validation_skips_the_activity(self, monkeypatch):
        client = _make_garminconnect_client()
        monkeypatch.setattr(
            activity_utils.file_uploads, "save_validated_bytes_sync", Mock(side_effect=ValueError("bad"))
        )
        ingest = Mock()
        monkeypatch.setattr(activity_utils.activity_ingestion_integration, "ingest_activity_file", ingest)

        assert _call(client) is None
        ingest.assert_not_called()


class TestExtractionFailureLogging:
    """Issue #749: extraction failures must say why, not just that they happened."""

    def test_the_failure_is_logged_with_its_type(self, monkeypatch):
        client = _make_garminconnect_client()
        monkeypatch.setattr(
            activity_utils.file_uploads, "extract_validated_zip_sync", Mock(side_effect=ValueError("zip-slip"))
        )

        assert _call(client) is None

        message = activity_utils.logger.warning.call_args.args[0]
        assert "extraction failed" in message
        assert "ValueError" in message


class TestWorkDirectoryIsPrivate:
    def test_the_archive_and_extracted_files_live_in_a_removed_temp_directory(self, monkeypatch):
        """Nothing a failed attempt leaves behind can make the next sync fail (#750)."""
        client = _make_garminconnect_client()
        seen: dict[str, str] = {}

        def _save(data, **kwargs):
            seen["upload_dir"] = kwargs["upload_dir"]
            return str(Path(kwargs["upload_dir"]) / kwargs["filename"])

        def _extract(path, **kwargs):
            seen["dest_dir"] = str(kwargs["dest_dir"])
            return []

        monkeypatch.setattr(activity_utils.file_uploads, "save_validated_bytes_sync", _save)
        monkeypatch.setattr(activity_utils.file_uploads, "extract_validated_zip_sync", _extract)

        _call(client)

        assert not Path(seen["upload_dir"]).exists()
        assert seen["dest_dir"].startswith(seen["upload_dir"])
