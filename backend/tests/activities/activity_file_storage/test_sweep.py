"""The daily sweep is a database query: it resolves what a crash or a lost event left, and lists no storage."""

import hashlib
import uuid
from unittest.mock import patch

import pytest
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import select, text

import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_file_storage.scheduled_jobs as file_jobs
import modules.activities.activity_file_storage.service as file_storage_service
from tests._factories.activities import make_activity
from tests._factories.ingestion import age_stored_objects, retain_file, store_legacy_file
from tests._factories.users import make_user
from tests._helpers.concurrency import Worker

AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = activity_file_storage_constants.ActivityFileState


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _age(committed_sessions, file_id: uuid.UUID, days: float = 2) -> None:
    with committed_sessions() as db:
        db.execute(
            text("UPDATE activity_files SET updated_at = now() - make_interval(days => :days) WHERE id = :id"),
            {"days": days, "id": file_id},
        )
        db.commit()


def _ids(committed_sessions) -> set[uuid.UUID]:
    with committed_sessions() as db:
        return set(db.scalars(select(file_models.ActivityFile.id)).all())


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
        return created


def test_a_crashed_upload_older_than_a_day_loses_its_blob_and_row(storage, committed_sessions, user):
    crashed = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)
    _age(committed_sessions, crashed.ref.file_id)

    file_jobs.sweep_orphaned_activity_files()

    assert storage.get(AREA, crashed.ref.storage_key) is None
    assert _ids(committed_sessions) == set()


def test_a_recent_pending_row_may_belong_to_an_upload_still_running(storage, committed_sessions, user):
    recent = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)

    file_jobs.sweep_orphaned_activity_files()

    assert storage.get(AREA, recent.ref.storage_key) == b"a"
    assert _ids(committed_sessions) == {recent.ref.file_id}


def test_an_upload_taking_a_pending_row_again_keeps_it_from_the_sweep(storage, committed_sessions, user):
    first = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)
    _age(committed_sessions, first.ref.file_id)
    file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)

    file_jobs.sweep_orphaned_activity_files()

    assert _ids(committed_sessions) == {first.ref.file_id}


def test_an_attached_file_no_activity_references_is_removed_after_a_day(storage, committed_sessions, user):
    with committed_sessions() as db:
        activity = make_activity(db, user.id)
        db.commit()
    lost = retain_file(user.id, activity.id, b"a", storage)
    with committed_sessions() as db:
        db.execute(text("UPDATE activities SET file_id = NULL"))
        db.commit()
    _age(committed_sessions, lost)

    file_jobs.sweep_orphaned_activity_files()

    assert storage.get(AREA, f"files/{lost}.fit") is None
    assert _ids(committed_sessions) == set()


def test_an_attached_file_an_activity_references_is_kept(storage, committed_sessions, user):
    with committed_sessions() as db:
        activity = make_activity(db, user.id)
        db.commit()
    kept = retain_file(user.id, activity.id, b"a", storage)
    _age(committed_sessions, kept)

    file_jobs.sweep_orphaned_activity_files()

    assert storage.get(AREA, f"files/{kept}.fit") == b"a"
    assert _ids(committed_sessions) == {kept}


def test_the_sweep_locks_no_file_an_activity_references(storage, committed_sessions, user):
    # A daily pass over every attached row must not lock them all: only an unreferenced candidate is locked and
    # checked again, so a transaction holding a referenced row does not hold the sweep up.
    with committed_sessions() as db:
        activity = make_activity(db, user.id)
        db.commit()
    kept = retain_file(user.id, activity.id, b"a", storage)
    _age(committed_sessions, kept)

    with committed_sessions() as holder:
        holder.execute(text("SELECT id FROM activity_files WHERE id = :id FOR SHARE"), {"id": kept})
        sweep = Worker(file_jobs.sweep_orphaned_activity_files)
        sweep.join()
        holder.rollback()

    assert sweep.error is None
    assert _ids(committed_sessions) == {kept}


def test_a_deleting_row_whose_blob_could_not_be_deleted_stays_and_is_retried(
    storage, committed_sessions, user, break_storage
):
    staged = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)
    with committed_sessions() as db:
        db.execute(text("UPDATE activity_files SET state = 'deleting'"))
        db.commit()
    break_storage(delete=StorageBackendUnavailableError("down"))
    file_jobs.sweep_orphaned_activity_files()
    assert _ids(committed_sessions) == {staged.ref.file_id}, "the row names the blob until it is deleted"

    break_storage()
    file_jobs.sweep_orphaned_activity_files()

    assert storage.get(AREA, staged.ref.storage_key) is None
    assert _ids(committed_sessions) == set()


def test_the_row_sweep_lists_no_storage(storage, committed_sessions, user):
    crashed = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)
    _age(committed_sessions, crashed.ref.file_id)

    with patch.object(type(storage), "iter_objects", side_effect=AssertionError("listed")) as listing:
        assert file_storage_service.sweep(storage) == 1
    listing.assert_not_called()


class TestLegacyFiles:
    def test_deletes_the_file_of_an_activity_that_is_gone_and_spares_files_with_a_row(
        self, storage, committed_sessions, user, tmp_path
    ):
        with committed_sessions() as db:
            alive = make_activity(db, user.id)
            db.commit()
        with_row = retain_file(user.id, alive.id, b"row", storage)
        orphan = uuid.uuid4()
        store_legacy_file(alive.id, b"alive", storage)
        store_legacy_file(orphan, b"orphan", storage)
        storage.save(AREA, "upload_staging/staged.fit", b"staged")
        age_stored_objects(tmp_path, 2 * 3600)
        recent = uuid.uuid4()
        store_legacy_file(recent, b"just written", storage)

        file_jobs.sweep_orphaned_activity_files()

        assert file_storage.read_file(orphan, None, storage) is None
        assert file_storage.read_file(alive.id, None, storage) == (".fit", b"alive")
        assert file_storage.read_file(recent, None, storage) is not None, "its activity row may not have committed"
        assert storage.get(AREA, f"files/{with_row}.fit") == b"row"
        assert storage.get(AREA, "upload_staging/staged.fit") == b"staged"
