"""The activities surface other modules use (Strava, Garmin, gears, goals, account deletion, profile export)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.gears.contracts as gears_contracts
from tests._factories.activities import make_activity, make_activity_at, make_activity_media, make_parsed_activity
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
_DAY = datetime(2026, 7, 15, 9, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


class TestProviderLookups:
    def test_an_import_is_found_by_the_providers_id_for_its_owner_only(self, db, owner, other):
        make_activity(db, owner.id, strava_activity_id=7, garminconnect_activity_id=8)

        assert activity_integration.is_provider_activity_stored(owner.id, "strava", 7, db) is True
        assert activity_integration.is_provider_activity_stored(owner.id, "garmin", 8, db) is True
        assert activity_integration.is_provider_activity_stored(other.id, "strava", 7, db) is False
        assert activity_integration.is_provider_activity_stored(other.id, "garmin", 8, db) is False
        assert activity_integration.is_provider_activity_stored(owner.id, "garmin", 7, db) is False

    def test_the_garmin_gear_refs_page_in_id_order(self, db, owner):
        ids = sorted(
            make_activity_at(db, owner.id, _DAY + timedelta(days=n), garminconnect_gear_id=f"g{n}").id for n in range(3)
        )

        first = activity_integration.list_garminconnect_gear_activity_refs(owner.id, db, limit=2)
        rest = activity_integration.list_garminconnect_gear_activity_refs(owner.id, db, after_id=first[-1].id)

        assert [ref.id for ref in first + rest] == ids

    def test_which_of_some_activity_ids_still_exist(self, db, owner):
        mine = make_activity(db, owner.id)

        assert activity_integration.filter_existing_activity_ids([mine.id], db) == {mine.id}

    def test_ownership_is_asked_through_the_surface_too(self, db, owner, other):
        mine = make_activity(db, owner.id)

        assert activity_integration.owns_activity(mine.id, owner.id, db) is True
        assert activity_integration.owns_activity(mine.id, other.id, db) is False


class TestGearWrites:
    def test_a_bulk_assignment_changes_the_gear_and_publishes_from_its_own_source(self, db, owner, published):
        gear = make_gear(db, owner.id)
        activity = make_activity(db, owner.id)

        assert activity_integration.bulk_set_activities_gear(owner.id, {activity.id: gear.id}, db) == 1
        db.commit()

        assert db.get(activity_models.Activity, activity.id).gear_id == gear.id
        [event] = published[activity_events.ACTIVITY_UPDATED]
        assert event.source == "api:bulk_set_activities_gear"

    def test_clearing_a_gear_unassigns_it_and_publishes_from_the_gear_deletion_source(self, db, owner, published):
        gear = make_gear(db, owner.id)
        activity = make_activity(db, owner.id, gear_id=gear.id)

        assert activity_integration.clear_activities_gear(gear.id, owner.id, 10, db) == 1
        db.commit()

        assert db.get(activity_models.Activity, activity.id).gear_id is None
        assert len(published[activity_events.ACTIVITY_UPDATED]) == 1

    def test_the_usage_of_a_gear_is_summed_overall_and_per_window(self, db, owner):
        gear = make_gear(db, owner.id)
        make_activity_at(db, owner.id, _DAY, gear_id=gear.id, distance=1000, total_timer_time=60.0)
        make_activity_at(db, owner.id, _DAY + timedelta(days=30), gear_id=gear.id, distance=2000, total_timer_time=30.0)
        window = gears_contracts.UsageWindow(key=gear.id, start_date=_DAY.date() + timedelta(days=20))

        total = activity_integration.get_gear_usage_totals([gear.id], owner.id, db)[gear.id]
        by_window = activity_integration.get_gear_usage_totals_by_window(gear.id, owner.id, [window], db)

        assert (total.distance, total.time) == (3000.0, 90.0)
        assert by_window[gear.id].distance == 2000.0


class TestDeletes:
    def test_a_batch_delete_removes_up_to_the_limit_and_publishes_deleted_for_each(self, db, owner, published):
        for n in range(3):
            make_activity_at(db, owner.id, _DAY + timedelta(days=n))

        assert activity_integration.delete_activities_batch_for_user(owner.id, 2, db) == 2
        db.commit()

        assert len(published[activity_events.ACTIVITY_DELETED]) == 2
        assert {e.source for e in published[activity_events.ACTIVITY_DELETED]} == {"api:delete_user"}

    def test_the_strava_delete_removes_the_synced_activities_only(self, db, owner, published):
        synced = make_activity_at(db, owner.id, _DAY, strava_activity_id=1)
        kept = make_activity_at(db, owner.id, _DAY + timedelta(days=1))

        assert activity_integration.delete_all_strava_activities(owner.id, db, limit=10) == 1
        db.commit()

        remaining = set(db.scalars(select(activity_models.Activity.id)))
        assert (synced.id in remaining, kept.id in remaining) == (False, True)
        assert len(published[activity_events.ACTIVITY_DELETED]) == 1


class TestReadsForOtherModules:
    def test_the_owners_pages_come_newest_first_for_the_profile_export(self, db, owner, other):
        old = make_activity_at(db, owner.id, _DAY, visibility=activity_constants.ActivityVisibility.PRIVATE)
        new = make_activity_at(db, owner.id, _DAY + timedelta(days=1))
        make_activity_at(db, other.id, _DAY)

        page = activity_integration.list_user_activities_page(owner.id, db, page_number=1, num_records=10)

        assert [a.id for a in page] == [new.id, old.id]
        assert activity_integration.list_user_activities_page(owner.id, db, page_number=2, num_records=10) == []

    def test_a_goal_window_leaves_out_hidden_duplicates_unless_asked(self, db, owner):
        make_activity_at(db, owner.id, _DAY)
        make_activity_at(db, owner.id, _DAY + timedelta(days=1), is_hidden=True)
        window = (_DAY - timedelta(days=1), _DAY + timedelta(days=5))

        by_default = activity_integration.total_user_activities_in_timeframe_by_types(owner.id, [1], *window, db)
        with_hidden = activity_integration.total_user_activities_in_timeframe_by_types(
            owner.id, [1], *window, db, exclude_hidden=False
        )

        assert (by_default.count, with_hidden.count) == (1, 2)

    def test_the_profile_summary_is_the_services(self, db, owner):
        make_activity_at(db, owner.id, _DAY)

        summary = activity_integration.get_user_profile_summary(owner.id, owner.id, db, anchor=_DAY.date())

        assert (summary.month_activity_count, summary.month_stats.run.distance) == (1, 10000.0)

    def test_a_restored_activity_is_stored_without_publishing_created(self, db, owner, published):
        core = make_parsed_activity(owner.id).activity

        restored = activity_integration.restore_activity(core, db)
        db.commit()

        assert db.get(activity_models.Activity, restored.id) is not None
        assert published[activity_events.ACTIVITY_CREATED] == []

    def test_a_restored_activity_keeps_analysis_version_zero_so_it_is_reprocessed(self, db, owner):
        core = make_parsed_activity(owner.id).activity

        restored = activity_integration.restore_activity(core, db)

        assert db.get(activity_models.Activity, restored.id).analysis_version == 0

    def test_the_readable_activity_media_and_public_reads_go_through_the_service(self, db, owner, other):
        mine = make_activity(db, owner.id, visibility=activity_constants.ActivityVisibility.PUBLIC)
        make_activity_media(db, mine, "a.jpg")

        read = activity_integration.get_readable_activity(mine.id, other.id, db)

        assert activity_integration.with_media(read, other.id, db).media == []
        assert len(activity_integration.with_media(read, owner.id, db).media) == 1
        assert activity_integration.resolve_readable_parent(mine.id, other.id, db).id == mine.id
        assert activity_integration.resolve_public_parent(mine.id, db) is None


class TestDerivedArtifactWritesStageOnly:
    def test_a_thumbnail_key_is_recorded_listed_and_cleared_without_ending_the_callers_transaction(self, db, owner):
        activity = make_activity(db, owner.id, start_latitude=38.7, start_longitude=-9.1)

        assert activity_integration.set_thumbnail_key(activity.id, "k.webp", db) is True
        assert [ref.id for ref in activity_integration.list_activities_with_thumbnail(db)] == [activity.id]
        activity_integration.clear_all_thumbnail_keys(db)

        assert [ref.id for ref in activity_integration.list_activities_without_thumbnail(db, due_at=_NOW)] == [
            activity.id
        ]

    def test_a_deferred_thumbnail_attempt_waits_for_its_time(self, db, owner):
        activity = make_activity(db, owner.id, start_latitude=38.7, start_longitude=-9.1)
        activity_integration.defer_thumbnail_attempts([activity.id], _NOW + timedelta(hours=1), db)

        assert activity_integration.list_activities_without_thumbnail(db, due_at=_NOW) == []
        assert len(activity_integration.list_activities_without_thumbnail(db, due_at=_NOW + timedelta(hours=2))) == 1

    def test_a_location_is_written_only_while_none_is_set_and_a_deferred_lookup_waits(self, db, owner):
        activity = make_activity(db, owner.id, start_latitude=38.7, start_longitude=-9.1)
        assert [ref.id for ref in activity_integration.list_activities_missing_location(db, due_at=_NOW)] == [
            activity.id
        ]
        activity_integration.defer_location_lookups([activity.id], _NOW + timedelta(hours=1), db)
        assert activity_integration.list_activities_missing_location(db, due_at=_NOW) == []

        assert activity_integration.set_activity_location(activity.id, "Lisbon", None, "Portugal", db) is True
        assert activity_integration.set_activity_location(activity.id, "Porto", None, "Portugal", db) is False

    def test_the_start_point_is_read_and_an_activity_without_one_is_not_a_location_candidate(self, db, owner):
        placed = make_activity(db, owner.id, start_latitude=38.7, start_longitude=-9.1)
        bare = make_activity(db, owner.id)

        assert activity_integration.get_activity_start_point(placed.id, db) == (38.7, -9.1)
        assert activity_integration.get_activity_start_point(bare.id, db) is None
        assert activity_integration.get_activity_start_point(uuid.uuid4(), db) is None
        [ref] = activity_integration.list_activities_missing_location(db, due_at=_NOW)
        assert (ref.id, ref.latitude, ref.longitude) == (placed.id, 38.7, -9.1)

    def test_touching_an_activity_restamps_it_without_a_new_version(self, db, owner):
        activity = make_activity(db, owner.id)

        activity_integration.touch_activity(activity.id, db)

        assert db.get(activity_models.Activity, activity.id).version == activity.version

    def test_the_change_surface_lists_changed_activities_and_deletions_of_the_owner(self, db, owner):
        mine = make_activity(db, owner.id)
        gone = make_activity_at(db, owner.id, _DAY + timedelta(days=1))
        activity_crud.delete_activity(gone.id, owner.id, db, if_match="*")
        until = datetime.now(UTC) + timedelta(days=1)

        changed = activity_integration.list_changed_activities(owner.id, None, until, 10, db)
        deleted = activity_integration.list_activity_deletions(owner.id, None, until, 10, db)

        assert [a.id for a in changed] == [mine.id]
        assert [d.record_id for d in deleted] == [gone.id]
