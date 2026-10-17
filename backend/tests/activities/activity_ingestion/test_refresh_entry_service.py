"""Tests for the provider-refresh entry point.

The refresh used to name Strava and Garmin directly, which is what made
activities and the provider modules mutually dependent. It now fans out over
whatever is registered, so these tests register fakes — no provider module is
imported here, which is the point.
"""

from datetime import UTC, datetime, timedelta

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.refresh_entry_service as refresh_entry_service


@pytest.fixture(autouse=True)
def _empty_registry():
    """Each test starts from an empty registry and leaves one behind."""
    provider_registry.clear()
    yield
    provider_registry.clear()


def _provider(name: str, produces=None, raises: Exception | None = None):
    """Register a fake provider and return the list of windows it was asked for."""
    seen: list[tuple] = []

    def _fetch(user_id, window_start, window_end):
        seen.append((user_id, window_start, window_end))
        if raises is not None:
            raise raises
        return produces

    provider_registry.register(provider_registry.ActivityProvider(name, _fetch, lambda after_id, limit: []))
    return seen


class TestSyncLinkedProviders:
    def test_combines_every_registered_provider(self):
        _provider("a", ["s1"])
        _provider("b", ["g1"])

        assert refresh_entry_service.sync_linked_providers(7) == ["s1", "g1"]

    def test_an_unlinked_provider_returns_nothing_rather_than_failing(self):
        """One unlinked integration must not fail the whole refresh."""
        _provider("a", None)
        _provider("b", ["g1"])

        assert refresh_entry_service.sync_linked_providers(7) == ["g1"]

    def test_a_failing_provider_does_not_take_the_others_down_but_fails_the_sync(self):
        """The others still run, and the sync raises so the job is retried."""
        _provider("a", raises=RuntimeError("provider down"))
        healthy = _provider("b", ["g1"])

        with pytest.raises(core_exceptions.ProcessingError):
            refresh_entry_service.sync_linked_providers(7)

        assert healthy[0] is not None

    def test_no_registered_providers_is_not_an_error(self):
        assert refresh_entry_service.sync_linked_providers(7) == []

    def test_asks_every_provider_for_the_same_default_window(self):
        first = _provider("a")
        second = _provider("b")

        refresh_entry_service.sync_linked_providers(7)

        assert first[0] == second[0]
        user_id, window_start, window_end = first[0]
        assert user_id == 7
        assert window_end - window_start == refresh_entry_service._REFRESH_WINDOW

    def test_an_explicit_window_is_passed_through_unchanged(self):
        seen = _provider("a")
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = start + timedelta(days=30)

        refresh_entry_service.sync_linked_providers(7, start, end)

        assert seen == [(7, start, end)]

    def test_a_named_provider_is_the_only_one_asked(self):
        wanted = _provider("a", ["s1"])
        other = _provider("b", ["g1"])

        assert refresh_entry_service.sync_linked_providers(7, provider="a") == ["s1"]
        assert len(wanted) == 1
        assert other == []

    def test_a_provider_missing_from_this_process_is_loud_not_an_empty_success(self):
        """A worker without a registration the API has would otherwise report a clean no-op."""
        _provider("a", ["s1"])

        with pytest.raises(core_exceptions.ProcessingError):
            refresh_entry_service.sync_linked_providers(7, provider="garminconnect")


class TestRegistry:
    def test_re_registering_a_name_replaces_rather_than_duplicates(self):
        """A second lifespan (or a test) must not double every fetch."""
        _provider("a", ["one"])
        _provider("a", ["two"])

        assert [p.name for p in provider_registry.registered()] == ["a"]

    def test_registration_order_is_preserved(self):
        _provider("a")
        _provider("b")

        assert [p.name for p in provider_registry.registered()] == ["a", "b"]

    def test_a_provider_is_found_by_name(self):
        _provider("a")

        assert provider_registry.get("a").name == "a"
        assert provider_registry.get("missing") is None
