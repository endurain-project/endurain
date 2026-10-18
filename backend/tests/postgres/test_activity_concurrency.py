"""Optimistic concurrency and background writes on activities, against real PostgreSQL.

The mock tests show ``edit_activity`` is wired to the ``If-Match`` header; these show
the version a second session sees after the first has committed, which only separate
connections can.
"""

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema
from tests.postgres.test_transaction_ownership import _add_activity


def _edit(factory, activity_id: int, name: str, *, if_match: str | None = None) -> None:
    with factory() as db:
        activity_crud.edit_activity(1, activity_id, activity_schema.ActivityEdit(name=name), db, if_match=if_match)
        db.commit()


def _version(factory, activity_id: int) -> int:
    with factory() as db:
        activity = activity_crud.get_activity_by_id_from_user_id(activity_id, 1, db)
        assert activity is not None
        return activity.version


def test_an_edit_made_after_another_commit_is_refused_against_the_old_version(pg_factory):
    activity_id = _add_activity(pg_factory)
    seen = _version(pg_factory, activity_id)

    _edit(pg_factory, activity_id, "first", if_match=f'"{seen}"')

    with pytest.raises(core_exceptions.PreconditionFailedError):
        _edit(pg_factory, activity_id, "second", if_match=f'"{seen}"')


def test_the_precondition_is_checked_on_the_row_that_is_written(pg_factory):
    """A commit landing after the session started but before the edit's load is caught."""
    activity_id = _add_activity(pg_factory)
    seen = _version(pg_factory, activity_id)

    with pg_factory() as stale_session:
        # Opens the transaction, as the old pre-read did; READ COMMITTED means it pins nothing.
        activity_crud.get_activity_by_id_from_user_id(activity_id, 1, stale_session)
        _edit(pg_factory, activity_id, "other writer")
        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_crud.edit_activity(
                1, activity_id, activity_schema.ActivityEdit(name="mine"), stale_session, if_match=f'"{seen}"'
            )


def test_a_background_thumbnail_write_does_not_change_the_version(pg_factory):
    activity_id = _add_activity(pg_factory)
    seen = _version(pg_factory, activity_id)

    with pg_factory() as db:
        assert activity_crud.set_activity_thumbnail_key(activity_id, f"{activity_id}.webp", db) is True
        db.commit()

    assert _version(pg_factory, activity_id) == seen
    _edit(pg_factory, activity_id, "still allowed", if_match=f'"{seen}"')


def test_setting_a_thumbnail_key_on_a_deleted_activity_reports_it(pg_factory):
    with pg_factory() as db:
        assert activity_crud.set_activity_thumbnail_key(424242, "424242.webp", db) is False
