"""The cap on the uploads one user may have open at once."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.crud as activity_ingestion_crud
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.service as ingestion_jobs
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service

_CAP = activity_ingestion_constants.MAX_OPEN_UPLOADS_PER_USER
_JOB_1 = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


def _received() -> upload_entry_service.ReceivedUpload:
    return upload_entry_service.ReceivedUpload(incoming_path="/incoming/x.gpx", storage_key="abc.gpx", fingerprint="h")


def _accept(db, *, counts: list[int], key: str | None = None, prior=None):
    """Run ``accept_upload`` with each open-upload count the cap reads, in order."""
    with (
        patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
        patch.object(ingestion_jobs.activity_ingestion_dispatch_service, "require_capacity"),
        patch.object(
            ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
        ) as receive,
        patch.object(
            ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
        ) as store,
        patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_received_upload"),
        patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        patch.object(ingestion_jobs.activity_ingestion_crud, "count_open_uploads", side_effect=counts),
        patch.object(ingestion_jobs.activity_ingestion_crud, "lock_user_uploads") as lock,
        patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_for_idempotency", return_value=prior),
        patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
        patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
        patch.object(ingestion_jobs, "run_in_background_or_fail"),
    ):
        try:
            result = ingestion_jobs.accept_upload(
                MOCK_USER_ID, "ride.gpx", MagicMock(), "storage", db, idempotency_key=key
            )
            error = None
        except core_exceptions.ConflictError as err:
            result, error = None, err
    return result, error, {"receive": receive, "store": store, "discard": discard, "lock": lock, "create": create}


class TestAcceptUploadCap:
    def test_the_upload_past_the_cap_is_refused_before_it_is_received_staged_or_queued(self):
        _, error, calls = _accept(MagicMock(), counts=[_CAP])

        assert error is not None
        assert str(_CAP) in error.detail
        calls["receive"].assert_not_called()
        calls["store"].assert_not_called()
        calls["create"].assert_not_called()

    def test_an_upload_under_the_cap_takes_the_user_lock_before_it_creates_the_job(self):
        db = MagicMock()
        result, error, calls = _accept(db, counts=[_CAP - 1, _CAP - 1])

        assert error is None
        assert result == "job-view"
        calls["lock"].assert_called_once_with(MOCK_USER_ID, db)
        calls["create"].assert_called_once()

    def test_a_cap_filled_while_the_file_was_stored_refuses_it_and_drops_the_staged_bytes(self):
        """The cheap check passed, but another request took the last slot before this one's row."""
        _, error, calls = _accept(MagicMock(), counts=[_CAP - 1, _CAP])

        assert error is not None
        calls["discard"].assert_called_once()
        calls["create"].assert_not_called()

    def test_a_retry_with_the_same_key_is_replayed_even_at_the_cap(self):
        original = MagicMock(id=_JOB_1)
        result, error, calls = _accept(MagicMock(), counts=[_CAP], key="key-1", prior=(original, "h"))

        assert error is None
        assert result is original
        calls["create"].assert_not_called()

    def test_a_new_key_at_the_cap_is_refused_before_the_file_is_stored(self):
        _, error, calls = _accept(MagicMock(), counts=[_CAP], key="key-2")

        assert error is not None
        calls["store"].assert_not_called()
        calls["create"].assert_not_called()


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    try:
        yield session_factory
    finally:
        session_factory.kw["bind"].dispose()


def _add_job(factory, *, kind: str = "upload", status: str = "pending", user_id: uuid.UUID = MOCK_USER_ID) -> uuid.UUID:
    job_id = uuid.uuid4()
    now = datetime.now(UTC)
    ensure_user(factory, user_id)
    with factory() as db:
        db.add(
            ingestion_models.ActivityIngestionJob(
                id=job_id,
                user_id=user_id,
                kind=kind,
                status=status,
                created_at=now,
                updated_at=now,
                completed_at=now if status in ("completed", "failed") else None,
            )
        )
        db.commit()
    return job_id


class TestCountOpenUploads:
    def _count(self, factory) -> int:
        with factory() as db:
            return activity_ingestion_crud.count_open_uploads(MOCK_USER_ID, db)

    def test_pending_processing_and_deferred_uploads_count(self, factory):
        for status in ("pending", "processing", "deferred"):
            _add_job(factory, status=status)

        assert self._count(factory) == 3

    def test_a_finished_upload_frees_its_slot(self, factory):
        open_ids = [_add_job(factory) for _ in range(_CAP)]
        _add_job(factory, status="completed")
        _add_job(factory, status="failed")
        assert self._count(factory) == _CAP

        with factory() as db:
            activity_ingestion_crud.mark_completed(open_ids[0], [], db)
            db.commit()

        assert self._count(factory) == _CAP - 1

    def test_other_kinds_and_other_users_do_not_count(self, factory):
        _add_job(factory, kind="refresh")
        _add_job(factory, kind="bulk_import")
        _add_job(factory, user_id=uuid.uuid4())

        assert self._count(factory) == 0
