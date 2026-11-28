"""An activity's sources: exact matching on re-import, provider ids read from them, the Strava rules and the regroup."""

import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.service as activity_service
import modules.activities.activity.source_crud as activity_source_crud
from tests._factories.activities import (
    DEFAULT_START,
    make_activity,
    make_activity_at,
    make_parsed_activity,
    make_source,
)
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_SHA = "c" * 64
_LATER = DEFAULT_START + timedelta(hours=3)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


def _upload(user_id: uuid.UUID, file_hash: str = _SHA, start: datetime = DEFAULT_START, **fields):
    return make_parsed_activity(
        user_id, source=activity_contracts.ImportSource(kind="upload", content_hash=file_hash), start=start, **fields
    )


def _store(db, parsed):
    return ingestion_service.store_parsed_activity(parsed, db)


def _count(db) -> int:
    return len(db.scalars(select(activity_models.Activity.id)).all())


class TestExactMatching:
    def test_the_same_file_twice_is_one_activity(self, db, owner):
        first = _store(db, _upload(owner.id))
        again = _store(db, _upload(owner.id))

        assert again.id == first.id
        assert _count(db) == 1

    def test_the_same_garmin_activity_twice_is_one_activity(self, db, owner):
        first = _store(db, make_parsed_activity(owner.id, garminconnect_activity_id=8))
        again = _store(db, make_parsed_activity(owner.id, garminconnect_activity_id=8))

        assert again.id == first.id

    def test_the_same_strava_activity_twice_is_one_activity_whatever_its_start(self, db, owner):
        first = _store(db, make_parsed_activity(owner.id, strava_activity_id=9))
        again = _store(db, make_parsed_activity(owner.id, strava_activity_id=9, start=_LATER))

        assert again.id == first.id

    def test_a_multi_activity_file_holds_one_activity_per_start_and_each_is_a_no_op_on_re_import(self, db, owner):
        first = _store(db, _upload(owner.id))
        second = _store(db, _upload(owner.id, start=_LATER))

        assert first.id != second.id
        assert _store(db, _upload(owner.id)).id == first.id
        assert _store(db, _upload(owner.id, start=_LATER)).id == second.id
        assert _count(db) == 2

    def test_the_start_is_matched_in_whole_seconds(self, db, owner):
        first = _store(db, _upload(owner.id))

        again = _store(db, _upload(owner.id, start=DEFAULT_START + timedelta(milliseconds=400)))

        assert again.id == first.id

    def test_another_users_identity_is_a_different_activity(self, db, owner, other):
        first = _store(db, _upload(owner.id))
        theirs = _store(db, _upload(other.id))

        assert theirs.id != first.id

    def test_a_garmin_and_a_file_identity_are_independent(self, db, owner):
        first = _store(db, make_parsed_activity(owner.id, garminconnect_activity_id=8))
        second = _store(db, _upload(owner.id, start=_LATER))

        assert first.id != second.id

    def test_a_source_with_nothing_to_identify_it_is_stored_every_time(self, db, owner):
        first = _store(db, make_parsed_activity(owner.id, start=DEFAULT_START))
        second = _store(db, make_parsed_activity(owner.id, start=_LATER))

        assert first.id != second.id
        assert not activity_source_crud.has_sources(first.id, db)

    def test_a_group_matches_on_its_whole_file(self, db, owner):
        legs = [_upload(owner.id, start=DEFAULT_START + timedelta(minutes=20 * n)) for n in range(2)]
        parent = _upload(owner.id, activity_type=activity_constants.ActivityType.MULTISPORT.stored)

        [first] = ingestion_service.store_parsed_group(parent, legs, db)
        [again] = ingestion_service.store_parsed_group(parent, legs, db)

        assert again.id == first.id
        assert _count(db) == 3

    def test_two_imports_racing_for_one_source_store_it_once(self, committed_sessions, arrange):
        user = arrange(lambda db: make_user(db, timezone="UTC"))
        barrier = threading.Barrier(5)
        ids: list[uuid.UUID] = []
        errors: list[BaseException] = []

        def import_it() -> None:
            try:
                barrier.wait()
                with committed_sessions() as db:
                    stored = _store(db, make_parsed_activity(user.id, strava_activity_id=1234))
                    db.commit()
                    ids.append(stored.id)
            except BaseException as err:
                errors.append(err)

        threads = [threading.Thread(target=import_it) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(set(ids)) == 1
        with committed_sessions() as db:
            assert _count(db) == 1
            assert len(db.scalars(select(activity_models.ActivitySource.id)).all()) == 1

    def test_a_lost_race_that_is_not_about_a_source_is_a_failure_not_a_duplicate(self, db):
        """An owner who does not exist fails the foreign key, which no stored source explains."""
        with pytest.raises(core_exceptions.ProcessingError):
            _store(db, make_parsed_activity(uuid.uuid4(), strava_activity_id=1))


class TestProviderPrecheck:
    def test_a_provider_activity_is_stored_for_its_owner_whichever_recording_of_it(self, db, owner, other):
        activity = make_activity(db, owner.id)
        make_source(db, activity, kind="garmin", provider_id=8, session_start=DEFAULT_START)

        assert activity_integration.is_provider_activity_stored(owner.id, "garmin", 8, db) is True
        assert activity_integration.is_provider_activity_stored(other.id, "garmin", 8, db) is False
        assert activity_integration.is_provider_activity_stored(owner.id, "strava", 8, db) is False
        assert activity_integration.is_provider_activity_stored(owner.id, "garmin", 9, db) is False

    def test_a_file_source_is_not_a_provider_activity(self, db, owner):
        activity = make_activity(db, owner.id)
        make_source(db, activity, kind="file", file_sha256=_SHA)

        assert activity_integration.is_provider_activity_stored(owner.id, "garmin", 1, db) is False


class TestProviderIdsReadFromSources:
    def test_an_activity_reads_the_ids_of_its_strava_and_garmin_sources(self, db, owner):
        activity = make_activity(db, owner.id)
        make_source(db, activity, kind="strava", provider_id=11, precedence=0)
        make_source(db, activity, kind="garmin", provider_id=22)

        read = activity_crud.get_activity_by_id(activity.id, db)

        assert (read.strava_activity_id, read.garminconnect_activity_id) == (11, 22)

    def test_an_activity_without_a_source_reads_no_id_even_when_the_legacy_column_holds_one(self, db, owner):
        created = activity_crud.create_activity(
            activity_contracts.ActivityCore.model_validate(
                make_parsed_activity(owner.id, strava_activity_id=5).activity.model_dump()
            ),
            db,
        )

        assert created.strava_activity_id is None
        assert activity_crud.get_activity_by_id(created.id, db).strava_activity_id is None

    def test_the_best_source_of_a_kind_names_the_id(self, db, owner):
        activity = make_activity(db, owner.id)
        make_source(db, activity, kind="garmin", provider_id=1, precedence=1)
        make_source(db, activity, kind="garmin", provider_id=2, precedence=2)

        assert activity_crud.get_activity_by_id(activity.id, db).garminconnect_activity_id == 2

    def test_a_stored_activity_returns_its_ids_straight_from_the_store(self, db, owner):
        stored = _store(db, make_parsed_activity(owner.id, strava_activity_id=5))

        assert stored.strava_activity_id == 5

    def test_a_viewer_never_reads_the_ids(self, db, owner):
        activity = make_activity(db, owner.id, visibility=_Visibility.PUBLIC)
        make_source(db, activity, kind="garmin", provider_id=22)

        read = activity_crud.get_activity_by_id_if_is_public(activity.id, db)

        assert read is not None
        assert read.garminconnect_activity_id is None

    def test_the_activity_deleted_takes_its_sources_with_it(self, db, owner):
        stored = _store(db, make_parsed_activity(owner.id, strava_activity_id=5))
        db.commit()
        etag = activity_crud.get_activity_by_id(stored.id, db).version

        activity_service.delete_activity(stored.id, owner.id, db, if_match=f'"{etag}"')

        assert db.scalars(select(activity_models.ActivitySource.id)).all() == []


class TestLiveStravaData:
    @staticmethod
    def _listed(db, owner_id) -> list[uuid.UUID]:
        return [
            activity.id
            for activity in activity_crud.get_user_activities_with_pagination(
                owner_id, db, user_is_owner=False, followee_ids=None
            )
        ]

    def test_an_activity_with_only_a_strava_source_is_the_owners_alone(self, db, owner):
        make_activity(db, owner.id, visibility=_Visibility.PUBLIC, strava_activity_id=42)

        assert self._listed(db, owner.id) == []

    def test_an_activity_a_device_file_also_recorded_is_listed_for_others(self, db, owner):
        merged = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, strava_activity_id=42)
        make_source(db, merged, kind="file", file_sha256=_SHA)

        assert self._listed(db, owner.id) == [merged.id]

    def test_an_activity_with_a_garmin_source_and_a_strava_one_is_listed_for_others(self, db, owner):
        merged = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, garminconnect_activity_id=8)
        make_source(db, merged, kind="strava", provider_id=42, precedence=0)

        assert self._listed(db, owner.id) == [merged.id]

    def test_a_file_source_alone_is_not_live_strava_data(self, db, owner):
        activity = make_activity(db, owner.id, visibility=_Visibility.PUBLIC)
        make_source(db, activity, kind="file", file_sha256=_SHA)

        assert self._listed(db, owner.id) == [activity.id]


