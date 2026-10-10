"""Tests for the provider-refresh entry point.

The refresh used to name Strava and Garmin directly, which is what made
activities and the provider modules mutually dependent. It now fans out over
whatever is registered, so these tests register fakes — no provider module is
imported here, which is the point.
"""

from unittest.mock import MagicMock

import pytest

import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.refresh_entry as refresh_entry


@pytest.fixture(autouse=True)
def _empty_registry():
    """Each test starts from an empty registry and leaves one behind."""
    provider_registry.clear()
    yield
    provider_registry.clear()


def _provider(name: str, produces=None, raises: Exception | None = None):
    """Register a fake provider and return the list of windows it was asked for."""
    seen: list[tuple] = []

    async def _fetch(user_id, window_start, window_end, db):
        seen.append((user_id, window_start, window_end, db))
        if raises is not None:
            raise raises
        return produces

    provider_registry.register(provider_registry.ActivityProvider(name, _fetch))
    return seen


class TestSyncLinkedProviders:
    @pytest.mark.asyncio
    async def test_combines_every_registered_provider(self):
        _provider("a", ["s1"])
        _provider("b", ["g1"])

        assert await refresh_entry.sync_linked_providers(7, MagicMock()) == ["s1", "g1"]

    @pytest.mark.asyncio
    async def test_an_unlinked_provider_returns_nothing_rather_than_failing(self):
        """One unlinked integration must not fail the whole refresh."""
        _provider("a", None)
        _provider("b", ["g1"])

        assert await refresh_entry.sync_linked_providers(7, MagicMock()) == ["g1"]

    @pytest.mark.asyncio
    async def test_a_failing_provider_does_not_take_the_others_down(self):
        _provider("a", raises=RuntimeError("provider down"))
        _provider("b", ["g1"])

        assert await refresh_entry.sync_linked_providers(7, MagicMock()) == ["g1"]

    @pytest.mark.asyncio
    async def test_no_registered_providers_is_not_an_error(self):
        assert await refresh_entry.sync_linked_providers(7, MagicMock()) == []

    @pytest.mark.asyncio
    async def test_asks_every_provider_for_the_same_window(self):
        first = _provider("a")
        second = _provider("b")
        db = MagicMock()

        await refresh_entry.sync_linked_providers(7, db)

        assert first[0] == second[0]
        user_id, window_start, window_end, passed_db = first[0]
        assert (user_id, passed_db) == (7, db)
        assert window_end - window_start == refresh_entry._REFRESH_WINDOW


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
