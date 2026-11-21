"""What storing, editing, deleting and scheduling work on an activity does to its rows, on PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

import core.exceptions as core_exceptions
import core.sync as core_sync
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity.scheduled_jobs as activity_scheduled_jobs
import modules.activities.activity.schema as activity_schema
from tests._factories.activities import make_activity, make_activity_at
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
_FAR_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


def _stored(db, activity_id: uuid.UUID) -> activity_models.Activity:
    """The row as the database holds it now."""
    db.expire_all()
    row = db.get(activity_models.Activity, activity_id)
    assert row is not None
    return row


def _stamp(db, activity_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(
        update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(updated_at=stamp)
    )
    db.flush()


def _core(user_id: uuid.UUID, **overrides: object) -> activity_contracts.ActivityCore:
    """The ingestion contract as a parser hands it over: naive UTC strings and the enrichment flags set."""
    values: dict[str, object] = {
        "user_id": user_id,
        "name": "Garmin ride",
        "distance": 42000,
        "activity_type": 4,
        "start_time": "2026-07-28T09:00:00",
        "end_time": "2026-07-28T10:00:00",
        "timezone": "Europe/Lisbon",
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3540.0,
        "visibility": 2,
    }
    values.update({flag: False for flag in activity_schema.ActivityBase.model_fields if flag.startswith("hide_")})
    values.update(overrides)
    return activity_contracts.ActivityCore.model_validate(values)


class TestCreate:
    def test_the_stored_row_is_read_back_with_its_generated_id_and_normalised_times(self, db, owner):
        created = activity_crud.create_activity(_core(owner.id, garminconnect_activity_id=23749427619), db)

        stored = _stored(db, created.id)
        assert isinstance(created, activity_schema.ActivityRead)
        assert (stored.user_id, stored.name, stored.garminconnect_activity_id) == (owner.id, "Garmin ride", 23749427619)
        assert stored.start_time == datetime(2026, 7, 28, 9, tzinfo=UTC)
        assert created.created_at is not None
        assert created.id.version == 4

    def test_the_contract_the_caller_passed_is_left_untouched(self, db, owner):
        contract = _core(owner.id)

        activity_crud.create_activity(contract, db)

        assert not hasattr(contract, "id")
        assert contract.is_hidden is False

    def test_a_caller_supplied_creation_time_is_kept(self, db, owner):
        created = activity_crud.create_activity(_core(owner.id, created_at="2020-01-01T00:00:00"), db)

        assert _stored(db, created.id).created_at.year == 2020

    def test_the_markdown_fields_are_sanitised_on_the_way_in(self, db, owner):
        created = activity_crud.create_activity(
            _core(owner.id, description="<script>alert(1)</script>**bold**", private_notes="<img src=x onerror=1>ok"),
            db,
        )

        stored = _stored(db, created.id)
        assert "<script" not in stored.description and "**bold**" in stored.description
        assert "onerror" not in stored.private_notes and "ok" in stored.private_notes

    def test_a_missing_timer_time_falls_back_to_the_elapsed_time(self, db, owner):
        created = activity_crud.create_activity(_core(owner.id, total_timer_time=None, total_elapsed_time=120.0), db)

        assert _stored(db, created.id).total_timer_time == 120.0

    def test_the_contract_refuses_an_activity_without_an_owner_or_a_start(self, owner):
        with pytest.raises(ValueError):
            _core(None)
        with pytest.raises(ValueError):
            _core(owner.id, start_time=None)

    def test_the_second_activity_with_the_same_start_is_stored_hidden_and_so_is_the_third(self, db, owner):
        first = activity_crud.create_activity(_core(owner.id), db)
        second = activity_crud.create_activity(_core(owner.id, name="Same start"), db)
        third = activity_crud.create_activity(_core(owner.id, name="Again"), db)

        assert [first.is_hidden, second.is_hidden, third.is_hidden] == [False, True, True]

    def test_the_same_start_of_another_user_is_not_a_duplicate(self, db, owner, other):
        activity_crud.create_activity(_core(owner.id), db)

        assert activity_crud.create_activity(_core(other.id), db).is_hidden is False

    def test_a_dedup_key_is_kept_and_finds_the_activity_for_its_owner_only(self, db, owner, other):
        created = activity_crud.create_activity(_core(owner.id), db, dedup_key="strava:1")

        assert activity_crud.get_activity_by_dedup_key("strava:1", owner.id, db).id == created.id
        assert activity_crud.get_activity_by_dedup_key("strava:1", other.id, db) is None

    def test_the_activity_at_a_start_time_is_found_for_its_owner_only(self, db, owner, other):
        created = activity_crud.create_activity(_core(owner.id), db)
        start = datetime(2026, 7, 28, 9)

        assert activity_crud.get_activity_by_start_time(start, owner.id, db).id == created.id
        assert activity_crud.get_activity_by_start_time("2026-07-28T09:00:00", owner.id, db).id == created.id
        assert activity_crud.get_activity_by_start_time(start, other.id, db) is None


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, owner):
        created = make_activity(db, owner.id)

        edited = activity_crud.edit_activity(
            owner.id,
            created.id,
            activity_schema.ActivityEdit(name="Renamed", description="*notes*"),
            db,
            if_match=f'"{created.version}"',
        )

        stored = _stored(db, created.id)
        assert (stored.name, stored.description, stored.version) == ("Renamed", "*notes*", created.version + 1)
        assert edited.version == stored.version

    def test_fields_the_edit_does_not_name_keep_their_value(self, db, owner):
        created = make_activity(db, owner.id, description="before", calories=300)

        activity_crud.edit_activity(
            owner.id, created.id, activity_schema.ActivityEdit(name="New"), db, if_match=f'"{created.version}"'
        )

        stored = _stored(db, created.id)
        assert (stored.description, stored.calories, stored.name) == ("before", 300, "New")

    def test_the_edit_stores_the_visibility_as_its_integer(self, db, owner):
        created = make_activity(db, owner.id)

        activity_crud.edit_activity(
            owner.id,
            created.id,
            activity_schema.ActivityEdit(visibility=activity_constants.ActivityVisibility.PUBLIC),
            db,
            if_match="*",
        )

        assert _stored(db, created.id).visibility == 0

    def test_a_stale_version_is_refused_and_the_row_is_unchanged(self, db, owner):
        created = make_activity(db, owner.id, name="Original")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_crud.edit_activity(
                owner.id, created.id, activity_schema.ActivityEdit(name="Late"), db, if_match='"99"'
            )

        assert _stored(db, created.id).name == "Original"

    def test_a_wildcard_matches_any_version(self, db, owner):
        created = make_activity(db, owner.id)

        activity_crud.edit_activity(owner.id, created.id, activity_schema.ActivityEdit(name="Any"), db, if_match="*")

        assert _stored(db, created.id).name == "Any"

    def test_an_activity_of_another_user_is_not_found(self, db, owner, other):
        theirs = make_activity(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_crud.edit_activity(
                owner.id, theirs.id, activity_schema.ActivityEdit(name="Mine now"), db, if_match="*"
            )

    def test_a_background_thumbnail_write_does_not_change_the_version(self, db, owner):
        created = make_activity(db, owner.id)

        assert activity_crud.set_activity_thumbnail_key(created.id, f"{created.id}.webp", db) is True

        assert _stored(db, created.id).version == created.version

    def test_setting_a_thumbnail_key_on_an_unknown_activity_reports_it(self, db):
        assert activity_crud.set_activity_thumbnail_key(uuid.uuid4(), "x.webp", db) is False

    def test_clearing_a_thumbnail_key_leaves_a_key_stored_in_the_meantime(self, db, owner):
        created = make_activity(db, owner.id)
        activity_crud.set_activity_thumbnail_key(created.id, "new.webp", db)

        assert activity_crud.set_activity_thumbnail_key(created.id, None, db, expected_key="old.webp") is False
        assert activity_crud.set_activity_thumbnail_key(created.id, None, db, expected_key="new.webp") is True
        assert _stored(db, created.id).map_thumbnail_path is None


class TestDelete:
    def test_the_row_goes_and_leaves_a_tombstone_for_its_owner(self, db, owner):
        created = make_activity(db, owner.id)

        activity_crud.delete_activity(created.id, owner.id, db, if_match=f'"{created.version}"')

        assert db.get(activity_models.Activity, created.id) is None
        tombstones = db.scalars(select(activity_models.ActivityDeletion)).all()
        assert [(row.user_id, row.record_id) for row in tombstones] == [(owner.id, created.id)]

    def test_a_stale_version_is_refused_and_the_row_stays(self, db, owner):
        created = make_activity(db, owner.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_crud.delete_activity(created.id, owner.id, db, if_match='"99"')

        assert db.get(activity_models.Activity, created.id) is not None

    def test_another_users_activity_is_not_found_and_stays(self, db, owner, other):
        theirs = make_activity(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_crud.delete_activity(theirs.id, owner.id, db, if_match="*")

        assert db.get(activity_models.Activity, theirs.id) is not None

    def test_the_strava_batch_deletes_the_synced_activities_only_and_records_them(self, db, owner, other):
        synced = [
            make_activity_at(db, owner.id, _NOW + timedelta(days=n), strava_activity_id=100 + n).id for n in (1, 2)
        ]
        kept = make_activity_at(db, owner.id, _NOW + timedelta(days=3)).id
        theirs = make_activity_at(db, other.id, _NOW, strava_activity_id=1).id

        deleted = activity_crud.delete_all_strava_activities_for_user(owner.id, db, limit=10)

        assert sorted(deleted) == sorted(synced)
        assert {kept, theirs} <= set(db.scalars(select(activity_models.Activity.id)).all())
        assert sorted(db.scalars(select(activity_models.ActivityDeletion.record_id)).all()) == sorted(synced)

    def test_a_batch_deletes_no_more_than_its_limit_and_an_empty_one_deletes_nothing(self, db, owner):
        ids = [make_activity_at(db, owner.id, _NOW + timedelta(days=n)).id for n in range(3)]

        first = activity_crud.delete_activities_batch_for_user(owner.id, 2, db)
        second = activity_crud.delete_activities_batch_for_user(owner.id, 2, db)
        third = activity_crud.delete_activities_batch_for_user(owner.id, 2, db)

        assert (len(first), len(second), third) == (2, 1, [])
        assert sorted(first + second) == sorted(ids)
        assert activity_crud.delete_all_strava_activities_for_user(owner.id, db, limit=5) == []


class TestBulkWrites:
    def test_a_visibility_batch_changes_only_the_activities_that_differ_and_moves_their_version(self, db, owner, other):
        public = make_activity_at(db, owner.id, _NOW, visibility=activity_constants.ActivityVisibility.PUBLIC)
        private = make_activity_at(db, owner.id, _NOW + timedelta(days=1))
        theirs = make_activity_at(db, other.id, _NOW)

        changed = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 10, db)

        assert changed == [private.id]
        assert _stored(db, private.id).visibility == 0
        assert _stored(db, private.id).version == private.version + 1
        assert _stored(db, public.id).version == public.version
        assert _stored(db, theirs.id).visibility == 2
        assert activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 10, db) == []

    def test_a_visibility_batch_stops_at_its_limit(self, db, owner):
        for n in range(3):
            make_activity_at(db, owner.id, _NOW + timedelta(days=n))

        assert len(activity_crud.edit_user_activities_visibility_batch(owner.id, 1, 2, db)) == 2
        assert len(activity_crud.edit_user_activities_visibility_batch(owner.id, 1, 2, db)) == 1

    def test_gear_is_assigned_and_cleared_per_activity_and_other_users_activities_are_left_alone(
        self, db, owner, other
    ):
        gear = make_gear(db, owner.id)
        first = make_activity_at(db, owner.id, _NOW, gear_id=gear.id)
        second = make_activity_at(db, owner.id, _NOW + timedelta(days=1))
        theirs = make_activity_at(db, other.id, _NOW)

        updated = activity_crud.bulk_set_activities_gear_id(
            owner.id, {first.id: None, second.id: gear.id, theirs.id: gear.id}, db
        )

        assert sorted(updated) == sorted([first.id, second.id])
        assert (_stored(db, first.id).gear_id, _stored(db, second.id).gear_id) == (None, gear.id)
        assert _stored(db, theirs.id).gear_id is None
        assert _stored(db, second.id).version == second.version + 1
        assert activity_crud.bulk_set_activities_gear_id(owner.id, {}, db) == []

    def test_clearing_a_gear_unassigns_it_from_up_to_the_limit_of_the_owners_activities(self, db, owner, other):
        gear = make_gear(db, owner.id)
        ids = [make_activity_at(db, owner.id, _NOW + timedelta(days=n), gear_id=gear.id).id for n in range(3)]

        first = activity_crud.clear_gear_from_activities(gear.id, owner.id, 2, db)
        second = activity_crud.clear_gear_from_activities(gear.id, owner.id, 2, db)

        assert (len(first), len(second)) == (2, 1)
        assert sorted(first + second) == sorted(ids)
        assert activity_crud.clear_gear_from_activities(gear.id, owner.id, 2, db) == []
        assert activity_crud.clear_gear_from_activities(gear.id, other.id, 2, db) == []

    def test_the_garmin_gear_refs_page_by_id_and_skip_activities_without_one(self, db, owner):
        with_gear = sorted(
            (make_activity_at(db, owner.id, _NOW + timedelta(days=n), garminconnect_gear_id=f"g{n}") for n in range(2)),
            key=lambda activity: activity.id,
        )
        make_activity_at(db, owner.id, _NOW + timedelta(days=9))

        first_page = activity_crud.get_garminconnect_gear_activity_refs(owner.id, db, limit=1)
        rest = activity_crud.get_garminconnect_gear_activity_refs(owner.id, db, after_id=first_page[0].id)

        assert [ref.id for ref in first_page + rest] == [activity.id for activity in with_gear]
        assert first_page[0].garminconnect_gear_id in {"g0", "g1"}


class TestLocationLookupSchedule:
    def _ids(self, db, **kwargs):
        return [ref.id for ref in activity_crud.get_activities_missing_location(db, due_at=_NOW, **kwargs)]

    def test_an_unresolved_activity_that_was_never_deferred_is_a_candidate(self, db, owner):
        created = make_activity(db, owner.id)

        assert self._ids(db) == [created.id]

    def test_a_resolved_location_is_written_once_and_the_activity_stops_being_a_candidate(self, db, owner):
        created = make_activity(db, owner.id)

        assert activity_crud.update_activity_location(created.id, "Lisbon", None, "Portugal", db) is True
        assert activity_crud.update_activity_location(created.id, "Porto", None, "Portugal", db) is False

        assert (_stored(db, created.id).city, self._ids(db)) == ("Lisbon", [])

    def test_an_activity_that_already_has_a_place_is_not_overwritten(self, db, owner):
        created = make_activity(db, owner.id, town="Sintra")

        assert activity_crud.update_activity_location(created.id, "Lisbon", None, None, db) is False
        assert activity_crud.update_activity_location(uuid.uuid4(), "Lisbon", None, None, db) is False

    def test_a_deferred_activity_is_skipped_until_it_is_due(self, db, owner):
        later = make_activity_at(db, owner.id, _NOW)
        earlier = make_activity_at(db, owner.id, _NOW + timedelta(days=1))
        activity_crud.defer_location_lookups([later.id], _NOW + timedelta(hours=1), db)
        activity_crud.defer_location_lookups([earlier.id], _NOW - timedelta(hours=1), db)
        activity_crud.defer_location_lookups([], _NOW, db)

        assert self._ids(db) == [earlier.id]

    def test_the_candidates_page_after_the_given_id(self, db, owner):
        first, second = sorted(
            (make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(2)), key=lambda a: a.id
        )

        assert self._ids(db, after_id=first.id) == [second.id]
        assert self._ids(db, limit=1) == [first.id]


class TestThumbnailSchedule:
    def _ids(self, db, **kwargs):
        return [ref.id for ref in activity_crud.get_activities_without_thumbnail(db, due_at=_NOW, **kwargs)]

    def test_an_activity_with_no_thumbnail_is_a_candidate_until_it_gets_one(self, db, owner):
        created = make_activity(db, owner.id)
        assert self._ids(db) == [created.id]

        activity_crud.set_activity_thumbnail_key(created.id, f"{created.id}.webp", db)

        assert self._ids(db) == []
        assert [ref.id for ref in activity_crud.get_activities_with_thumbnail(db)] == [created.id]

    def test_the_candidates_page_after_the_given_id(self, db, owner):
        first, second = sorted(
            (make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(2)), key=lambda a: a.id
        )

        assert self._ids(db, after_id=first.id) == [second.id]
        assert self._ids(db, limit=1) == [first.id]

    def test_a_deferred_activity_is_skipped_until_it_is_due(self, db, owner):
        later = make_activity_at(db, owner.id, _NOW)
        earlier = make_activity_at(db, owner.id, _NOW + timedelta(days=1))
        activity_crud.defer_thumbnail_attempts([later.id], _NOW + timedelta(hours=1), db)
        activity_crud.defer_thumbnail_attempts([earlier.id], _NOW - timedelta(hours=1), db)
        activity_crud.defer_thumbnail_attempts([], _NOW, db)

        assert self._ids(db) == [earlier.id]

    def test_clearing_every_key_also_clears_the_deferral(self, db, owner):
        created = make_activity(db, owner.id)
        activity_crud.set_activity_thumbnail_key(created.id, "old.webp", db)
        activity_crud.defer_thumbnail_attempts([created.id], _NOW + timedelta(days=1), db)

        activity_crud.clear_all_activity_thumbnail_keys(db)

        assert self._ids(db) == [created.id]

    def test_the_keys_page_by_id_and_are_replaced_only_where_the_old_key_still_stands(self, db, owner):
        first, second = sorted(
            (make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(2)), key=lambda a: a.id
        )
        activity_crud.set_activity_thumbnail_key(first.id, "a.webp", db)
        activity_crud.set_activity_thumbnail_key(second.id, "b.webp", db)

        activity_crud.replace_activity_thumbnail_keys(
            [(first.id, "a.webp", "a2.webp"), (second.id, "stale", "b2.webp")], db
        )

        assert sorted(activity_crud.get_activity_thumbnail_keys(db)) == sorted(
            [(first.id, "a2.webp"), (second.id, "b.webp")]
        )
        assert [ref.id for ref in activity_crud.get_activities_with_thumbnail(db, after_id=first.id)] == [second.id]
        assert [ref.id for ref in activity_crud.get_activities_with_thumbnail(db, limit=1)] == [first.id]


class TestChangeStamps:
    def test_an_insert_is_stamped(self, db, owner):
        created = make_activity(db, owner.id)

        assert _stored(db, created.id).updated_at is not None

    def test_an_orm_edit_restamps_and_moves_the_version(self, db, owner):
        created = make_activity(db, owner.id)
        _stamp(db, created.id, datetime(2020, 1, 1))

        activity_crud.edit_activity(
            owner.id, created.id, activity_schema.ActivityEdit(name="Renamed"), db, if_match="*"
        )

        assert _stored(db, created.id).updated_at.year > 2020

    def test_a_core_update_and_a_touch_restamp_without_bumping_the_version(self, db, owner):
        created = make_activity(db, owner.id)
        _stamp(db, created.id, datetime(2020, 1, 1))
        activity_crud.set_activity_thumbnail_key(created.id, "1.webp", db)
        assert _stored(db, created.id).updated_at.year > 2020
        _stamp(db, created.id, datetime(2020, 1, 1))

        activity_crud.touch_activity(created.id, db)

        row = _stored(db, created.id)
        assert (row.updated_at.year > 2020, row.version) == (True, created.version)

    def test_changed_activities_come_in_stamp_then_id_order_and_belong_to_the_owner(self, db, owner, other):
        tied_a, tied_b, third = (make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(3))
        theirs = make_activity_at(db, other.id, _NOW)
        first, second = sorted((tied_a.id, tied_b.id))
        for activity_id, day in ((first, 1), (second, 1), (third.id, 2), (theirs.id, 1)):
            _stamp(db, activity_id, datetime(2026, 5, day))

        page = activity_crud.get_changed_activities(owner.id, None, _FAR_FUTURE, 2, db)
        rest = activity_crud.get_changed_activities(owner.id, (page[-1].updated_at, page[-1].id), _FAR_FUTURE, 10, db)

        assert [a.id for a in page] == [first, second]
        assert [a.id for a in rest] == [third.id]

    def test_the_after_position_is_exclusive_and_until_bounds_the_stamp(self, db, owner):
        first, second = (make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(2))
        _stamp(db, first.id, datetime(2026, 5, 1))
        _stamp(db, second.id, datetime(2026, 5, 3))

        bounded = activity_crud.get_changed_activities(owner.id, None, datetime(2026, 5, 3, tzinfo=UTC), 10, db)
        after = activity_crud.get_changed_activities(
            owner.id, (datetime(2026, 5, 1, tzinfo=UTC), first.id), _FAR_FUTURE, 10, db
        )

        assert [a.id for a in bounded] == [first.id]
        assert [a.id for a in after] == [second.id]

    def test_deletions_page_in_order_and_belong_to_the_owner(self, db, owner, other):
        ids = [make_activity_at(db, owner.id, _NOW + timedelta(days=n)) for n in range(3)]
        theirs = make_activity(db, other.id)
        for index, created in enumerate(ids):
            activity_crud.delete_activity(created.id, owner.id, db, if_match="*")
            db.execute(
                update(activity_models.ActivityDeletion)
                .where(activity_models.ActivityDeletion.record_id == created.id)
                .values(deleted_at=datetime(2026, 5, 1 + index))
            )
        activity_crud.delete_activity(theirs.id, other.id, db, if_match="*")

        page = activity_crud.get_activity_deletions(owner.id, None, _FAR_FUTURE, 2, db)
        rest = activity_crud.get_activity_deletions(owner.id, page[-1].position, _FAR_FUTURE, 10, db)

        assert [d.record_id for d in page] == [ids[0].id, ids[1].id]
        assert [d.record_id for d in rest] == [ids[2].id]
        assert {d.type for d in page + rest} == {activity_constants.SYNC_TYPE}
        assert page[0].position[0] == page[0].deleted_at

    def test_the_prune_job_removes_only_tombstones_past_the_retention(self, db, owner):
        old, recent = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(UTC)
        db.add_all(
            [
                activity_models.ActivityDeletion(
                    user_id=owner.id, record_id=old, deleted_at=now - core_sync.TOMBSTONE_RETENTION - timedelta(days=1)
                ),
                activity_models.ActivityDeletion(
                    user_id=owner.id, record_id=recent, deleted_at=now - timedelta(days=1)
                ),
            ]
        )
        db.flush()

        activity_scheduled_jobs.prune_activity_deletions()

        assert db.scalars(select(activity_models.ActivityDeletion.record_id)).all() == [recent]

    def test_the_prune_job_is_scheduled_daily(self):
        (job,) = activity_scheduled_jobs.recurring_jobs()

        assert job.func is activity_scheduled_jobs.prune_activity_deletions
