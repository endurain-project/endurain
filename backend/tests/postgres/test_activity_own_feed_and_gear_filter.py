"""The own-activities feed cursor and the gear filter run as SQL, against real PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

import core.pagination as core_pagination
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.gears.gear.service as gear_service
from module_registry import configure_gear_contributors
from tests._helpers.db import ensure_user
from tests._helpers.gears import gear_create
from tests.postgres.test_transaction_ownership import _add_activity

_BASE = datetime(2026, 7, 1, 9, tzinfo=UTC)


@pytest.fixture
def factory(pg_factory):
    configure_gear_contributors()
    return pg_factory


def _add(factory, *, user_id=1, hours=0, visibility=2, gear_id=None, hide_start_time=False, created_at=None):
    """Add an activity starting ``hours`` after the base time and return its id."""
    activity_id = _add_activity(factory, user_id=user_id)
    values = {
        "start_time": _BASE + timedelta(hours=hours),
        "end_time": _BASE + timedelta(hours=hours, minutes=30),
        "visibility": visibility,
        "gear_id": gear_id,
        "hide_start_time": hide_start_time,
    }
    if created_at is not None:
        values["created_at"] = created_at
    with factory() as db:
        db.execute(update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(**values))
        db.commit()
    return activity_id


def _walk(factory, user_id, size):
    """Read the whole own feed in slices of ``size``, following each slice's last entry as the service does."""
    seen, after = [], None
    while True:
        with factory() as db:
            entries = activity_crud.get_own_feed_after(user_id, after, size + 1, db)
        page = entries[:size]
        seen.append([entry.activity.id for entry in page])
        if len(entries) <= size:
            return seen
        after = core_pagination.decode_cursor(
            core_pagination.encode_cursor(page[-1].cursor_sort_value, page[-1].cursor_id)
        )


class TestOwnFeed:
    def test_every_visibility_of_the_owner_is_listed_newest_first_and_nobody_elses(self, factory):
        private = _add(factory, hours=1, visibility=2)
        public = _add(factory, hours=3, visibility=0)
        followers = _add(factory, hours=2, visibility=1)
        _add(factory, user_id=2, hours=4)

        assert _walk(factory, 1, 10) == [[public, followers, private]]

    def test_the_cursor_walks_every_activity_once_across_slices(self, factory):
        ids = [_add(factory, hours=hours) for hours in range(5)]

        assert _walk(factory, 1, 2) == [[ids[4], ids[3]], [ids[2], ids[1]], [ids[0]]]

    def test_activities_sharing_a_start_time_are_neither_skipped_nor_repeated(self, factory):
        ids = [_add(factory, hours=0) for _ in range(4)]

        walked = [activity_id for page in _walk(factory, 1, 2) for activity_id in page]

        assert walked == sorted(ids, reverse=True)

    def test_a_hidden_start_time_sorts_by_when_the_activity_was_recorded(self, factory):
        late = _add(factory, hours=5)
        hidden = _add(factory, hours=0, hide_start_time=True, created_at=_BASE + timedelta(hours=9))

        assert _walk(factory, 1, 10) == [[hidden, late]]

    def test_the_owner_sees_the_hidden_start_time_of_their_own_activity(self, factory):
        hidden = _add(factory, hours=2, hide_start_time=True)

        with factory() as db:
            [entry] = activity_crud.get_own_feed_after(1, None, 10, db)

        assert entry.activity.id == hidden
        assert entry.activity.start_time == _BASE + timedelta(hours=2)


class TestGearFilter:
    def _gears(self, factory):
        ensure_user(factory, 1)
        with factory() as db:
            first = gear_service.create_gear(gear_create("First"), 1, db).id
            second = gear_service.create_gear(gear_create("Second"), 1, db).id
        return first, second

    def _listed(self, factory, gear_id):
        with factory() as db:
            items = activity_crud.get_user_activities_with_pagination(
                1, db, page_number=1, num_records=10, gear_id=gear_id, user_is_owner=True
            )
            total = activity_crud.count_user_activities(1, db, gear_id=gear_id, user_is_owner=True)
        return [item.id for item in items], total

    def test_only_the_activities_of_that_gear_are_listed_and_counted(self, factory):
        first, second = self._gears(factory)
        on_first = _add(factory, hours=1, gear_id=first)
        _add(factory, hours=2, gear_id=second)
        _add(factory, hours=3)

        assert self._listed(factory, first) == ([on_first], 1)

    def test_without_the_filter_every_activity_is_listed(self, factory):
        first, _ = self._gears(factory)
        _add(factory, hours=1, gear_id=first)
        _add(factory, hours=2)

        assert self._listed(factory, None)[1] == 2

    def test_another_users_activity_on_the_same_gear_is_not_listed(self, factory):
        first, _ = self._gears(factory)
        _add(factory, user_id=2, hours=1, gear_id=first)

        assert self._listed(factory, first) == ([], 0)
