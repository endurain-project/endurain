"""Generating, backfilling, regenerating and deleting thumbnails, against a real database and tile server."""

import contextlib
import io
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import pytest
from jasil._core.job_context import job_lease
from jasil.backends.storage_local import LocalStorage
from PIL import Image
from sqlalchemy import delete

import core.exceptions as core_exceptions
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_thumbnail.constants as thumbnail_constants
import modules.activities.activity_thumbnail.service as thumbnail_service
import modules.activities.activity_thumbnail.signing as thumbnail_signing
import modules.server_settings.constants as server_settings_constants
from tests._factories.activities import DEFAULT_START, make_activity, make_stream
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_AREA = thumbnail_constants.THUMBNAIL_STORAGE_AREA
_MAP = stream_constants.STREAM_TYPE_MAP
_ROUTE = [{"lat": 38.70, "lon": -9.10}, {"lat": 38.72, "lon": -9.14}]


class UnavailableStorage(LocalStorage):
    """Local storage whose deletes fail, as an object store that is down does."""

    def delete(self, area: str, key: str) -> None:
        raise platform_providers.StorageBackendUnavailableError("storage down")


class HeldLock:
    """A lock provider whose locks another replica already holds."""

    @contextlib.contextmanager
    def try_acquire(self, name: str):
        yield False


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


@pytest.fixture
def clock():
    return platform_runtime.get_active_platform().clock


@pytest.fixture
def owner(db):
    return make_user(db)


@pytest.fixture
def tiles(db, tile_server):
    """The server's tile source set to the real tile server."""
    edit_server_settings(db, tileserver_url=tile_server.url(), map_background_color="#112233")
    return tile_server


def _routed(db, owner, day: int = 0):
    start = DEFAULT_START + timedelta(days=day)
    activity = make_activity(db, owner.id, start_time=start, end_time=start + timedelta(hours=1))
    make_stream(db, activity, _MAP, _ROUTE)
    return activity


def _plain(db, owner, day: int = 0):
    start = DEFAULT_START + timedelta(days=day)
    return make_activity(db, owner.id, start_time=start, end_time=start + timedelta(hours=1))


def _key_of(db, activity) -> str | None:
    db.expire_all()
    return db.get(activity_models.Activity, activity.id).map_thumbnail_path


class TestResolveTileSettings:
    def test_the_configured_source_colour_and_decrypted_key_are_used(self, db):
        edit_server_settings(
            db,
            tileserver_url="https://tiles.example/{z}/{x}/{y}.png",
            map_background_color="#abcdef",
            tileserver_api_key="k",
        )

        assert thumbnail_service.resolve_tile_settings(db) == (
            "https://tiles.example/{z}/{x}/{y}.png",
            "#abcdef",
            "k",
        )

    def test_the_seeded_settings_name_the_built_in_tile_source_and_no_key(self, db):
        url, _, key = thumbnail_service.resolve_tile_settings(db)

        assert (url, key) == (server_settings_constants.DEFAULT_TILE_URL, None)


class TestGenerateForActivity:
    def test_a_route_is_rendered_stored_under_the_activitys_key_and_recorded_on_the_activity(
        self, db, owner, storage, tiles
    ):
        activity = _routed(db, owner)

        key = thumbnail_service.generate_thumbnail_for_activity(activity.id, owner.id, storage, db)

        assert key == f"{activity.id}.webp"
        assert _key_of(db, activity) == key
        with Image.open(io.BytesIO(storage.get(_AREA, key))) as image:
            assert (image.format, image.size) == ("WEBP", (1200, 400))
        assert tiles.requests

    @pytest.mark.parametrize("waypoints", [None, [], _ROUTE[:1]])
    def test_an_activity_without_a_route_of_two_points_stores_nothing_and_asks_for_no_tiles(
        self, db, owner, storage, tiles, waypoints
    ):
        activity = _plain(db, owner)
        if waypoints is not None:
            make_stream(db, activity, _MAP, waypoints)

        assert thumbnail_service.generate_thumbnail_for_activity(activity.id, owner.id, storage, db) is None

        assert (_key_of(db, activity), list(storage.list_keys(_AREA, "")), tiles.requests) == (None, [], [])

    def test_a_render_that_is_skipped_stores_nothing(self, db, owner, storage):
        edit_server_settings(db, tileserver_url="https://tiles.stadiamaps.com/{z}/{x}/{y}.png", tileserver_api_key=None)
        activity = _routed(db, owner)

        assert thumbnail_service.generate_thumbnail_for_activity(activity.id, owner.id, storage, db) is None

        assert (_key_of(db, activity), list(storage.list_keys(_AREA, ""))) == (None, [])

    def test_a_tile_server_that_fails_is_a_processing_error_and_stores_nothing(self, db, owner, storage, tiles):
        tiles.status = 500
        activity = _routed(db, owner)

        with pytest.raises(core_exceptions.ProcessingError):
            thumbnail_service.generate_thumbnail_for_activity(activity.id, owner.id, storage, db)

        assert (_key_of(db, activity), list(storage.list_keys(_AREA, ""))) == (None, [])

    def test_an_activity_deleted_while_it_renders_leaves_no_blob(self, committed_sessions, storage, tile_server):
        with committed_sessions() as db:
            edit_server_settings(db, tileserver_url=tile_server.url())
            user = make_user(db)
            activity = _routed(db, user)
            db.commit()

        def delete_activity(_path: str) -> None:
            with committed_sessions() as other:
                other.execute(delete(activity_models.Activity).where(activity_models.Activity.id == activity.id))
                other.commit()

        tile_server.on_request = delete_activity
        with committed_sessions() as db:
            key = thumbnail_service.generate_thumbnail_for_activity(activity.id, user.id, storage, db)

        assert key is None
        assert list(storage.list_keys(_AREA, "")) == []


