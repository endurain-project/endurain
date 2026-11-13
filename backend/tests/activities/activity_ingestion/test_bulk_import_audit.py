"""Audit rows of a bulk import request."""

import os
from pathlib import Path
from unittest.mock import patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.storage_local import LocalStorage
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.audit_actions as ingestion_audit_actions
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.models as ingestion_models

from .test_bulk_import_archive import _commit_through, _saver, _zip

_USER = MOCK_USER_ID


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    ensure_user(session_factory, _USER)
    yield session_factory
    session_factory.kw["bind"].dispose()


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(base_dir=str(tmp_path / "storage"), url_prefix="/files")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, factory, monkeypatch):
    monkeypatch.setattr(bulk.core_database, "SessionLocal", factory)
    monkeypatch.setattr(bulk.core_config, "FILES_UPLOAD_INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setattr(bulk.core_config, "bulk_import_dir_for", lambda user_id: str(tmp_path / "drop" / str(user_id)))


class TestArchiveImportRequest:
    def _accept(self, tmp_path, factory, storage, *, jobs_enabled: bool):
        archive = _zip(tmp_path, {"a.fit": b"x", "nested/b.gpx": b"y", "readme.txt": b"z"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", jobs_enabled),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            return bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

    @pytest.mark.parametrize("jobs_enabled", [True, False])
    def test_an_uploaded_archive_is_audited_with_its_file_count(self, tmp_path, factory, storage, jobs_enabled):
        with jasil_testing.capture_audit() as audit:
            job = self._accept(tmp_path, factory, storage, jobs_enabled=jobs_enabled)

        entry = audit.assert_audited(
            ingestion_audit_actions.IMPORT_REQUEST.id,
            target_type="activity_ingestion_job",
            target_id=job.id,
            target_owner_id=str(_USER),
        )
        assert entry.details == {"source": "archive", "file_count": 2}

    def test_a_refused_archive_is_not_audited(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"notes.txt": b"x"})

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

        audit.assert_not_audited(ingestion_audit_actions.IMPORT_REQUEST.id)

    def test_a_second_import_while_one_runs_is_audited_once(self, tmp_path, factory, storage):
        with jasil_testing.capture_audit() as audit:
            self._accept(tmp_path, factory, storage, jobs_enabled=True)
            with pytest.raises(core_exceptions.ConflictError):
                self._accept(tmp_path, factory, storage, jobs_enabled=True)

        assert len(audit.matching(ingestion_audit_actions.IMPORT_REQUEST.id)) == 1


class TestFolderImportRequest:
    def _folder(self, tmp_path, files: dict[str, bytes]) -> Path:
        folder = tmp_path / "drop" / str(_USER)
        for name, data in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return folder

    def test_a_folder_import_is_audited_without_a_count_or_a_path(self, tmp_path, factory, storage):
        self._folder(tmp_path, {"a.fit": b"1"})
        with (
            jasil_testing.capture_audit() as audit,
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            job = bulk.start_from_directory(_USER, "generic", storage, factory())

        entry = audit.assert_audited(
            ingestion_audit_actions.IMPORT_REQUEST.id,
            target_type="activity_ingestion_job",
            target_id=job.id,
            target_owner_id=str(_USER),
        )
        assert entry.details == {"source": "server_directory", "file_count": None}

    def test_an_empty_folder_is_not_audited(self, tmp_path, factory, storage):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            bulk.start_from_directory(_USER, "generic", storage, factory())

        audit.assert_not_audited(ingestion_audit_actions.IMPORT_REQUEST.id)
        assert not os.listdir(tmp_path / "drop" / str(_USER))
        with factory() as db:
            assert db.query(ingestion_models.ActivityIngestionJob).count() == 0
