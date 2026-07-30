"""Tests for event_outbox CRUD — add, list unrelayed, mark relayed."""

from datetime import UTC, datetime, timedelta

import pytest

import core.jobs.outbox as jobs_outbox
import core.platform.events as platform_events
from core.jobs.models import EventOutbox
from tests._helpers.db import create_sqlite_session

_NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()  # StaticPool keeps one connection; dispose to avoid ResourceWarning


def _event(event_id="e1", metadata=None):
    return platform_events.Event(
        event_id=event_id,
        event_type="activity.created",
        source="api:store_activity",
        timestamp="2026-07-14T12:00:00+00:00",
        payload={"activity_id": 42},
        metadata=metadata if metadata is not None else {"activity_id": 42},
        retry_count=0,
    )


class TestAddToOutbox:
    def test_inserts_row(self, db):
        outbox_id = jobs_outbox.add_to_outbox(_event(), now=_NOW, db=db)
        row = db.get(EventOutbox, outbox_id)
        assert row is not None
        assert row.event_id == "e1"
        assert row.event_type == "activity.created"
        assert row.payload == {"activity_id": 42}
        assert row.event_metadata == {"activity_id": 42}
        assert row.relayed_at is None

    def test_empty_metadata_stored_as_null(self, db):
        outbox_id = jobs_outbox.add_to_outbox(_event(metadata={}), now=_NOW, db=db)
        assert db.get(EventOutbox, outbox_id).event_metadata is None


class TestListUnrelayed:
    def test_returns_only_unrelayed_oldest_first(self, db):
        jobs_outbox.add_to_outbox(_event("older"), now=_NOW - timedelta(minutes=2), db=db)
        jobs_outbox.add_to_outbox(_event("newer"), now=_NOW - timedelta(minutes=1), db=db)
        relayed_id = jobs_outbox.add_to_outbox(_event("done"), now=_NOW, db=db)
        jobs_outbox.mark_relayed(relayed_id, now=_NOW, db=db)
        rows = jobs_outbox.list_unrelayed(limit=10, db=db)
        assert [row.event_id for row in rows] == ["older", "newer"]

    def test_respects_limit(self, db):
        for index in range(3):
            jobs_outbox.add_to_outbox(_event(f"e{index}"), now=_NOW + timedelta(seconds=index), db=db)
        assert len(jobs_outbox.list_unrelayed(limit=2, db=db)) == 2


class TestMarkRelayed:
    def test_stamps_relayed_at(self, db):
        outbox_id = jobs_outbox.add_to_outbox(_event(), now=_NOW, db=db)
        jobs_outbox.mark_relayed(outbox_id, now=_NOW, db=db)
        assert db.get(EventOutbox, outbox_id).relayed_at is not None
        assert jobs_outbox.list_unrelayed(limit=10, db=db) == []
