"""Tests for COROS activity discovery, download and sync decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

import modules.coros.activity_utils as activity_utils
import modules.coros.constants as constants
import modules.coros.contracts as contracts
import modules.coros.mcp_client as mcp_client


def _summary(label_id: str = "123", sport_type: int = 100) -> contracts.CorosActivitySummary:
    return contracts.CorosActivitySummary(label_id=label_id, sport_type=sport_type)


def _result(text: str) -> mcp_client.MCPToolResult:
    return mcp_client.MCPToolResult(content=[{"type": "text", "text": text}])


class TestParseSportRecords:
    """The documented text format and structured fallbacks both parse."""

    def test_documented_text_format_is_parsed(self):
        result = _result(
            "Sport Records — 2026-09-19 to 2026-10-18 (1 records)\n\n"
            "1. Sport(100) — 2026-10-03\n"
            "   LabelId: 452764979110641666 | SportType: 100\n"
            "   Duration: 2:12:38 | Distance: 12.03 km\n"
        )

        assert activity_utils.parse_sport_records(result) == [_summary("452764979110641666", 100)]

    def test_sport_type_before_label_id_is_parsed(self):
        result = _result("SportType: 200 | LabelId: abc-1")
        assert activity_utils.parse_sport_records(result) == [_summary("abc-1", 200)]

    def test_a_markdown_table_is_parsed(self):
        result = _result(
            "| Date | LabelId | SportType |\n"
            "| --- | --- | --- |\n"
            "| 2026-10-03 | 123 | 100 |\n"
            "| 2026-10-04 | 456 | 200 |\n"
        )

        assert activity_utils.parse_sport_records(result) == [
            _summary("123", 100),
            _summary("456", 200),
        ]

    def test_structured_content_is_parsed(self):
        result = mcp_client.MCPToolResult(
            content=[],
            structured_content={"activities": [{"labelId": 99, "sportType": "101"}]},
        )
        assert activity_utils.parse_sport_records(result) == [_summary("99", 101)]

    def test_empty_result_is_not_an_error(self):
        assert activity_utils.parse_sport_records(_result("0 records")) == []

    def test_unknown_non_empty_shape_is_rejected(self):
        with pytest.raises(mcp_client.CorosMCPProtocolError):
            activity_utils.parse_sport_records(_result("Something entirely different"))


class TestDateChunks:
    """Queries are bounded so one response cannot silently truncate history."""

    def test_range_is_split_into_inclusive_weeks(self):
        chunks = list(activity_utils._date_chunks(datetime(2026, 1, 1).date(), datetime(2026, 1, 15).date()))
        assert chunks == [
            (datetime(2026, 1, 1).date(), datetime(2026, 1, 7).date()),
            (datetime(2026, 1, 8).date(), datetime(2026, 1, 14).date()),
            (datetime(2026, 1, 15).date(), datetime(2026, 1, 15).date()),
        ]


class TestSyncDecisions:
    """One user sync is isolated, idempotent and quota-aware."""

    @pytest.fixture
    def connection(self):
        return SimpleNamespace(mcp_url="https://mcpeu.coros.com/mcp", access_token="token")

    @pytest.fixture
    def fake_client(self):
        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                self.tools = [
                    {"name": constants.TOOL_QUERY_ACTIVITIES},
                    {"name": constants.TOOL_DOWNLOAD_FIT},
                ]

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return None

            def list_tools(self):
                return self.tools

            def call_tool(self, _name, _arguments):
                return mcp_client.MCPToolResult()

        return FakeClient

    @pytest.fixture(autouse=True)
    def common_patches(self, monkeypatch, connection, fake_client):
        monkeypatch.setattr(activity_utils.coros_service, "get_valid_connection", Mock(return_value=connection))
        monkeypatch.setattr(activity_utils.coros_mcp_client, "CorosMCPClient", fake_client)
        monkeypatch.setattr(activity_utils, "fetch_activity_summaries", Mock(return_value=[_summary()]))
        monkeypatch.setattr(activity_utils, "_already_stored", Mock(return_value=False))
        monkeypatch.setattr(activity_utils, "_already_skipped", Mock(return_value=False))
        monkeypatch.setattr(activity_utils.coros_service, "reserve_fit_download", Mock(return_value=True))
        monkeypatch.setattr(activity_utils, "_download_fit", Mock(return_value=b"fit"))
        monkeypatch.setattr(activity_utils, "_ingest_fit", Mock(return_value=[SimpleNamespace(id=1)]))
        monkeypatch.setattr(activity_utils, "_mark_skipped", Mock())
        monkeypatch.setattr(activity_utils.coros_service, "mark_sync_success", Mock())
        monkeypatch.setattr(activity_utils.coros_service, "mark_sync_error", Mock())
        monkeypatch.setattr(activity_utils.logger, "warning", Mock())
        monkeypatch.setattr(activity_utils.logger, "error", Mock())
        monkeypatch.setattr(activity_utils.logger, "info", Mock())

    def test_successful_sync_stores_and_records_the_count(self):
        result = activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))

        assert result is not None and len(result) == 1
        activity_utils.coros_service.mark_sync_success.assert_called_once_with(1, 1)

    def test_already_stored_activity_is_not_downloaded(self, monkeypatch):
        monkeypatch.setattr(activity_utils, "_already_stored", Mock(return_value=True))

        assert (
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
        )
        activity_utils._download_fit.assert_not_called()

    def test_an_activity_without_a_fit_file_is_marked_once(self, monkeypatch):
        monkeypatch.setattr(activity_utils, "_download_fit", Mock(return_value=None))

        assert (
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
        )
        activity_utils._mark_skipped.assert_called_once_with(1, "123", "no_file")

    def test_quota_exhaustion_is_reported(self, monkeypatch):
        monkeypatch.setattr(activity_utils.coros_service, "reserve_fit_download", Mock(return_value=False))

        assert (
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
        )
        activity_utils.coros_service.mark_sync_error.assert_called_once_with(1, constants.SyncErrorCode.QUOTA_EXHAUSTED)

    def test_missing_required_tool_is_reported(self, fake_client):
        class FakeClientWithoutDownload(fake_client):
            def list_tools(self):
                return [{"name": constants.TOOL_QUERY_ACTIVITIES}]

        activity_utils.coros_mcp_client.CorosMCPClient = FakeClientWithoutDownload

        assert (
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
        )
        activity_utils.coros_service.mark_sync_error.assert_called_once_with(
            1, constants.SyncErrorCode.TOOLS_UNAVAILABLE
        )

    def test_rejected_token_requires_reconnection(self, fake_client):
        class RejectingClient(fake_client):
            def list_tools(self):
                raise mcp_client.CorosMCPAuthenticationError("rejected")

        activity_utils.coros_mcp_client.CorosMCPClient = RejectingClient

        assert (
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
        )
        activity_utils.coros_service.mark_sync_error.assert_called_once_with(
            1, constants.SyncErrorCode.AUTHORIZATION_EXPIRED
        )

    def test_transient_failure_is_raised_for_the_job_retry(self, monkeypatch):
        monkeypatch.setattr(
            activity_utils,
            "fetch_activity_summaries",
            Mock(side_effect=mcp_client.CorosMCPTransientError("down")),
        )

        with pytest.raises(mcp_client.CorosMCPTransientError):
            activity_utils._sync_locked(1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC))
        activity_utils.coros_service.mark_sync_error.assert_called_once_with(1, constants.SyncErrorCode.NETWORK_ERROR)


class TestPerUserLock:
    """A manual and a scheduled sync for one user cannot run together."""

    def test_a_held_lock_skips_the_sync(self, monkeypatch):
        lock = MagicMock()
        lock.try_acquire.return_value.__enter__.return_value = False
        state = MagicMock()
        state.set_if_absent.return_value = True
        platform = SimpleNamespace(lock=lock, state=state)
        monkeypatch.setattr(activity_utils.platform_runtime, "get_active_platform", Mock(return_value=platform))
        monkeypatch.setattr(activity_utils, "_sync_locked", Mock())

        assert (
            activity_utils.get_user_coros_activities_by_dates(
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 2, tzinfo=UTC),
                1,
            )
            is None
        )
        activity_utils._sync_locked.assert_not_called()

    def test_a_held_state_guard_skips_the_sync(self, monkeypatch):
        lock = MagicMock()
        lock.try_acquire.return_value.__enter__.return_value = True
        state = MagicMock()
        state.set_if_absent.return_value = False
        platform = SimpleNamespace(lock=lock, state=state)
        monkeypatch.setattr(activity_utils.platform_runtime, "get_active_platform", Mock(return_value=platform))
        monkeypatch.setattr(activity_utils, "_sync_locked", Mock())

        assert (
            activity_utils.get_user_coros_activities_by_dates(
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 2, tzinfo=UTC),
                1,
            )
            is None
        )
        activity_utils._sync_locked.assert_not_called()
        lock.try_acquire.assert_not_called()
