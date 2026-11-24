"""Storing a day's record, or updating the one the day has, on the real database.

The read, create and edit steps are the steps crud's own; a stale read or a row that moves under an edit is arranged
by what ``find`` and ``edit`` report.
"""

from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
from tests._factories.health import make_health_steps
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)


@pytest.fixture
def user(db):
    return make_user(db)


class _Steps:
    """The steps crud as the three steps of an upsert, with a count of the calls to each."""

    def __init__(self, db, user, *, steps=10, hide_existing=False):
        self.db = db
        self.user = user
        self.steps = steps
        self.hide_existing = hide_existing
        self.finds = 0
        self.creates = 0
        self.edits = 0

    def find(self):
        self.finds += 1
        if self.hide_existing and self.finds == 1:
            return None
        return health_steps_crud.get_health_steps_by_date_and_user_id(self.user.id, _DAY.isoformat(), self.db)

    def create(self):
        self.creates += 1
        return health_steps_crud.create_health_steps(
            self.user.id, health_steps_schema.HealthStepsCreate(date=_DAY, steps=self.steps), self.db
        )

    def edit(self, record_id):
        self.edits += 1
        return health_steps_crud.edit_health_steps(
            self.user.id, record_id, health_steps_schema.HealthStepsUpdate(steps=self.steps), self.db, if_match="*"
        )

    def upsert(self):
        return health_computation.upsert_for_day(self.find, self.create, self.edit, self.db)


def _stored(db, user):
    rows = db.scalars(
        sa.select(health_steps_models.HealthSteps).where(health_steps_models.HealthSteps.user_id == user.id)
    )
    return [(row.date, row.steps) for row in rows]


class TestUpsertForDay:
    def test_creates_the_record_when_the_day_has_none(self, db, user):
        steps = _Steps(db, user)

        stored = steps.upsert()

        assert (steps.creates, steps.edits) == (1, 0)
        assert (stored.date, stored.steps) == (_DAY, 10)
        assert _stored(db, user) == [(_DAY, 10)]

    def test_edits_the_record_the_day_already_has(self, db, user):
        existing = make_health_steps(db, user.id, date=_DAY, steps=5)
        steps = _Steps(db, user)

        stored = steps.upsert()

        assert (steps.creates, steps.edits) == (0, 1)
        assert (stored.id, stored.steps) == (existing.id, 10)
        assert _stored(db, user) == [(_DAY, 10)]

    def test_a_writer_that_created_the_day_first_is_updated_instead_and_the_session_stays_usable(self, db, user):
        existing = make_health_steps(db, user.id, date=_DAY, steps=5)
        steps = _Steps(db, user, hide_existing=True)

        stored = steps.upsert()

        assert (steps.creates, steps.edits) == (1, 1)
        assert (stored.id, stored.steps) == (existing.id, 10)
        assert _stored(db, user) == [(_DAY, 10)]

    def test_a_conflict_with_no_record_to_find_is_raised(self, db, user):
        def create():
            raise core_exceptions.ConflictError("duplicate")

        with pytest.raises(core_exceptions.ConflictError):
            health_computation.upsert_for_day(lambda: None, create, lambda record_id: None, db)

    def test_a_row_changed_under_the_edit_is_read_again_and_retried(self, db, user):
        make_health_steps(db, user.id, date=_DAY, steps=5)
        steps = _Steps(db, user)
        edit = steps.edit
        failures = [StaleDataError("moved")]

        def edit_after_a_stale_attempt(record_id):
            if failures:
                raise failures.pop()
            return edit(record_id)

        health_computation.upsert_for_day(steps.find, steps.create, edit_after_a_stale_attempt, db)

        assert (steps.finds, steps.edits) == (2, 1)
        assert _stored(db, user) == [(_DAY, 10)]

    def test_a_row_that_keeps_moving_is_given_up_on(self, db, user):
        make_health_steps(db, user.id, date=_DAY, steps=5)
        steps = _Steps(db, user)
        attempts = []

        def always_stale(record_id):
            attempts.append(record_id)
            raise StaleDataError("moved")

        with pytest.raises(StaleDataError):
            health_computation.upsert_for_day(steps.find, steps.create, always_stale, db)

        assert len(attempts) == health_constants.UPSERT_ATTEMPTS
        assert _stored(db, user) == [(_DAY, 5)]

    def test_a_row_deleted_by_another_session_between_attempts_is_raised(self, committed_sessions):
        with committed_sessions() as setup:
            owner = make_user(setup)
            existing = make_health_steps(setup, owner.id, date=_DAY, steps=5)
            setup.commit()

        with committed_sessions() as db:
            steps = _Steps(db, owner)

            def deleted_by_another_session(record_id):
                with committed_sessions() as other:
                    other.delete(other.get(health_steps_models.HealthSteps, existing.id))
                    other.commit()
                raise StaleDataError("moved")

            with pytest.raises(StaleDataError):
                health_computation.upsert_for_day(steps.find, steps.create, deleted_by_another_session, db)

        with committed_sessions() as db:
            assert _stored(db, owner) == []
