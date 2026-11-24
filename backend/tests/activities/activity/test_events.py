"""The events an activity change publishes: type, payload, correlation metadata and payload version."""

from datetime import timedelta

import pytest

import modules.activities.activity.event_publishers as event_publishers
import modules.activities.activity.events as activity_events
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
from tests._factories.activities import DEFAULT_START, make_activity, make_activity_at, make_parsed_activity
from tests._factories.users import make_user


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


class TestSingleActivity:
    def test_created_carries_the_ids_the_source_and_the_payload_version(self, db, owner, published):
        stored = ingestion_service.store_parsed_activity(make_parsed_activity(owner.id), db)
        db.commit()

        [event] = published[activity_events.ACTIVITY_CREATED]
        assert event.payload["activity_id"] == str(stored.id)
        assert event.metadata["activity_id"] == str(stored.id)
        assert event.metadata["user_id"] == str(owner.id)
        assert event.schema_version == activity_events.ActivityCreatedPayload.SCHEMA_VERSION

    def test_updated_lists_the_changed_fields_sorted_whatever_order_the_edit_sent_them(self, db, owner, published):
        activity = make_activity(db, owner.id)

        activity_service.edit_activity(
            activity.id,
            owner.id,
            activity_schema.ActivityEdit(name="b", description="a", private_notes="c"),
            db,
            if_match="*",
        )

        [event] = published[activity_events.ACTIVITY_UPDATED]
        assert event.payload["changed_fields"] == ["description", "name", "private_notes"]
        assert event.source == "api:edit_activity"
        assert event.metadata["user_id"] == str(owner.id)
        assert event.schema_version == activity_events.ActivityUpdatedPayload.SCHEMA_VERSION

    def test_deleted_names_only_the_activity_and_correlates_the_owner_in_the_metadata(self, db, owner, published):
        activity = make_activity(db, owner.id)

        activity_service.delete_activity(activity.id, owner.id, db, if_match="*")

        [event] = published[activity_events.ACTIVITY_DELETED]
        assert event.payload["activity_id"] == str(activity.id)
        assert event.metadata["user_id"] == str(owner.id)
        assert event.source == "api:delete_activity"
        assert event.schema_version == activity_events.ActivityDeletedPayload.SCHEMA_VERSION

    def test_an_event_staged_in_a_session_that_is_rolled_back_is_never_delivered(self, db, owner, published):
        activity = make_activity(db, owner.id)
        event_publishers.publish_activity_deleted(activity.id, owner.id, db)

        db.rollback()

        assert published[activity_events.ACTIVITY_DELETED] == []


class TestBatches:
    def test_each_activity_of_a_bulk_update_gets_its_own_event_with_its_own_metadata(self, db, owner, published):
        ids = [make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=n)).id for n in range(2)]

        event_publishers.publish_activities_updated(
            ids, owner.id, db, changed_fields=["visibility", "gear_id"], source="job:test"
        )
        db.commit()

        events = published[activity_events.ACTIVITY_UPDATED]
        assert sorted(e.metadata["activity_id"] for e in events) == sorted(str(i) for i in ids)
        assert {tuple(e.payload["changed_fields"]) for e in events} == {("gear_id", "visibility")}
        assert {e.source for e in events} == {"job:test"}
        assert {e.schema_version for e in events} == {activity_events.ActivityUpdatedPayload.SCHEMA_VERSION}

    def test_each_activity_of_a_bulk_delete_gets_its_own_event(self, db, owner, published):
        ids = [make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=n)).id for n in range(2)]

        event_publishers.publish_activities_deleted(ids, owner.id, db, source="job:test")
        db.commit()

        events = published[activity_events.ACTIVITY_DELETED]
        assert sorted(e.payload["activity_id"] for e in events) == sorted(str(i) for i in ids)
        assert {e.schema_version for e in events} == {activity_events.ActivityDeletedPayload.SCHEMA_VERSION}

    def test_an_empty_batch_publishes_nothing(self, db, owner, published):
        event_publishers.publish_activities_updated([], owner.id, db, changed_fields=["gear_id"], source="job:test")
        event_publishers.publish_activities_deleted([], owner.id, db, source="job:test")
        db.commit()

        assert published[activity_events.ACTIVITY_UPDATED] == published[activity_events.ACTIVITY_DELETED] == []
