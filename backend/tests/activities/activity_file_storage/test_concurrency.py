"""A file's last reference going away races an upload attaching to the same file; the file row's lock settles it."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity_file_storage.constants as file_storage_constants
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.service as file_storage_service
from tests._factories.activities import make_activity_at
from tests._factories.ingestion import file_rows, retain_file
from tests._factories.users import make_user
from tests._helpers.concurrency import Worker, wait_until_a_session_waits_for_a_lock

_AREA = file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = file_storage_constants.ActivityFileState
_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _delete(committed_sessions, activity_id: uuid.UUID) -> None:
    with committed_sessions() as db:
        db.execute(sa.delete(activity_models.Activity).where(activity_models.Activity.id == activity_id))
        db.commit()


def test_a_cleanup_waits_for_an_upload_attaching_to_the_file_and_then_keeps_it(committed_sessions, storage):
    with committed_sessions() as db:
        user = make_user(db)
        gone = make_activity_at(db, user.id, _NOW)
        newcomer = make_activity_at(db, user.id, _NOW + timedelta(days=1))
        db.commit()
    file_id = retain_file(user.id, gone.id, b"shared", storage)
    _delete(committed_sessions, gone.id)

    with committed_sessions() as uploader:
        assert activity_integration.set_file_id(newcomer.id, file_id, uploader)
        worker = Worker(lambda: file_storage_service.release_unreferenced(file_id, storage))
        wait_until_a_session_waits_for_a_lock(committed_sessions)
        file_storage.mark_attached(file_id, uploader)
        uploader.commit()
        worker.join()

    assert worker.error is None
    assert storage.get(_AREA, f"files/{file_id}.fit") == b"shared"
    assert [(row.id, row.state) for row in file_rows(committed_sessions)] == [(file_id, _State.ATTACHED)]


def test_an_upload_meeting_a_file_the_cleanup_removed_is_refused_and_stages_a_new_row(committed_sessions, storage):
    with committed_sessions() as db:
        user = make_user(db)
        gone = make_activity_at(db, user.id, _NOW)
        db.commit()
    file_id = retain_file(user.id, gone.id, b"shared", storage)
    _delete(committed_sessions, gone.id)

    file_storage_service.release_unreferenced(file_id, storage)

    assert storage.get(_AREA, f"files/{file_id}.fit") is None
    with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
        file_storage.mark_attached(file_id, db)
    staged = file_storage.stage_file(user.id, hashlib.sha256(b"shared").hexdigest(), ".fit", b"shared", storage)
    assert staged.created is True
    assert storage.get(_AREA, staged.ref.storage_key) == b"shared"
