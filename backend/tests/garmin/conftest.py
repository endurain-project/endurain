"""Shared fixtures for the Garmin Connect tests."""

import threading

import pytest

import modules.garmin.service as garmin_service


@pytest.fixture(autouse=True)
def fresh_link_slots(monkeypatch):
    """Give every test its own link capacity, so a mocked executor never leaks slots."""
    monkeypatch.setattr(garmin_service, "_link_slots", threading.BoundedSemaphore(garmin_service.MAX_CONCURRENT_LINKS))