class TestReadAndDelete:
    def test_a_valid_token_reads_the_stored_bytes(self, storage):
        activity_id = uuid.uuid4()
        storage.save(_AREA, thumbnail_signing.thumbnail_key(activity_id), b"webp")

        token = thumbnail_signing.sign_thumbnail_token(activity_id)

        assert thumbnail_service.read_activity_thumbnail(activity_id, token, storage) == b"webp"

    def test_a_forged_token_and_a_missing_blob_are_both_not_found(self, storage):
        activity_id = uuid.uuid4()
        storage.save(_AREA, thumbnail_signing.thumbnail_key(activity_id), b"webp")

        with pytest.raises(core_exceptions.AccessConcealedError):
            thumbnail_service.read_activity_thumbnail(activity_id, "forged", storage)
        with pytest.raises(core_exceptions.NotFoundError):
            other = uuid.uuid4()
            thumbnail_service.read_activity_thumbnail(other, thumbnail_signing.sign_thumbnail_token(other), storage)

    def test_deleting_a_thumbnail_removes_the_blob_and_is_idempotent(self, storage):
        activity_id = uuid.uuid4()
        storage.save(_AREA, thumbnail_signing.thumbnail_key(activity_id), b"webp")

        thumbnail_service.delete_activity_thumbnail(activity_id, storage)
        thumbnail_service.delete_activity_thumbnail(activity_id, storage)

        assert list(storage.list_keys(_AREA, "")) == []


class TestBackfill:
    def test_every_activity_with_a_route_gets_a_thumbnail_and_the_others_are_left_without(
        self, db, owner, storage, clock, tiles
    ):
        first, second, plain = _routed(db, owner, 0), _routed(db, owner, 1), _plain(db, owner, 2)

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert _key_of(db, first) == f"{first.id}.webp" and _key_of(db, second) == f"{second.id}.webp"
        assert _key_of(db, plain) is None
        assert sorted(storage.list_keys(_AREA, "")) == sorted([f"{first.id}.webp", f"{second.id}.webp"])

    def test_an_activity_that_ended_a_pass_without_a_thumbnail_waits_before_it_is_tried_again(
        self, db, owner, storage, clock, tiles
    ):
        activity = _plain(db, owner)
        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)
        make_stream(db, activity, _MAP, _ROUTE)

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)
        still_waiting = _key_of(db, activity)
        clock.advance(thumbnail_service.THUMBNAIL_RETRY_DELAY.total_seconds() + 1)
        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (still_waiting, _key_of(db, activity)) == (None, f"{activity.id}.webp")

    def test_a_tile_server_that_fails_is_survived_and_the_activity_is_tried_again_later(
        self, db, owner, storage, clock, tiles
    ):
        activity = _routed(db, owner)
        tiles.status = 500
        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)
        failed = _key_of(db, activity)
        tiles.status = 200
        clock.advance(thumbnail_service.THUMBNAIL_RETRY_DELAY.total_seconds() + 1)

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (failed, _key_of(db, activity)) == (None, f"{activity.id}.webp")

    def test_one_activity_that_cannot_be_rendered_does_not_stop_the_pass(self, db, owner, storage, clock, tiles):
        bad = _plain(db, owner, 0)
        make_stream(db, bad, _MAP, [{"lat": 38.7}, {"lat": 38.8}])
        good = _routed(db, owner, 1)

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (_key_of(db, bad), _key_of(db, good)) == (None, f"{good.id}.webp")

    def test_a_key_whose_blob_is_gone_is_cleared_and_one_whose_blob_exists_is_kept(
        self, db, owner, storage, clock, tiles
    ):
        gone, kept = _plain(db, owner, 0), _plain(db, owner, 1)
        activity_integration.set_thumbnail_key(gone.id, f"{gone.id}.webp", db)
        activity_integration.set_thumbnail_key(kept.id, f"{kept.id}.webp", db)
        storage.save(_AREA, f"{kept.id}.webp", b"webp")

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (_key_of(db, gone), _key_of(db, kept)) == (None, f"{kept.id}.webp")
        assert tiles.requests == []

    def test_a_key_outside_the_uuid_layout_whose_blob_exists_survives(self, db, owner, storage, clock, tiles):
        activity = _plain(db, owner)
        activity_integration.set_thumbnail_key(activity.id, "custom-name.webp", db)
        storage.save(_AREA, "custom-name.webp", b"webp")

        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert _key_of(db, activity) == "custom-name.webp"

    def test_a_pass_with_nothing_to_do_does_nothing(self, db, storage, clock, tiles):
        thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (list(storage.list_keys(_AREA, "")), tiles.requests) == ([], [])


