"""Tests for the activity-media integration surface."""

import pytest
from sqlalchemy import event
from tests._helpers.db import create_sqlite_session

import modules.activities.activity_media.integration_service as media_integration
import modules.activities.activity_media.models as media_models


@pytest.fixture
def session():
    db = create_sqlite_session()
    yield db
    db.close()


def _add_media(db, activity_id: int, count: int) -> None:
    for n in range(count):
        db.add(media_models.ActivityMedia(activity_id=activity_id, media_path=f"{activity_id}_{n}.jpg", media_type=1))
    db.flush()


class TestMediaForActivities:
    def test_groups_signed_media_by_activity_oldest_first(self, session):
        _add_media(session, 1, 2)
        _add_media(session, 2, 1)

        result = media_integration.media_for_activities([1, 2, 3], session)

        assert sorted(result) == [1, 2]
        assert [m.activity_id for m in result[1]] == [1, 1]
        assert result[1][0].id < result[1][1].id
        assert all(m.url and "1_0.jpg" not in m.url for m in result[1])
        assert "t=" in result[2][0].url

    def test_no_ids_runs_no_query(self, session):
        assert media_integration.media_for_activities([], session) == {}

    def test_query_count_does_not_grow_with_the_page(self, session):
        for activity_id in range(1, 31):
            _add_media(session, activity_id, 2)
        statements: list[str] = []
        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))

        media_integration.media_for_activities([1], session)
        one = len(statements)
        statements.clear()
        media_integration.media_for_activities(list(range(1, 31)), session)

        assert len(statements) == one == 1
