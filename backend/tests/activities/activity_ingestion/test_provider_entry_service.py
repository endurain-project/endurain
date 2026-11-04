"""Tests for the provider entry: a bad file is skipped, an outage reaches the window."""

from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.provider_entry_service as provider_entry_service


def _store(db: MagicMock, error: Exception | None = None, result: object = None):
    with patch.object(
        provider_entry_service.activity_ingestion_pipeline_service,
        "validate_prepare_and_store_file",
        side_effect=error,
        return_value=result,
    ):
        return provider_entry_service.store_activity_file(7, "/tmp/a.fit", MagicMock(), db, source=MagicMock())


class TestStoreActivityFile:
    def test_returns_the_stored_activities(self):
        db = MagicMock()

        assert _store(db, result=["activity"]) == ["activity"]
        db.rollback.assert_not_called()

    def test_a_terminal_file_verdict_is_rolled_back_and_skipped(self):
        db = MagicMock()

        assert _store(db, core_exceptions.UnsupportedFormatError("bad")) is None
        db.rollback.assert_called_once()

    @pytest.mark.parametrize(
        "error",
        [
            OperationalError("stmt", {}, Exception("db down")),
            platform_providers.StorageBackendUnavailableError("storage down"),
            RuntimeError("bug"),
        ],
        ids=["database", "storage", "bug"],
    )
    def test_an_outage_or_bug_propagates_so_the_window_retries(self, error):
        with pytest.raises(type(error)):
            _store(MagicMock(), error)
