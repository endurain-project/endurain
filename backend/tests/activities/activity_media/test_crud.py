"""Media records: the order photos keep, the unique keys that make a re-store a no-op, and the lookups."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.activities.activity_media.contracts as media_contracts
import modules.activities.activity_media.crud as media_crud
import modules.activities.activity_media.models as media_models
from modules.activities.activity.constants import MediaType
from tests._factories.activities import DEFAULT_START, make_activity, make_activity_media
from tests._factories.users import make_user

_HASH = "a" * 64
_KEYS = [f"{index}_photo.jpg" for index in range(8)]


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _at(day: int) -> datetime:
    return DEFAULT_START + timedelta(days=day)


def _batch(*keys: str) -> list[media_contracts.ActivityMediaCreate]:
    return [
        media_contracts.ActivityMediaCreate(media_path=key, media_type=MediaType.PHOTO, content_hash=None)
        for key in keys
    ]


class TestPhotoOrder:
    def test_a_new_activity_gets_a_random_version_4_id(self, db):
        user = make_user(db)
        ids = [make_activity(db, user.id, start_time=_at(day)).id for day in range(3)]

        assert len(set(ids)) == 3
        assert {activity_id.version for activity_id in ids} == {4}

    def test_a_batch_of_photos_keeps_its_order(self, db, activity):
        media_crud.create_activity_medias(_batch(*_KEYS), activity.id, db)

        stored = media_crud.get_activities_media([activity.id], db)
        owned = media_crud.get_media_for_owned_activities([activity.id], db)
        paged = media_crud.get_media_for_activity(activity.id, db)

        assert [m.media_path for m in stored] == _KEYS
        assert [m.media_path for m in owned] == _KEYS
        assert [m.media_path for m in paged] == _KEYS

    def test_photos_staged_one_by_one_keep_their_order_and_get_uuid_ids(self, db, activity):
        for key in _KEYS:
            media_crud.create_activity_media(activity.id, key, db)

        stored = media_crud.get_activities_media([activity.id], db)

        assert [m.media_path for m in stored] == _KEYS
        assert all(isinstance(m.id, uuid.UUID) for m in stored)


class TestCreate:
    def test_a_record_keeps_its_key_hash_and_photo_type(self, db, activity):
        record = media_crud.create_activity_media(activity.id, "k_1.jpg", db, content_hash=_HASH)

        row = db.get(media_models.ActivityMedia, record.id)
        assert (row.activity_id, row.media_path, row.content_hash, row.media_type) == (
            activity.id,
            "k_1.jpg",
            _HASH,
            MediaType.PHOTO.stored,
        )

    def test_the_same_storage_key_twice_is_a_conflict(self, db, activity):
        make_activity_media(db, activity, "same.jpg")

        with pytest.raises(core_exceptions.ConflictError):
            media_crud.create_activity_media(activity.id, "same.jpg", db)

    def test_the_same_content_twice_for_one_activity_is_a_conflict_but_not_for_two(self, db, activity):
        other = make_activity(db, make_user(db).id)
        media_crud.create_activity_media(activity.id, "a.jpg", db, content_hash=_HASH)
        media_crud.create_activity_media(other.id, "b.jpg", db, content_hash=_HASH)

        with pytest.raises(core_exceptions.ConflictError):
            media_crud.create_activity_media(activity.id, "c.jpg", db, content_hash=_HASH)

    def test_an_empty_batch_stores_nothing(self, db, activity):
        media_crud.create_activity_medias([], activity.id, db)

        assert media_crud.count_media_for_activity(activity.id, db) == 0


class TestRead:
    def test_a_record_is_read_by_id_and_a_missing_id_is_none(self, db, activity):
        record = make_activity_media(db, activity, "a.jpg")

        assert media_crud.get_activity_media_by_id(record.id, db).media_path == "a.jpg"
        assert media_crud.get_activity_media_by_id(uuid.uuid4(), db) is None

    def test_a_page_holds_its_slice_and_the_count_covers_all_records(self, db, activity):
        media_crud.create_activity_medias(_batch("1.jpg", "2.jpg", "3.jpg"), activity.id, db)

        page = media_crud.get_media_for_activity(activity.id, db, page_number=2, num_records=2)

        assert [m.media_path for m in page] == ["3.jpg"]
        assert media_crud.count_media_for_activity(activity.id, db) == 3

    def test_another_activitys_media_is_not_read_or_counted(self, db, activity):
        make_activity_media(db, make_activity(db, make_user(db).id), "theirs.jpg")

        assert media_crud.get_media_for_activity(activity.id, db) == []
        assert media_crud.count_media_for_activity(activity.id, db) == 0

    def test_several_activities_are_read_at_once_and_none_reads_nothing(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_activity_media(db, activity, "a.jpg")
        make_activity_media(db, other, "b.jpg")

        assert {m.media_path for m in media_crud.get_activities_media([activity.id, other.id], db)} == {
            "a.jpg",
            "b.jpg",
        }
        assert media_crud.get_activities_media([], db) == []
        assert media_crud.get_media_for_owned_activities([], db) == []

    def test_every_record_is_listed(self, db, activity):
        make_activity_media(db, activity, "a.jpg")

        assert [m.media_path for m in media_crud.get_all_activity_media(db)] == ["a.jpg"]

    def test_the_keys_records_still_name_are_found_among_those_asked_about(self, db, activity):
        make_activity_media(db, activity, "a.jpg")

        assert media_crud.get_existing_media_paths(["a.jpg", "gone.jpg"], db) == {"a.jpg"}
        assert media_crud.get_existing_media_paths([], db) == set()

    def test_a_record_is_found_by_the_hash_of_its_content_within_its_activity(self, db, activity):
        other = make_activity(db, make_user(db).id)
        record = media_crud.create_activity_media(activity.id, "a.jpg", db, content_hash=_HASH)

        assert media_crud.get_activity_media_by_content_hash(activity.id, _HASH, db).id == record.id
        assert media_crud.get_activity_media_by_content_hash(other.id, _HASH, db) is None


class TestChange:
    def test_a_key_is_replaced_only_where_the_record_still_holds_the_key_it_was_read_with(self, db, activity):
        stale = make_activity_media(db, activity, "old.jpg")
        fresh = make_activity_media(db, activity, "kept.jpg")

        media_crud.replace_activity_media_paths(
            [(stale.id, "old.jpg", "new.jpg"), (fresh.id, "something-else.jpg", "lost.jpg")], db
        )

        paths = db.scalars(select(media_models.ActivityMedia.media_path)).all()
        assert sorted(paths) == ["kept.jpg", "new.jpg"]

    def test_a_record_is_deleted_and_a_missing_one_is_not_found(self, db, activity):
        record = make_activity_media(db, activity, "a.jpg")

        media_crud.delete_activity_media(record.id, db)

        assert media_crud.get_activity_media_by_id(record.id, db) is None
        with pytest.raises(core_exceptions.NotFoundError):
            media_crud.delete_activity_media(record.id, db)