class TestUnlinkingStrava:
    def test_activities_that_are_only_strava_are_deleted_and_merged_ones_lose_just_their_strava_source(
        self, db, owner, other, published
    ):
        only = make_activity_at(db, owner.id, DEFAULT_START, strava_activity_id=1)
        merged = make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=1), strava_activity_id=2)
        make_source(db, merged, kind="file", file_sha256=_SHA)
        device = make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=2), garminconnect_activity_id=3)
        theirs = make_activity_at(db, other.id, DEFAULT_START, strava_activity_id=1)

        deleted = activity_service.delete_all_strava_activities(owner.id, db, source="test", limit=10)
        db.commit()

        assert deleted == 1
        remaining = set(db.scalars(select(activity_models.Activity.id)).all())
        assert remaining == {merged.id, device.id, theirs.id}
        sources = {(row.activity_id, row.kind) for row in db.scalars(select(activity_models.ActivitySource)).all()}
        assert sources == {
            (merged.id, "file"),
            (device.id, "garmin"),
            (theirs.id, "strava"),
        }
        assert only.id not in remaining

    def test_the_merged_activities_sources_go_only_after_the_last_batch(self, db, owner):
        for index in range(3):
            make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=index), strava_activity_id=index + 1)
        merged = make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=9), strava_activity_id=99)
        make_source(db, merged, kind="file", file_sha256=_SHA)

        first = activity_service.delete_all_strava_activities(owner.id, db, source="test", limit=2)
        assert first == 2
        assert activity_source_crud.provider_source_exists(owner.id, "strava", 99, db) is True
        second = activity_service.delete_all_strava_activities(owner.id, db, source="test", limit=2)

        assert second == 1
        assert activity_source_crud.provider_source_exists(owner.id, "strava", 99, db) is False
        assert activity_crud.get_activity_by_id(merged.id, db) is not None


