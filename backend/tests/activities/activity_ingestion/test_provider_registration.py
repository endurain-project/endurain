"""Both providers register themselves on the activities provider registry.

The registration is what replaced ingestion importing Strava and Garmin. If a
provider stops registering, refresh silently returns nothing for it — so the
wiring is asserted rather than assumed.
"""

import pytest

import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.garmin.provider_registry as garmin_provider_registry
import modules.strava.provider_registry as strava_provider_registry


@pytest.fixture(autouse=True)
def _empty_registry():
    provider_registry.clear()
    yield
    provider_registry.clear()


class TestProviderRegistration:
    def test_strava_registers_itself(self):
        strava_provider_registry.register_activity_provider()

        assert [p.name for p in provider_registry.registered()] == [strava_provider_registry.PROVIDER_NAME]

    def test_garmin_registers_itself(self):
        garmin_provider_registry.register_activity_provider()

        assert [p.name for p in provider_registry.registered()] == [garmin_provider_registry.PROVIDER_NAME]

    def test_the_two_providers_do_not_collide(self):
        strava_provider_registry.register_activity_provider()
        garmin_provider_registry.register_activity_provider()

        assert len(provider_registry.registered()) == 2

    def test_registering_twice_is_idempotent(self):
        """Both entrypoints register; a re-run must not double the fetch."""
        strava_provider_registry.register_activity_provider()
        strava_provider_registry.register_activity_provider()

        assert len(provider_registry.registered()) == 1
