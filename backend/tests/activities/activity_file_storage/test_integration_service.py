"""Tests for the retained-file surface: staging, attaching, reading and releasing a file with a row."""

import hashlib
import uuid

import pytest
from sqlalchemy import select, text

import core.exceptions as core_exceptions
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.models as file_models
from tests._factories.activities import make_activity
from tests._factories.ingestion import retain_file, store_legacy_file
from tests._factories.users import make_user

AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = activity_file_storage_constants.ActivityFileState


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows(committed_sessions) -> list[file_models.ActivityFile]:
    with committed_sessions() as db:
        return list(db.scalars(select(file_models.ActivityFile).order_by(file_models.ActivityFile.created_at)).all())


def _user(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
        return user


class TestStageFile:
    def test_records_a_pending_row_and_stores_the_blob_under_the_files_prefix(self, storage, committed_sessions):
        user = _user(committed_sessions)

        staged = file_storage.stage_file(user.id, _sha(b"fit"), ".FIT", b"fit", storage)

        assert staged.created is True
        assert staged.ref.storage_key == f"files/{staged.ref.file_id}.fit"
        assert storage.get(AREA, staged.ref.storage_key) == b"fit"
        (row,) = _rows(committed_sessions)
        assert (row.user_id, row.sha256, row.extension, row.size_bytes, row.state) == (
            user.id,
            _sha(b"fit"),
            ".fit",
            3,
            _State.PENDING,
        )

    def test_the_same_bytes_of_the_same_user_share_one_row(self, storage, committed_sessions):
        user = _user(committed_sessions)
        first = file_storage.stage_file(user.id, _sha(b"fit"), ".fit", b"fit", storage)

        second = file_storage.stage_file(user.id, _sha(b"fit"), ".fit", b"fit", storage)

        assert second.created is False
        assert second.ref.file_id == first.ref.file_id
        assert len(_rows(committed_sessions)) == 1

    def test_an_attached_row_is_taken_without_writing_the_blob_again(self, storage, committed_sessions):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            activity = make_activity(db, user.id)
            db.commit()
        file_id = retain_file(user.id, activity.id, b"fit", storage)
        storage.delete(AREA, f"files/{file_id}.fit")

        staged = file_storage.stage_file(user.id, _sha(b"fit"), ".fit", b"fit", storage)

        assert staged.ref.file_id == file_id
        assert storage.get(AREA, staged.ref.storage_key) is None, "an attached file's blob is not rewritten"

    def test_the_same_bytes_of_another_user_get_their_own_row(self, storage, committed_sessions):
        first_user, second_user = _user(committed_sessions), None
        with committed_sessions() as db:
            second_user = make_user(db)
            db.commit()
        first = file_storage.stage_file(first_user.id, _sha(b"fit"), ".fit", b"fit", storage)

        second = file_storage.stage_file(second_user.id, _sha(b"fit"), ".fit", b"fit", storage)

        assert second.created is True
        assert second.ref.file_id != first.ref.file_id

    def test_a_row_being_deleted_is_not_taken_so_the_new_blob_has_its_own_key(self, storage, committed_sessions):
        user = _user(committed_sessions)
        old = file_storage.stage_file(user.id, _sha(b"fit"), ".fit", b"fit", storage)
        with committed_sessions() as db:
            db.execute(text("UPDATE activity_files SET state = 'deleting'"))
            db.commit()

        new = file_storage.stage_file(user.id, _sha(b"fit"), ".fit", b"fit", storage)

        assert new.created is True
        assert new.ref.storage_key != old.ref.storage_key


class TestMarkAttached:
    def test_moves_a_pending_row_to_attached(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"x"), ".gpx", b"x", storage)

        with committed_sessions() as db:
            file_storage.mark_attached(staged.ref.file_id, db)
            db.commit()

        assert _rows(committed_sessions)[0].state == _State.ATTACHED

    def test_refuses_a_row_that_is_being_deleted_so_the_caller_stages_a_new_one(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"x"), ".gpx", b"x", storage)
        with committed_sessions() as db:
            db.execute(text("UPDATE activity_files SET state = 'deleting'"))
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            file_storage.mark_attached(staged.ref.file_id, db)

    def test_refuses_a_row_that_is_gone(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            file_storage.mark_attached(uuid.uuid4(), db)


class TestReadFile:
    def test_reads_the_blob_a_row_names(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"gpx"), ".gpx", b"gpx", storage)

        assert file_storage.read_file(uuid.uuid4(), staged.ref, storage) == (".gpx", b"gpx")

    def test_a_row_whose_blob_is_missing_has_no_file(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"gpx"), ".gpx", b"gpx", storage)
        storage.delete(AREA, staged.ref.storage_key)

        assert file_storage.read_file(uuid.uuid4(), staged.ref, storage) is None

    @pytest.mark.parametrize("extension", [".gpx", ".fit", ".tcx"])
    def test_an_activity_without_a_row_is_probed_under_its_own_id(self, storage, extension):
        activity_id = uuid.uuid4()
        store_legacy_file(activity_id, b"legacy", storage, extension=extension)

        assert file_storage.read_file(activity_id, None, storage) == (extension, b"legacy")

    def test_an_activity_with_no_file_at_all_has_none(self, storage):
        assert file_storage.read_file(uuid.uuid4(), None, storage) is None

    def test_resolves_the_references_of_the_given_rows(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"gpx"), ".gpx", b"gpx", storage)

        with committed_sessions() as db:
            refs = file_storage.resolve_refs([staged.ref.file_id, uuid.uuid4()], db)

        assert refs == {staged.ref.file_id: staged.ref}


