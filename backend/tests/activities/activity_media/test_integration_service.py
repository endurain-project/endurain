"""Tests for the activity-media integration surface."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from tests._helpers.db import create_sqlite_session

import modules.activities.activity_media.integration_service as media_integration
import modules.activities.activity_media.models as media_models

ACT1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
ACT2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
ACT3 = uuid.UUID("00000000-0000-4000-8000-000000000003")
NEW_ACT = uuid.UUID("00000000-0000-4000-8000-000000000007")
ORIGINAL_ACT = uuid.UUID("00000000-0000-4000-8000-000000000001")
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def session():
    db = create_sqlite_session()
    yield db
    db.close()


def _add_media(db, activity_id: uuid.UUID, count: int, *, newest_first: bool = False) -> None:
    """Add ``count`` photos; ``created_at`` rises with ``n``, or falls when ``newest_first``."""
    for n in range(count):
        offset = timedelta(seconds=-n if newest_first else n)
        db.add(
            media_models.ActivityMedia(
                activity_id=activity_id,
                media_path=f"{activity_id}_{n}.jpg",
                media_type=1,
                created_at=_EPOCH + offset,
            )
        )
    db.flush()


class TestMediaForActivities:
    def test_groups_signed_media_by_activity_oldest_first(self, session):
        _add_media(session, ACT1, 2, newest_first=True)
        _add_media(session, ACT2, 1)

        result = media_integration.media_for_activities([ACT1, ACT2, ACT3], session)

        assert sorted(result) == sorted([ACT1, ACT2])
        assert [m.activity_id for m in result[ACT1]] == [ACT1, ACT1]
        by_path = {row.media_path: row.id for row in session.query(media_models.ActivityMedia)}
        # Photo 1 was created first, so it comes first whatever the random ids sort as.
        assert [m.id for m in result[ACT1]] == [by_path[f"{ACT1}_1.jpg"], by_path[f"{ACT1}_0.jpg"]]
        assert all(m.url and "_0.jpg" not in m.url for m in result[ACT1])
        assert "t=" in result[ACT2][0].url

    def test_no_ids_runs_no_query(self, session):
        assert media_integration.media_for_activities([], session) == {}

    def test_query_count_does_not_grow_with_the_page(self, session):
        activity_ids = [uuid.uuid4() for _ in range(30)]
        for activity_id in activity_ids:
            _add_media(session, activity_id, 2)
        statements: list[str] = []
        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))

        media_integration.media_for_activities(activity_ids[:1], session)
        one = len(statements)
        statements.clear()
        media_integration.media_for_activities(activity_ids, session)

        assert len(statements) == one == 1


_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _restore(session, records):
    activity = SimpleNamespace(id=NEW_ACT)
    count = media_integration._restore_profile_records(records, ORIGINAL_ACT, activity, session)
    session.flush()
    rows = session.query(media_models.ActivityMedia).order_by(media_models.ActivityMedia.media_path).all()
    return count, [(r.media_path, r.content_hash) for r in rows]


def _record(name, **extra):
    return {"activity_id": str(ORIGINAL_ACT), "media_path": f"{ORIGINAL_ACT}_{name}.jpg", "media_type": 1, **extra}


class TestRestoreProfileRecords:
    def test_restores_the_content_hash(self, session):
        count, rows = _restore(session, [_record("a", content_hash=_HASH_A)])

        assert count == 1
        assert rows[0][1] == _HASH_A

    def test_rows_without_a_hash_still_restore(self, session):
        count, rows = _restore(session, [_record("a"), _record("b", content_hash=None)])

        assert count == 2
        assert [h for _, h in rows] == [None, None]

    @pytest.mark.parametrize("bad", ["not-a-hash", "A" * 64, "a" * 63, "a" * 64 + "\n", 12, ["a" * 64], ""])
    def test_malformed_hash_restores_the_row_without_one(self, session, bad):
        count, rows = _restore(session, [_record("a", content_hash=bad)])

        assert count == 1
        assert rows[0][1] is None

    def test_duplicate_hash_in_one_activity_restores_once(self, session):
        count, rows = _restore(
            session,
            [
                _record("a", content_hash=_HASH_A),
                _record("b", content_hash=_HASH_A),
                _record("c", content_hash=_HASH_B),
            ],
        )

        assert count == 2
        assert [h for _, h in rows] == [_HASH_A, _HASH_B]
        assert rows[0][0].endswith("_a.jpg")
