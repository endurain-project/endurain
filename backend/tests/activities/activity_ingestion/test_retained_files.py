"""The pipeline stages a file row and blob, then attaches it in the transaction that stores the activity."""

import pytest
from sqlalchemy import text

import core.config as core_config
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity_file_storage.constants as file_storage_constants
from tests._factories.ingestion import activities_of, file_rows, fit_file, retained_file

_API = core_config.ROOT_PATH
_State = file_storage_constants.ActivityFileState


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _upload(user, name: str, content: bytes):
    return user.client.post(f"{_API}/activities/upload", files={"file": (name, content)})


def test_an_upload_stores_an_attached_row_the_activity_references(me, pool, committed_sessions, storage):
    content = fit_file()

    _upload(me, "ride.fit", content)
    pool.drain()

    (activity,) = activities_of(committed_sessions, me.user.id)
    (row,) = file_rows(committed_sessions)
    assert (row.state, row.user_id, row.extension, row.size_bytes) == (
        _State.ATTACHED,
        me.user.id,
        ".fit",
        len(content),
    )
    assert activity.file_id == row.id
    assert row.storage_key == f"files/{row.id}.fit"
    assert storage.get("activity_files", row.storage_key) == content
    assert retained_file(activity.id, storage) == (".fit", content)


def test_the_same_bytes_uploaded_again_add_no_row_and_no_blob(me, pool, committed_sessions, storage):
    content = fit_file()
    _upload(me, "ride.fit", content)
    pool.drain()
    (first,) = file_rows(committed_sessions)

    _upload(me, "again.fit", content)
    pool.drain()

    assert len(activities_of(committed_sessions, me.user.id)) == 1
    assert [row.id for row in file_rows(committed_sessions)] == [first.id]
    assert len(list(storage.list_keys("activity_files", "files/"))) == 1


def test_a_failure_between_the_blob_and_the_activity_leaves_a_pending_row_the_retry_attaches(
    me, pool, committed_sessions, storage, monkeypatch
):
    content = fit_file()
    real = activity_event_publishers.publish_activity_created

    def fail(*args, **kwargs):
        raise RuntimeError("crash before the commit")

    monkeypatch.setattr(activity_event_publishers, "publish_activity_created", fail)
    _upload(me, "ride.fit", content)
    pool.drain()
    (row,) = file_rows(committed_sessions)
    assert (row.state, activities_of(committed_sessions, me.user.id)) == (_State.PENDING, [])
    assert storage.get("activity_files", row.storage_key) == content

    monkeypatch.setattr(activity_event_publishers, "publish_activity_created", real)
    _upload(me, "again.fit", content)
    pool.drain()

    (retried,) = file_rows(committed_sessions)
    assert (retried.id, retried.state) == (row.id, _State.ATTACHED)
    (activity,) = activities_of(committed_sessions, me.user.id)
    assert activity.file_id == row.id


def test_a_file_that_yields_no_activity_leaves_no_row(me, pool, committed_sessions, storage):
    _upload(
        me,
        "empty.gpx",
        b'<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"/>',
    )
    pool.drain()

    assert file_rows(committed_sessions) == []
    assert list(storage.list_keys("activity_files", "files/")) == []


def test_an_upload_of_a_legacy_activitys_file_neither_adopts_it_nor_leaves_a_row(me, pool, committed_sessions, storage):
    content = fit_file()
    _upload(me, "ride.fit", content)
    pool.drain()
    (activity,) = activities_of(committed_sessions, me.user.id)
    (row,) = file_rows(committed_sessions)
    with committed_sessions() as db:
        db.execute(text("UPDATE activities SET file_id = NULL"))
        db.execute(text("DELETE FROM activity_files"))
        db.commit()
    storage.delete("activity_files", row.storage_key)
    storage.save("activity_files", f"processed/{activity.id}.fit", content)

    _upload(me, "again.fit", content)
    pool.drain()

    assert file_rows(committed_sessions) == []
    assert list(storage.list_keys("activity_files", "files/")) == []
    assert activities_of(committed_sessions, me.user.id)[0].file_id is None
    assert retained_file(activity.id, storage) == (".fit", content)
