"""Fixtures for the retained-source-file tests: the platform's real storage, and a way to break it."""

import dataclasses
from collections.abc import Callable

import jasil.runtime as jasil_runtime
import pytest

from tests._factories.profile import FaultyStorage


@pytest.fixture
def platform(_publish_local_platform):
    """The test platform: real local storage under the test's directory and a real in-process event bus."""
    return _publish_local_platform


@pytest.fixture
def storage(platform):
    """The platform's storage, where retained source files live."""
    return platform.storage


@pytest.fixture
def break_storage(platform) -> Callable[..., FaultyStorage]:
    """Return a function that makes the platform's storage fail the way an unreachable backend does."""

    def apply(**faults: BaseException) -> FaultyStorage:
        faulty = FaultyStorage(platform.storage, faults=faults)
        jasil_runtime.set_active_platform(dataclasses.replace(platform, storage=faulty))
        return faulty

    return apply