class TestLeaseLost:
    """A durable job whose lease is gone stops at its next unit of work; the next pass reconciles."""

    @staticmethod
    def _lost() -> threading.Event:
        lost = threading.Event()
        lost.set()
        return lost

    def test_a_backfill_that_lost_its_lease_renders_nothing(self, db, owner, storage, clock, tiles):
        activity = _routed(db, owner)

        with job_lease(self._lost()):
            thumbnail_service.generate_missing_activity_thumbnails(storage, clock, db)

        assert (_key_of(db, activity), tiles.requests) == (None, [])

    def test_a_regeneration_that_lost_its_lease_leaves_the_keys_and_the_blobs_for_the_next_pass(
        self, db, owner, storage, clock, tiles
    ):
        activity = _routed(db, owner)
        activity_integration.set_thumbnail_key(activity.id, f"{activity.id}.webp", db)
        storage.save(_AREA, f"{activity.id}.webp", b"kept")

        with job_lease(self._lost()):
            thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
                storage, platform_runtime.get_active_platform().lock, clock, db
            )

        assert (_key_of(db, activity), storage.get(_AREA, f"{activity.id}.webp")) == (f"{activity.id}.webp", b"kept")
        assert tiles.requests == []


class TestRegenerateAll:
    def test_every_thumbnail_is_deleted_and_rendered_again_from_the_current_tile_source(
        self, db, owner, storage, clock, tiles
    ):
        routed, plain = _routed(db, owner, 0), _plain(db, owner, 1)
        activity_integration.set_thumbnail_key(routed.id, f"{routed.id}.webp", db)
        activity_integration.set_thumbnail_key(plain.id, f"{plain.id}.webp", db)
        storage.save(_AREA, f"{routed.id}.webp", b"stale")
        storage.save(_AREA, f"{plain.id}.webp", b"stale")

        thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
            storage, platform_runtime.get_active_platform().lock, clock, db
        )

        assert _key_of(db, plain) is None
        assert list(storage.list_keys(_AREA, "")) == [f"{routed.id}.webp"]
        assert storage.get(_AREA, f"{routed.id}.webp") != b"stale"

    def test_another_replica_holding_the_lock_is_a_conflict_that_touches_nothing(
        self, db, owner, storage, clock, tiles
    ):
        activity = _routed(db, owner)
        activity_integration.set_thumbnail_key(activity.id, f"{activity.id}.webp", db)
        storage.save(_AREA, f"{activity.id}.webp", b"kept")

        with pytest.raises(core_exceptions.ConflictError):
            thumbnail_service.delete_and_regenerate_all_activity_thumbnails(storage, HeldLock(), clock, db)

        assert (_key_of(db, activity), storage.get(_AREA, f"{activity.id}.webp")) == (f"{activity.id}.webp", b"kept")

    def test_a_blob_that_cannot_be_deleted_is_logged_and_the_keys_are_still_cleared(
        self, db, owner, clock, tiles, tmp_path
    ):
        down = UnavailableStorage(str(tmp_path / "down"), plain_areas=frozenset({_AREA}))
        activity = _plain(db, owner)
        activity_integration.set_thumbnail_key(activity.id, f"{activity.id}.webp", db)
        down.save(_AREA, f"{activity.id}.webp", b"stale")

        thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
            down, platform_runtime.get_active_platform().lock, clock, db
        )

        assert _key_of(db, activity) is None


class TestSweep:
    def test_an_old_thumbnail_of_a_deleted_activity_is_swept_and_the_rest_are_kept(self, db, owner, tmp_path):
        plain = LocalStorage(str(tmp_path / "plain"), plain_areas=frozenset({_AREA}))
        alive = _plain(db, owner)
        gone = uuid.uuid4()
        for name in (f"{alive.id}.webp", f"{gone}.webp", "not-a-thumbnail.webp", f"{gone}.png"):
            plain.save(_AREA, name, b"x")
            old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
            os.utime(tmp_path / "plain" / _AREA / name, (old, old))

        removed = thumbnail_service.sweep_orphaned_thumbnails(plain)

        assert removed == 1
        assert sorted(plain.list_keys(_AREA, "")) == sorted([f"{alive.id}.webp", "not-a-thumbnail.webp", f"{gone}.png"])
