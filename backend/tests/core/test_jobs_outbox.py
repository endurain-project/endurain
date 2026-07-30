"""Tests for event_outbox CRUD — add, list unrelayed, mark relayed."""

from datetime import UTC, datetime, timedelta

import pytest

import infra.events as platform_events
import infra.jobs.outbox as jobs_outbox
from infra.jobs.models import EventOutbox
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

    def test_commit_false_flushes_without_committing(self, db):
        # commit=False stages the row in the caller's open transaction (visible via
        # the session) but does not commit — a rollback discards it, which is what
        # makes the ingestion outbox write atomic with the domain change.
        outbox_id = jobs_outbox.add_to_outbox(_event("staged"), now=_NOW, db=db, commit=False)
        assert db.get(EventOutbox, outbox_id) is not None  # flushed, visible in-session
        db.rollback()
        assert db.get(EventOutbox, outbox_id) is None  # never committed


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


class TestDeleteRelayedBefore:
    @staticmethod
    def _add(db, outbox_id, *, relayed_at, created_at=_NOW):
        db.add(
            EventOutbox(
                id=outbox_id,
                event_id=f"ev-{outbox_id}",
                event_type="activity.created",
                source="api:test",
                timestamp="2026-07-14T12:00:00+00:00",
                payload={},
                created_at=created_at,
                relayed_at=relayed_at,
            )
        )
        db.commit()

    def test_deletes_old_relayed_only(self, db):
        cutoff = _NOW - timedelta(days=90)
        self._add(db, "old-relayed", relayed_at=_NOW - timedelta(days=100))
        self._add(db, "recent-relayed", relayed_at=_NOW)

        assert jobs_outbox.delete_relayed_before(cutoff, db=db) == 1
        assert db.get(EventOutbox, "old-relayed") is None
        assert db.get(EventOutbox, "recent-relayed") is not None

    def test_never_deletes_unrelayed(self, db):
        cutoff = _NOW - timedelta(days=90)
        # An unrelayed row is pending work — never pruned, however old.
        self._add(db, "unrelayed", relayed_at=None, created_at=_NOW - timedelta(days=100))

        assert jobs_outbox.delete_relayed_before(cutoff, db=db) == 0
        assert db.get(EventOutbox, "unrelayed") is not None
