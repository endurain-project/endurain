"""Retention and erasure of the failed bulk-import files kept in the ``bulk_import_errors`` storage area."""

import time
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.service as ingestion_service

_AREA = activity_ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA
_DAY = 86400


class TestSweepStaleBulkImportErrors:
    def test_removes_only_files_older_than_the_retention_window(self):
        storage = MagicMock()
        now = time.time()
        storage.iter_objects.return_value = iter([("1/job/old.fit", now - 10 * _DAY), ("1/job/new.fit", now - _DAY)])

        with patch.object(ingestion_service.core_config.settings, "JOBS_RETENTION_DAYS", 5):
            removed = ingestion_service.sweep_stale_bulk_import_errors(storage)

        assert removed == 1
        storage.iter_objects.assert_called_once_with(_AREA)
        storage.delete.assert_called_once_with(_AREA, "1/job/old.fit")

    @pytest.mark.parametrize("retention_days", [0, -1])
    def test_does_nothing_when_retention_is_disabled(self, retention_days):
        storage = MagicMock()

        with patch.object(ingestion_service.core_config.settings, "JOBS_RETENTION_DAYS", retention_days):
            removed = ingestion_service.sweep_stale_bulk_import_errors(storage)

        assert removed == 0
        assert storage.mock_calls == []


class TestDeleteBulkImportErrors:
    def test_deletes_only_that_users_prefix(self):
        storage = MagicMock()

        ingestion_integration.delete_bulk_import_errors(1, storage)

        storage.delete_prefix.assert_called_once_with(_AREA, "1")

    def test_a_storage_failure_is_logged_not_raised(self):
        storage = MagicMock()
        storage.delete_prefix.side_effect = platform_providers.StorageBackendUnavailableError("down")

        ingestion_integration.delete_bulk_import_errors(1, storage)

        storage.delete_prefix.assert_called_once()

    def test_an_unexpected_error_propagates(self):
        storage = MagicMock()
        storage.delete_prefix.side_effect = TypeError("bug")

        with pytest.raises(TypeError):
            ingestion_integration.delete_bulk_import_errors(1, storage)
