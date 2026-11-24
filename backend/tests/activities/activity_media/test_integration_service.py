"""What other modules do with media: export and restore it with a profile archive, attach server-side bytes."""

import uuid

import pytest

import modules.activities.activity_media.crud as media_crud
import modules.activities.activity_media.integration_service as media_integration
from tests._factories.activities import make_activity, make_activity_media, make_stored_media
from tests._factories.users import make_user
from tests._helpers import images

_HASH = "b" * 64
_ARCHIVED = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _record(name: str, **fields) -> dict[str, object]:
    return {"activity_id": str(_ARCHIVED), "media_path": f"{_ARCHIVED}_{name}", "media_type": 1, **fields}


def _restore(db, activity, records):
    return media_integration.profile_contributor().restore(records, _ARCHIVED, activity, db)


class TestExport:
    def test_the_export_lists_the_media_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_activity_media(db, activity, "a.jpg")
        make_activity_media(db, other, "b.jpg")

        exported = media_integration.profile_contributor().export([activity.id], db)

        assert [m.media_path for m in exported] == ["a.jpg"]

    def test_the_media_of_several_activities_is_returned_as_the_per_activity_endpoint_returns_it(self, db, activity):
        make_stored_media(db, activity, images.png_with_text(), "a.png")

        media = media_integration.media_for_activities([activity.id, uuid.uuid4()], db)

        assert list(media) == [activity.id]
        assert media[activity.id][0].url.startswith("/") or "://" in media[activity.id][0].url


class TestRestore:
    def test_the_archived_media_is_re_keyed_onto_the_restored_activity_and_other_activities_are_skipped(
        self, db, activity
    ):
        records = [_record("a.jpg", content_hash=_HASH), {**_record("b.jpg"), "activity_id": str(uuid.uuid4())}]

        restored = _restore(db, activity, records)

        [stored] = media_crud.get_media_for_activity(activity.id, db)
        assert (restored, stored.media_path, stored.content_hash) == (1, f"{activity.id}_a.jpg", _HASH)

    def test_a_record_with_no_key_or_a_key_that_is_not_a_flat_name_is_skipped(self, db, activity):
        records = [_record("../escape.jpg"), {**_record("x.jpg"), "media_path": None}, _record("ok.jpg")]

        assert _restore(db, activity, records) == 1
        assert [m.media_path for m in media_crud.get_media_for_activity(activity.id, db)] == [f"{activity.id}_ok.jpg"]

    @pytest.mark.parametrize("bad_hash", ["short", "A" * 64, 12345])
    def test_a_malformed_content_hash_is_dropped_and_the_photo_is_restored_without_it(self, db, activity, bad_hash):
        assert _restore(db, activity, [_record("a.jpg", content_hash=bad_hash)]) == 1

        assert media_crud.get_media_for_activity(activity.id, db)[0].content_hash is None

    def test_two_archived_photos_with_the_same_hash_restore_one(self, db, activity):
        records = [_record("a.jpg", content_hash=_HASH), _record("b.jpg", content_hash=_HASH)]

        assert _restore(db, activity, records) == 1

    def test_nothing_matching_is_restored_as_zero(self, db, activity):
        assert _restore(db, activity, [{"activity_id": str(uuid.uuid4()), "media_path": "x_a.jpg"}]) == 0
        assert media_crud.count_media_for_activity(activity.id, db) == 0


class TestBlobs:
    def test_server_side_bytes_are_attached_to_an_activity_through_the_platform_storage(self, db, activity):
        record = media_integration.attach_media_bytes(activity.id, "sidecar.png", images.png_with_text(), db)

        assert media_crud.get_activity_media_by_id(record.id, db) is not None

    def test_the_blobs_of_an_activity_are_exported_and_restored_under_a_new_activity(self, db, activity):
        import jasil.runtime as platform_runtime

        storage = platform_runtime.get_active_platform().storage
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")
        target = make_activity(db, make_user(db).id)

        [(key, data)] = media_integration.list_media_blobs(activity.id, storage)
        restored_key = media_integration.store_media_blob(target.id, "copy", ".png", data, storage)

        assert key == record.media_path
        assert restored_key == f"{target.id}_copy.png"
        assert storage.get("activity_media", restored_key) == data
