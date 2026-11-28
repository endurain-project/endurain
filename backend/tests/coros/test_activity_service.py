"""Tests for COROS activity discovery, download and sync decisions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import httpx2
import pytest

import core.exceptions as core_exceptions
import modules.coros.activity_service as activity_service
import modules.coros.constants as constants
import modules.coros.contracts as contracts
import modules.coros.mcp_client as mcp_client

USER_ID = uuid.uuid4()
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 2, tzinfo=UTC)


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

        assert activity_service.parse_sport_records(result) == [_summary("452764979110641666", 100)]

    def test_sport_type_before_label_id_is_parsed(self):
        result = _result("SportType: 200 | LabelId: abc-1")
        assert activity_service.parse_sport_records(result) == [_summary("abc-1", 200)]

    def test_a_markdown_table_is_parsed(self):
        result = _result(
            "| Date | LabelId | SportType |\n"
            "| --- | --- | --- |\n"
            "| 2026-10-03 | 123 | 100 |\n"
            "| 2026-10-04 | 456 | 200 |\n"
        )

        assert activity_service.parse_sport_records(result) == [
            _summary("123", 100),
            _summary("456", 200),
        ]

    def test_structured_content_is_parsed(self):
        result = mcp_client.MCPToolResult(
            content=[],
            structured_content={"activities": [{"labelId": 99, "sportType": "101"}]},
        )
        assert activity_service.parse_sport_records(result) == [_summary("99", 101)]

    def test_empty_result_is_not_an_error(self):
        assert activity_service.parse_sport_records(_result("0 records")) == []

    def test_unknown_non_empty_shape_is_rejected(self):
        with pytest.raises(mcp_client.CorosMCPProtocolError):
            activity_service.parse_sport_records(_result("Something entirely different"))


class TestDateChunks:
    """Queries are bounded so one response cannot silently truncate history."""

    def test_range_is_split_into_inclusive_weeks(self):
        chunks = list(activity_service._date_chunks(datetime(2026, 1, 1).date(), datetime(2026, 1, 15).date()))
        assert chunks == [
            (datetime(2026, 1, 1).date(), datetime(2026, 1, 7).date()),
            (datetime(2026, 1, 8).date(), datetime(2026, 1, 14).date()),
            (datetime(2026, 1, 15).date(), datetime(2026, 1, 15).date()),
        ]


class TestFitDownload:
    """A FIT download maps its response to the sync's errors."""

    @staticmethod
    def _use_response(monkeypatch, response):
        real_client = httpx2.Client
        monkeypatch.setattr(activity_service, "_url_is_allowed", Mock(return_value=True))
        monkeypatch.setattr(
            activity_service.httpx2,
            "Client",
            lambda **_kwargs: real_client(transport=httpx2.MockTransport(lambda _request: response)),
        )

    def test_a_rate_limited_download_carries_the_retry_after(self, monkeypatch):
        self._use_response(monkeypatch, httpx2.Response(429, headers={"retry-after": "45"}))

        with pytest.raises(mcp_client.CorosMCPRateLimitError) as caught:
            activity_service._download_url("https://mcpeu.coros.com/fit/1")

        assert caught.value.retry_after == 45

    def test_another_failed_download_is_transient(self, monkeypatch):
        self._use_response(monkeypatch, httpx2.Response(503))

        with pytest.raises(mcp_client.CorosMCPTransientError):
            activity_service._download_url("https://mcpeu.coros.com/fit/1")


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
        monkeypatch.setattr(activity_service.coros_service, "get_valid_connection", Mock(return_value=connection))
        monkeypatch.setattr(activity_service.coros_mcp_client, "CorosMCPClient", fake_client)
        monkeypatch.setattr(activity_service, "fetch_activity_summaries", Mock(return_value=[_summary()]))
        monkeypatch.setattr(activity_service, "_already_imported", Mock(return_value=False))
        monkeypatch.setattr(activity_service, "_already_skipped", Mock(return_value=False))
        monkeypatch.setattr(activity_service.coros_service, "reserve_fit_download", Mock(return_value=True))
        monkeypatch.setattr(activity_service, "_download_fit", Mock(return_value=b"fit"))
        monkeypatch.setattr(activity_service, "_ingest_fit", Mock(return_value=[SimpleNamespace(id=1)]))
        monkeypatch.setattr(activity_service, "_mark_skipped", Mock())
        monkeypatch.setattr(activity_service, "_mark_imported", Mock())
        monkeypatch.setattr(activity_service.coros_service, "mark_sync_success", Mock())
        monkeypatch.setattr(activity_service.coros_service, "mark_sync_error", Mock())
        monkeypatch.setattr(activity_service.logger, "warning", Mock())
        monkeypatch.setattr(activity_service.logger, "error", Mock())
        monkeypatch.setattr(activity_service.logger, "info", Mock())

    def test_successful_sync_stores_and_records_the_count(self):
        result = activity_service._sync_locked(USER_ID, START, END)

        assert result is not None and len(result) == 1
        activity_service.coros_service.mark_sync_success.assert_called_once_with(USER_ID, 1)

    def test_completely_imported_activity_is_not_downloaded(self, monkeypatch):
        monkeypatch.setattr(activity_service, "_already_imported", Mock(return_value=True))

        assert activity_service._sync_locked(USER_ID, START, END) is None
        activity_service._download_fit.assert_not_called()

    def test_a_completed_import_is_marked(self):
        activity_service._sync_locked(USER_ID, START, END)

        activity_service._mark_imported.assert_called_once_with(USER_ID, "123")

    def test_a_failed_import_is_not_marked_complete(self, monkeypatch):
        monkeypatch.setattr(activity_service, "_ingest_fit", Mock(side_effect=RuntimeError("failed")))

        with pytest.raises(RuntimeError):
            activity_service._sync_locked(USER_ID, START, END)

        activity_service._mark_imported.assert_not_called()

    def test_an_activity_without_a_fit_file_is_marked_once(self, monkeypatch):
        monkeypatch.setattr(activity_service, "_download_fit", Mock(return_value=None))

        assert activity_service._sync_locked(USER_ID, START, END) is None
        activity_service._mark_skipped.assert_called_once_with(USER_ID, "123", "no_file")

    def test_quota_exhaustion_is_reported(self, monkeypatch):
        monkeypatch.setattr(activity_service.coros_service, "reserve_fit_download", Mock(return_value=False))

        assert activity_service._sync_locked(USER_ID, START, END) is None
        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.QUOTA_EXHAUSTED
        )

    def test_missing_required_tool_is_reported(self, fake_client):
        class FakeClientWithoutDownload(fake_client):
            def list_tools(self):
                return [{"name": constants.TOOL_QUERY_ACTIVITIES}]

        activity_service.coros_mcp_client.CorosMCPClient = FakeClientWithoutDownload

        assert activity_service._sync_locked(USER_ID, START, END) is None
        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.TOOLS_UNAVAILABLE
        )

    def test_rejected_token_requires_reconnection(self, fake_client):
        class RejectingClient(fake_client):
            def list_tools(self):
                raise mcp_client.CorosMCPAuthenticationError("rejected")

        activity_service.coros_mcp_client.CorosMCPClient = RejectingClient

        assert activity_service._sync_locked(USER_ID, START, END) is None
        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.AUTHORIZATION_EXPIRED
        )

    def test_transient_failure_is_raised_for_the_job_retry(self, monkeypatch):
        monkeypatch.setattr(
            activity_service,
            "fetch_activity_summaries",
            Mock(side_effect=mcp_client.CorosMCPTransientError("down")),
        )

        with pytest.raises(mcp_client.CorosMCPTransientError):
            activity_service._sync_locked(USER_ID, START, END)
        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.NETWORK_ERROR
        )

    def test_a_rate_limit_is_raised_as_a_deferral(self, monkeypatch):
        monkeypatch.setattr(
            activity_service,
            "fetch_activity_summaries",
            Mock(side_effect=mcp_client.CorosMCPRateLimitError("limited", 30)),
        )

        with pytest.raises(core_exceptions.TooManyRequestsError) as caught:
            activity_service._sync_locked(USER_ID, START, END)

        assert caught.value.retry_at is not None
        assert caught.value.retry_at > datetime.now(UTC) + timedelta(seconds=20)
        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.RATE_LIMITED
        )

    def test_a_rate_limit_without_a_reset_time_has_no_retry_at(self, monkeypatch):
        monkeypatch.setattr(
            activity_service,
            "fetch_activity_summaries",
            Mock(side_effect=mcp_client.CorosMCPRateLimitError("limited")),
        )

        with pytest.raises(core_exceptions.TooManyRequestsError) as caught:
            activity_service._sync_locked(USER_ID, START, END)

        assert caught.value.retry_at is None

    def test_a_rate_limited_token_refresh_is_raised_for_the_deferral(self, monkeypatch):
        limited = core_exceptions.TooManyRequestsError(
            "limited",
            scope=core_exceptions.TooManyRequestsScope.PROVIDER,
            retry_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        monkeypatch.setattr(activity_service.coros_service, "get_valid_connection", Mock(side_effect=limited))

        with pytest.raises(core_exceptions.TooManyRequestsError):
            activity_service._sync_locked(USER_ID, START, END)

        activity_service.coros_service.mark_sync_error.assert_called_once_with(
            USER_ID, constants.SyncErrorCode.RATE_LIMITED
        )


class TestPerUserLock:
    """A manual and a scheduled sync for one user cannot run together."""

    def test_a_held_lock_skips_the_sync(self, monkeypatch):
        lock = MagicMock()
        lock.try_acquire.return_value.__enter__.return_value = False
        state = MagicMock()
        state.set_if_absent.return_value = True
        platform = SimpleNamespace(lock=lock, state=state)
        monkeypatch.setattr(activity_service, "_sync_locked", Mock())

        assert (
            activity_service.get_user_coros_activities_by_dates(
                platform,
                START,
                END,
                USER_ID,
            )
            is None
        )
        activity_service._sync_locked.assert_not_called()

    def test_a_held_state_guard_skips_the_sync(self, monkeypatch):
        lock = MagicMock()
        lock.try_acquire.return_value.__enter__.return_value = True
        state = MagicMock()
        state.set_if_absent.return_value = False
        platform = SimpleNamespace(lock=lock, state=state)
        monkeypatch.setattr(activity_service, "_sync_locked", Mock())

        assert (
            activity_service.get_user_coros_activities_by_dates(
                platform,
                START,
                END,
                USER_ID,
            )
            is None
        )
        activity_service._sync_locked.assert_not_called()
        lock.try_acquire.assert_not_called()
