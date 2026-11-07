"""The database sums an activity window for goal progress, against real PostgreSQL."""

from datetime import UTC, datetime

from sqlalchemy import update

import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
from tests.postgres.test_transaction_ownership import _add_activity

_WINDOW = (datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 31, tzinfo=UTC))


def _totals(factory, **kwargs):
    with factory() as db:
        return activity_crud.sum_user_activities_per_timeframe_and_activity_types(1, [1], *_WINDOW, db, **kwargs)


def test_nothing_matching_is_all_zero(pg_factory):
    _add_activity(pg_factory)

    with pg_factory() as db:
        totals = activity_crud.sum_user_activities_per_timeframe_and_activity_types(1, [2], *_WINDOW, db)

    assert (totals.count, totals.calories, totals.distance, totals.elapsed_time) == (0, 0, 0, 0)


def test_activities_are_summed_and_missing_values_count_as_zero(pg_factory):
    _add_activity(pg_factory)
    _add_activity(pg_factory)

    totals = _totals(pg_factory)

    assert totals.count == 2
    assert totals.distance == 2000
    assert totals.elapsed_time == 7200
    assert totals.calories == 0
    assert totals.elevation_gain == 0


def test_a_hidden_activity_is_left_out_only_when_asked(pg_factory):
    visible = _add_activity(pg_factory)
    hidden = _add_activity(pg_factory)
    # Activities that share a start time are flagged as duplicates on creation, so set each flag explicitly.
    with pg_factory() as db:
        for activity_id, is_hidden in ((visible, False), (hidden, True)):
            db.execute(
                update(activity_models.Activity)
                .where(activity_models.Activity.id == activity_id)
                .values(is_hidden=is_hidden)
            )
        db.commit()

    assert _totals(pg_factory).count == 2
    assert _totals(pg_factory, exclude_hidden=True).count == 1


def test_another_users_activities_are_not_counted(pg_factory):
    _add_activity(pg_factory, user_id=1)
    _add_activity(pg_factory, user_id=2)

    assert _totals(pg_factory).count == 1