class TestRelease:
    def test_releasing_an_unattached_row_removes_its_blob_and_row(self, storage, committed_sessions):
        user = _user(committed_sessions)
        staged = file_storage.stage_file(user.id, _sha(b"x"), ".fit", b"x", storage)

        file_storage.release_unattached(staged.ref.file_id, storage)

        assert storage.get(AREA, staged.ref.storage_key) is None
        assert _rows(committed_sessions) == []

    def test_an_attached_row_is_not_released_as_unattached(self, storage, committed_sessions):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            activity = make_activity(db, user.id)
            db.commit()
        file_id = retain_file(user.id, activity.id, b"x", storage)

        file_storage.release_unattached(file_id, storage)

        assert storage.get(AREA, f"files/{file_id}.fit") == b"x"
        assert _rows(committed_sessions)[0].state == _State.ATTACHED

    def test_deletes_the_file_an_activity_without_a_row_stored(self, storage):
        activity_id = uuid.uuid4()
        store_legacy_file(activity_id, b"x", storage)

        file_storage.delete_legacy_activity_file(activity_id, storage)

        assert file_storage.read_file(activity_id, None, storage) is None


class TestEraseUserFiles:
    def test_removes_every_file_of_the_user_in_any_state_and_no_other(self, storage, committed_sessions):
        user, other = _user(committed_sessions), None
        with committed_sessions() as db:
            other = make_user(db)
            db.commit()
        pending = file_storage.stage_file(user.id, _sha(b"a"), ".fit", b"a", storage)
        deleting = file_storage.stage_file(user.id, _sha(b"b"), ".fit", b"b", storage)
        with committed_sessions() as db:
            db.execute(
                text("UPDATE activity_files SET state = 'deleting' WHERE id = :id"), {"id": deleting.ref.file_id}
            )
            db.commit()
        kept = file_storage.stage_file(other.id, _sha(b"a"), ".fit", b"a", storage)

        file_storage.erase_user_files(user.id, storage)

        assert storage.get(AREA, pending.ref.storage_key) is None
        assert storage.get(AREA, deleting.ref.storage_key) is None
        assert storage.get(AREA, kept.ref.storage_key) == b"a"
        assert [row.id for row in _rows(committed_sessions)] == [kept.ref.file_id]


def test_the_legacy_key_parser_ignores_the_keys_of_files_with_a_row():
    file_id = uuid.uuid4()
    assert activity_file_storage_files.activity_id_of_processed_key(f"files/{file_id}.fit") is None
    assert activity_file_storage_files.activity_id_of_processed_key(f"processed/{file_id}.fit") == file_id
