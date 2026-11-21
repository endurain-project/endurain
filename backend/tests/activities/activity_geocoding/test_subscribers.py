"""Activities are located when they are created, through the bus and the durable handler."""

import uuid
from datetime import timedelta

import jasil.runtime as platform_runtime
import pydantic
import pytest
from jasil.events import new_event
from jasil.jobs import DeferJob
from jasil.jobs.registry import JobHandlerRegistry

import modules.activities.activity.events as activity_events
import modules.activities.activity.models as activity_models
import modules.activities.activity_geocoding.subscriber_registry as geocoding_subscriber_registry
import modules.activities.activity_geocoding.subscribers as geocoding_subscribers
import modules.activities.activity_streams.constants as stream_constants
from tests._factories.activities import make_activity, make_stream
from tests._factories.users import make_user

_MAP = stream_constants.STREAM_TYPE_MAP
_LISBON = [{"lat": 38.7, "lon": -9.1}, {"lat": 38.8, "lon": -9.2}]


@pytest.fixture
def events():
    return platform_runtime.get_active_platform().events


@pytest.fixture
def clock():
    return platform_runtime.get_active_platform().clock


@pytest.fixture
def created(db, geocoder):
    """An activity with a GPS stream, and its ``activity.created`` event."""
    user = make_user(db)
    activity = make_activity(db, user.id)
    make_stream(db, activity, _MAP, _LISBON)
    payload = activity_events.ActivityCreatedPayload(activity_id=activity.id, user_id=user.id)
    event = new_event(activity_events.ACTIVITY_CREATED, payload.model_dump(mode="json"), source="test")
    return activity, event


def _country(db, activity) -> str | None:
    db.expire_all()
    return db.get(activity_models.Activity, activity.id).country


class TestBus:
    def test_a_created_activity_is_located_when_the_event_is_published(self, db, events, created):
        activity, event = created
        geocoding_subscribers.register_bus_subscribers(events)

        events.publish(event)

        assert _country(db, activity) == "Portugal"

    def test_a_held_back_lookup_is_left_to_the_backfill_and_never_reaches_the_publisher(
        self, db, events, created, geocoding_server, clock
    ):
        activity, event = created
        geocoding_server.mode = "rate_limited"
        geocoding_subscribers.register_bus_subscribers(events)

        events.publish(event)

        assert _country(db, activity) is None

    def test_a_failure_in_the_handler_never_reaches_the_publisher(self, db, geocoder):
        event = new_event(activity_events.ACTIVITY_CREATED, {"activity_id": "not-a-uuid"}, source="test")

        geocoding_subscribers.on_activity_created_geocode(event)


class TestDurableHandler:
    def test_the_handler_locates_the_activity_named_in_the_event(self, db, created):
        activity, event = created

        geocoding_subscribers.geocode_activity_for_event(event)

        assert _country(db, activity) == "Portugal"

    def test_an_activity_without_a_route_is_left_alone_without_error(self, db, geocoder, geocoding_server):
        user = make_user(db)
        activity = make_activity(db, user.id)
        payload = activity_events.ActivityCreatedPayload(activity_id=activity.id, user_id=user.id)
        event = new_event(activity_events.ACTIVITY_CREATED, payload.model_dump(mode="json"), source="test")

        geocoding_subscribers.geocode_activity_for_event(event)

        assert (_country(db, activity), geocoding_server.requests) == (None, [])

    def test_a_held_back_lookup_defers_the_job_to_the_time_the_service_names(
        self, db, created, geocoding_server, clock
    ):
        _, event = created
        geocoding_server.mode = "rate_limited"

        with pytest.raises(DeferJob) as deferred:
            geocoding_subscribers.geocode_activity_for_event(event)

        assert deferred.value.retry_at == clock.now() + timedelta(seconds=120)

    def test_an_event_without_a_valid_payload_is_refused_so_the_runner_retries(self, geocoder):
        event = new_event(activity_events.ACTIVITY_CREATED, {"user_id": str(uuid.uuid4())}, source="test")

        with pytest.raises(pydantic.ValidationError):
            geocoding_subscribers.geocode_activity_for_event(event)


class TestRegistry:
    def test_the_package_registers_its_durable_handler_under_a_stable_id_and_wires_the_bus(self, db, events, created):
        activity, event = created
        registry = JobHandlerRegistry()

        geocoding_subscriber_registry.register_durable_handlers(registry)
        geocoding_subscriber_registry.register_bus_subscribers(events)
        events.publish(event)

        assert registry.subscribers_for(activity_events.ACTIVITY_CREATED) == ("activity_geocoding.reverse_geocode",)
        assert _country(db, activity) == "Portugal"