class TestRegroupingLegs:
    def _legacy_legs(self, db, owner):
        legs = []
        for index in range(2):
            start = DEFAULT_START + timedelta(minutes=20 * index)
            legs.append(_store(db, _upload(owner.id, start=start, end_time=start + timedelta(minutes=20))))
        return legs

    @staticmethod
    def _parent(owner_id, **source):
        return make_parsed_activity(
            owner_id,
            source=activity_contracts.ImportSource(kind="reprocess", **source),
            activity_type=activity_constants.ActivityType.MULTISPORT.stored,
        )

    def test_the_parent_takes_the_files_whole_source_and_the_legs_keep_theirs(self, db, owner):
        legs = self._legacy_legs(db, owner)

        parent = activity_service.regroup_legs(self._parent(owner.id, content_hash=_SHA), [leg.id for leg in legs], db)

        assert parent is not None
        sources = db.scalars(select(activity_models.ActivitySource)).all()
        whole = [source for source in sources if source.activity_id == parent.id]
        assert [(source.file_sha256, source.session_start) for source in whole] == [(_SHA, None)]
        assert {source.activity_id for source in sources if source.session_start is not None} == {
            leg.id for leg in legs
        }

    def test_a_file_whose_whole_source_is_stored_is_not_regrouped_again(self, db, owner):
        legs = self._legacy_legs(db, owner)
        taken = make_activity_at(db, owner.id, DEFAULT_START - timedelta(days=1))
        make_source(db, taken, kind="file", file_sha256=_SHA)

        parent = activity_service.regroup_legs(self._parent(owner.id, content_hash=_SHA), [leg.id for leg in legs], db)

        assert parent is None
        assert {activity_crud.get_activity_by_id(leg.id, db).parent_activity_id for leg in legs} == {None}

    def test_a_reimport_of_a_regrouped_file_returns_the_parent(self, db, owner):
        legs = self._legacy_legs(db, owner)
        parent = activity_service.regroup_legs(self._parent(owner.id, content_hash=_SHA), [leg.id for leg in legs], db)
        assert parent is not None
        again_legs = [_upload(owner.id, start=DEFAULT_START + timedelta(minutes=20 * n)) for n in range(2)]

        [again] = ingestion_service.store_parsed_group(
            _upload(owner.id, activity_type=activity_constants.ActivityType.MULTISPORT.stored), again_legs, db
        )

        assert again.id == parent.id
