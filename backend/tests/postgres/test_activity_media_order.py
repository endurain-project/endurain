"""Photos keep the order they were stored in, and a new activity gets a random UUID v4 id, against real PostgreSQL."""

import uuid

import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
from modules.activities.activity.constants import MediaType
from tests.postgres.test_transaction_ownership import _add_activity

_KEYS = [f"{index}_photo.jpg" for index in range(8)]


def test_a_new_activity_gets_a_random_version_4_id(pg_factory):
    ids = {_add_activity(pg_factory) for _ in range(3)}

    assert len(ids) == 3
    assert {activity_id.version for activity_id in ids} == {4}


def test_a_batch_of_photos_keeps_its_order(pg_factory):
    activity_id = _add_activity(pg_factory)
    batch = [
        activity_media_contracts.ActivityMediaCreate(media_path=key, media_type=MediaType.PHOTO, content_hash=None)
        for key in _KEYS
    ]

    with pg_factory() as db:
        activity_media_crud.create_activity_medias(batch, activity_id, db)
        db.commit()

    with pg_factory() as db:
        stored = activity_media_crud.get_activities_media([activity_id], db)
        owned = activity_media_crud.get_media_for_owned_activities([activity_id], db)
    assert [media.media_path for media in stored] == _KEYS
    assert [media.media_path for media in owned] == _KEYS


def test_photos_staged_one_by_one_in_one_transaction_keep_their_order(pg_factory):
    activity_id = _add_activity(pg_factory)

    with pg_factory() as db:
        for key in _KEYS:
            activity_media_crud.create_activity_media(activity_id, key, db)
        db.commit()

    with pg_factory() as db:
        stored = activity_media_crud.get_activities_media([activity_id], db)
    assert [media.media_path for media in stored] == _KEYS
    assert all(isinstance(media.id, uuid.UUID) for media in stored)
