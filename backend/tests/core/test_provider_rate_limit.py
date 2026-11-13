"""Tests for core.provider_rate_limit: the shared record of a provider's rate limit."""

from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers
import pytest
from jasil.backends.state_memory import MemoryState

import core.provider_rate_limit as core_provider_rate_limit


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def store(state):
    return core_provider_rate_limit.ProviderRateLimitStore(state, "acme")


def _down(*_args, **_kwargs):
    raise platform_providers.StateBackendUnavailableError("redis down")


def test_nothing_is_limited_to_begin_with(store):
    assert store.expiry("user-1") is None


def test_a_marked_subject_reads_back_its_expiry(store):
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    store.mark("user-1", expires_at)

    assert store.expiry("user-1") == expires_at


def test_the_flag_is_visible_to_another_store_over_the_same_state(state, store):
    store.mark("user-1", datetime.now(UTC) + timedelta(minutes=10))

    assert core_provider_rate_limit.ProviderRateLimitStore(state, "acme").expiry("user-1") is not None


def test_subjects_and_providers_do_not_reach_each_other(state, store):
    store.mark("user-1", datetime.now(UTC) + timedelta(minutes=10))

    assert store.expiry("user-2") is None
    assert core_provider_rate_limit.ProviderRateLimitStore(state, "other").expiry("user-1") is None


def test_keys_are_namespaced_by_provider_and_subject(state, store):
    store.mark("short:app-a", datetime.now(UTC) + timedelta(minutes=10))

    assert state.get("acme:rate_limited:short:app-a") is not None


def test_the_flag_expires_on_its_own(state, store):
    store.mark("user-1", datetime.now(UTC) + timedelta(minutes=10))
    state.delete("acme:rate_limited:user-1")

    assert store.expiry("user-1") is None


def test_a_flag_without_a_readable_expiry_still_defers(state, store):
    state.set("acme:rate_limited:user-1", b"1", ttl_seconds=60)

    until = store.expiry("user-1")

    assert until is not None
    assert until > datetime.now(UTC) + timedelta(minutes=10)


def test_an_unreachable_state_fails_open(state, store, monkeypatch):
    monkeypatch.setattr(state, "get", _down)
    monkeypatch.setattr(state, "set", _down)

    assert store.expiry("user-1") is None
    store.mark("user-1", datetime.now(UTC) + timedelta(minutes=10))  # must not raise
