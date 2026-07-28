"""Tests for version-aware event payload parsing.

The behaviour under test is what happens when the build that *wrote* an event is
not the build that *reads* it — the normal state of affairs during a rolling
deploy, and for any event sitting in the outbox or dead-lettered.
"""

from typing import ClassVar

import pytest
from pydantic import ConfigDict, ValidationError

import infra.event_versioning as event_versioning
from infra.events import INITIAL_SCHEMA_VERSION, Event, new_event


class _V1(event_versioning.VersionedPayload):
    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    activity_id: int


class _V2(event_versioning.VersionedPayload):
    """A payload that renamed a field — the case silent parsing gets wrong."""

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 2
    UPGRADERS: ClassVar[dict] = {
        1: lambda payload: {"activity_ref": payload["activity_id"]},
    }

    activity_ref: int


class _V3NoUpgrader(event_versioning.VersionedPayload):
    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 3
    UPGRADERS: ClassVar[dict] = {1: lambda payload: payload}

    activity_id: int


def _event(payload: dict, version: int = INITIAL_SCHEMA_VERSION) -> Event:
    return new_event("activity.created", payload, source="test", schema_version=version)


class TestEnvelope:
    def test_new_event_defaults_to_the_initial_version(self):
        assert new_event("activity.created", {}, source="test").schema_version == INITIAL_SCHEMA_VERSION

    def test_new_event_carries_an_explicit_version(self):
        assert new_event("activity.created", {}, source="test", schema_version=4).schema_version == 4


class TestMatchingVersion:
    def test_parses_when_versions_agree(self):
        payload = event_versioning.parse_payload(_V1, _event({"activity_id": 7}))
        assert payload.activity_id == 7

    def test_a_malformed_payload_still_raises(self):
        # The version check must not swallow ordinary validation failures — the
        # durable runner relies on them to retry and dead-letter.
        with pytest.raises(ValidationError):
            event_versioning.parse_payload(_V1, _event({}))


class TestOlderEventNewerConsumer:
    """The outbox-backlog case: this must actually work, not just not crash."""

    def test_upgrades_an_older_payload(self):
        payload = event_versioning.parse_payload(_V2, _event({"activity_id": 7}, version=1))
        assert payload.activity_ref == 7

    def test_without_the_upgrader_the_rename_would_be_silently_dropped(self):
        # Proves the upgrade is load-bearing: ``extra="ignore"`` means the old
        # field name is discarded, so the new required field would be missing.
        with pytest.raises(ValidationError):
            _V2.model_validate({"activity_id": 7})

    def test_a_missing_upgrade_step_is_refused(self):
        # 1 -> 3 needs a 2 -> 3 entry; shipping an evolution without its
        # migration must fail loudly rather than validate against the wrong shape.
        with pytest.raises(event_versioning.UnsupportedEventVersionError, match="no upgrader"):
            event_versioning.parse_payload(_V3NoUpgrader, _event({"activity_id": 7}, version=1))


class TestNewerEventOlderConsumer:
    """The rolling-deploy case: fail loudly so the runner retries."""

    def test_refuses_a_newer_payload(self):
        with pytest.raises(event_versioning.UnsupportedEventVersionError) as err:
            event_versioning.parse_payload(_V1, _event({"activity_id": 7}, version=2))
        assert "version 2" in str(err.value)

    def test_refusal_happens_before_validation(self):
        # Even a payload that would validate is refused: the local model cannot
        # know whether a field's *meaning* changed, which is the silent failure
        # this whole mechanism exists to prevent.
        with pytest.raises(event_versioning.UnsupportedEventVersionError):
            event_versioning.parse_payload(_V1, _event({"activity_id": 7, "extra": 1}, version=99))
