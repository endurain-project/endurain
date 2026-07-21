"""Tests for garmin.activity_utils Garmin ZIP handling logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, status

import modules.garmin.activity_utils as activity_utils


def _make_garminconnect_client(activity_id: int = 12345) -> Mock:
    """Return a garminconnect client mock with one downloadable activity."""
    client = Mock()
    client.get_activities_by_date.return_value = [
        {"activityId": activity_id, "activityName": "Morning Run"},
    ]
    client.get_activity_gear.return_value = {}
    client.download_activity.return_value = b"zip-bytes"
    client.ActivityDownloadFormat.ORIGINAL = "ORIGINAL"
    return client


async def _call(client: Mock, user_id: int = 1) -> list | None:
    return await activity_utils.fetch_and_process_activities_by_dates(
        garminconnect_client=client,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 2, tzinfo=UTC),
        user_id=user_id,
        ws_manager=Mock(),
        db=Mock(),
    )


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch):
    """Patch dependencies shared by every test in this module."""
    monkeypatch.setattr(
        activity_utils.activities_crud,
        "get_activity_by_garminconnect_id_from_user_id",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        activity_utils.file_uploads,
        "save_validated_bytes",
        AsyncMock(return_value=Path("/data/12345.zip")),
    )
    monkeypatch.setattr(activity_utils.file_uploads, "safe_remove_within", Mock(return_value=True))
    monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())


class TestExtractionFailureLogging:
    """Issue #749: HTTPException detail must not be swallowed in the log."""

    async def test_http_exception_detail_is_logged(self, monkeypatch):
        """The warning log includes the HTTPException detail dict."""
        detail = {
            "message": "Archive target already exists: '12345_ACTIVITY.fit'",
            "code": "ZIP_TARGET_EXISTS",
        }
        monkeypatch.setattr(
            activity_utils.file_uploads,
            "extract_validated_zip",
            AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=detail,
                )
            ),
        )

        client = _make_garminconnect_client()
        result = await _call(client)

        assert result is None
        logged_messages = [call.args[0] for call in activity_utils.core_logger.print_to_log.call_args_list]
        assert any(str(detail) in message for message in logged_messages)
        assert any("HTTPException" in message for message in logged_messages)

    async def test_non_http_exception_logs_type_name_only(self, monkeypatch):
        """Exceptions without a `.detail` attribute log only the type name."""
        monkeypatch.setattr(
            activity_utils.file_uploads,
            "extract_validated_zip",
            AsyncMock(side_effect=OSError("disk failure")),
        )

        client = _make_garminconnect_client()
        result = await _call(client)

        assert result is None
        logged_messages = [call.args[0] for call in activity_utils.core_logger.print_to_log.call_args_list]
        assert any(message.endswith("OSError") for message in logged_messages)


class TestOrphanedExtractedFileCleanup:
    """Issue #750: a failed parse must not orphan the extracted file."""

    async def test_failed_parse_removes_orphaned_extracted_file(self, monkeypatch):
        """When parsing fails, the extracted file is removed to avoid a retry loop."""
        extracted_path = Path("/data/12345_ACTIVITY.fit")
        monkeypatch.setattr(
            activity_utils.file_uploads,
            "extract_validated_zip",
            AsyncMock(return_value=[extracted_path]),
        )
        monkeypatch.setattr(
            activity_utils.ingestion_orchestrator,
            "parse_and_store_activity_from_file",
            Mock(return_value=None),
        )

        client = _make_garminconnect_client()
        result = await _call(client)

        assert result is None
        activity_utils.file_uploads.safe_remove_within.assert_any_call(
            extracted_path,
            base_dir=activity_utils.core_config.settings.FILES_DIR,
        )

    async def test_successful_parse_does_not_remove_extracted_file(self, monkeypatch):
        """When parsing succeeds, the extracted activity file is left alone."""
        extracted_path = Path("/data/12345_ACTIVITY.fit")
        monkeypatch.setattr(
            activity_utils.file_uploads,
            "extract_validated_zip",
            AsyncMock(return_value=[extracted_path]),
        )
        monkeypatch.setattr(
            activity_utils.ingestion_orchestrator,
            "parse_and_store_activity_from_file",
            Mock(return_value=["created-activity"]),
        )

        client = _make_garminconnect_client()
        result = await _call(client)

        assert result == ["created-activity"]
        removed_paths = [call.args[0] for call in activity_utils.file_uploads.safe_remove_within.call_args_list]
        assert extracted_path not in removed_paths
