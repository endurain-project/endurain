"""Erasure of the failed bulk-import files kept in the ``bulk_import_errors`` storage area.

Their retention sweep is tested with the other scheduled passes (``test_job_lifecycle.py``).
"""

import uuid

import jasil.runtime as platform_runtime
import pytest
from jasil.providers import StorageBackendUnavailableError

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.integration_service as ingestion_integration
from tests._factories.profile import FaultyStorage
from tests._helpers.auth import MOCK_USER_ID

_AREA = activity_ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA


class TestDeleteBulkImportErrors:
    def test_deletes_that_users_files_and_no_one_elses_on_the_real_storage(self):
        """``delete_prefix`` takes the user's path; a prefix ending in ``/`` is refused by the storage provider."""
        storage = platform_runtime.get_active_platform().storage
        other = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
        mine = f"{activity_ingestion_constants.bulk_import_error_prefix(MOCK_USER_ID)}job/a.fit"
        theirs = f"{activity_ingestion_constants.bulk_import_error_prefix(other)}job/a.fit"
        for key in (mine, theirs):
            storage.save(_AREA, key, b"fit")

        ingestion_integration.delete_bulk_import_errors(MOCK_USER_ID, storage)

        assert list(storage.list_keys(_AREA, "")) == [theirs]

    def test_a_storage_failure_is_logged_not_raised(self):
        storage = platform_runtime.get_active_platform().storage
        mine = f"{activity_ingestion_constants.bulk_import_error_prefix(MOCK_USER_ID)}job/a.fit"
        storage.save(_AREA, mine, b"fit")
        down = FaultyStorage(storage, faults={"delete_prefix": StorageBackendUnavailableError("down")})

        ingestion_integration.delete_bulk_import_errors(MOCK_USER_ID, down)

        assert list(storage.list_keys(_AREA, "")) == [mine], "left for the retention sweep"

    def test_an_unexpected_error_propagates(self):
        storage = platform_runtime.get_active_platform().storage
        buggy = FaultyStorage(storage, faults={"delete_prefix": TypeError("bug")})

        with pytest.raises(TypeError):
            ingestion_integration.delete_bulk_import_errors(MOCK_USER_ID, buggy)
