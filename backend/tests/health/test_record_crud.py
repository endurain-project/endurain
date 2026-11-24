"""The persistence steps every health package shares, on the real database.

Steps records stand for any kind; weight records, which have a numeric column, stand for the comparison of values.
"""

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.models as health_models
import modules.health.record_crud as health_record_crud
from tests._factories.health import make_health_steps, make_health_weight
from tests._factories.users import make_user

_SPEC = health_steps_crud.SPEC
_DAY = date(2025, 3, 10)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestRead:
    def test_an_owned_row_is_loaded_by_its_id(self, db, user):
        record = make_health_steps(db, user.id)

        row = health_record_crud.get_owned(_SPEC, record.id, user.id, db)

        assert (row.id, row.user_id, row.steps) == (record.id, user.id, 5000)

    def test_another_users_row_is_not_found_with_the_spec_message(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_crud.get_owned(_SPEC, theirs.id, user.id, db)

    def test_a_row_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_crud.get_owned(_SPEC, uuid.uuid4(), user.id, db)

    def test_a_record_exists_for_its_owner_only(self, db, user, other):
        record = make_health_steps(db, user.id)

        assert health_record_crud.exists(_SPEC, record.id, user.id, db) is True
        assert health_record_crud.exists(_SPEC, record.id, other.id, db) is False
        assert health_record_crud.exists(_SPEC, uuid.uuid4(), user.id, db) is False

    def test_a_record_is_found_by_id_as_its_read_schema(self, db, user):
        record = make_health_steps(db, user.id, steps=123)

        found = health_record_crud.find_by_id(_SPEC, record.id, user.id, db)

        assert isinstance(found, health_steps_schema.HealthStepsRead)
        assert (found.id, found.steps) == (record.id, 123)

    def test_another_users_record_is_not_found_by_id(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        assert health_record_crud.find_by_id(_SPEC, theirs.id, user.id, db) is None

    def test_a_record_is_found_by_its_date_for_its_owner_only(self, db, user, other):
        mine = make_health_steps(db, user.id, date=_DAY)
        make_health_steps(db, user.id, date=_DAY - timedelta(days=1))
        make_health_steps(db, other.id, date=_DAY + timedelta(days=1))

        assert health_record_crud.find_by_date(_SPEC, user.id, _DAY.isoformat(), db) == mine
        assert health_record_crud.find_by_date(_SPEC, user.id, (_DAY + timedelta(days=1)).isoformat(), db) is None


class TestList:
    @pytest.fixture
    def days(self, db, user, other):
        """Five days of steps for the user and one of another, returned oldest first."""
        days = [_DAY + timedelta(days=offset) for offset in range(5)]
        for day in days:
            make_health_steps(db, user.id, date=day, steps=1000 + day.day)
        make_health_steps(db, other.id, date=_DAY)
        return days

    def _page(self, db, user, **kwargs):
        defaults = {"since": None, "until": None, "page_number": None, "num_records": None}
        return health_record_crud.list_page(
            _SPEC,
            user.id,
            health_steps_models.HealthSteps.date,
            health_steps_models.HealthSteps.date,
            **{**defaults, **kwargs},
            db=db,
        )

    def _count(self, db, user, **kwargs):
        defaults = {"since": None, "until": None}
        return health_record_crud.count(
            _SPEC, user.id, health_steps_models.HealthSteps.date, **{**defaults, **kwargs}, db=db
        )

    def test_the_users_records_come_newest_first(self, db, user, days):
        assert [r.date for r in self._page(db, user)] == sorted(days, reverse=True)

    def test_the_window_is_inclusive_at_both_ends(self, db, user, days):
        page = self._page(db, user, since=days[1], until=days[3])

        assert [r.date for r in page] == [days[3], days[2], days[1]]
        assert self._count(db, user, since=days[1], until=days[3]) == 3

    def test_an_open_window_counts_every_record_of_the_user(self, db, user, days):
        assert self._count(db, user) == 5

    def test_a_page_needs_both_the_number_and_the_size(self, db, user, days):
        assert len(self._page(db, user, page_number=2)) == 5
        assert len(self._page(db, user, num_records=2)) == 5
        assert [r.date for r in self._page(db, user, page_number=2, num_records=2)] == [days[2], days[1]]

    def test_a_further_condition_narrows_the_records(self, db, user, days):
        wanted = health_steps_models.HealthSteps.steps > 1000 + days[2].day - 1

        page = health_record_crud.list_page(
            _SPEC,
            user.id,
            health_steps_models.HealthSteps.date,
            health_steps_models.HealthSteps.date,
            None,
            None,
            None,
            None,
            db,
            conditions=[wanted],
        )

        assert [r.date for r in page] == [days[4], days[3], days[2]]
        assert (
            health_record_crud.count(
                _SPEC, user.id, health_steps_models.HealthSteps.date, None, None, db, conditions=[wanted]
            )
            == 3
        )


class TestCreate:
    def test_a_second_record_on_a_day_is_the_given_conflict(self, db, user):
        make_health_steps(db, user.id, date=_DAY)

        with pytest.raises(core_exceptions.ConflictError, match="taken"):
            health_record_crud.create(
                _SPEC, user.id, health_steps_schema.HealthStepsCreate(date=_DAY, steps=1), db, conflict="taken"
            )

    def test_without_a_conflict_the_integrity_error_is_not_translated(self, db, user):
        make_health_steps(db, user.id, date=_DAY)
        row = health_steps_models.HealthSteps(user_id=user.id, date=_DAY, steps=1)
        db.add(row)

        with pytest.raises(IntegrityError, match="uq_health_steps_user_date"):
            health_record_crud.save(_SPEC, row, db)

    def test_the_duplicate_date_message_names_the_day(self):
        assert health_record_crud.duplicate_date_message(_DAY).endswith("created for 2025-03-10")


class TestEditRow:
    def test_only_the_set_fields_are_applied_and_the_version_moves_on(self, db, user):
        record = make_health_steps(db, user.id, date=_DAY, steps=10)

        edited = health_record_crud.edit(
            _SPEC, record.id, user.id, health_steps_schema.HealthStepsUpdate(steps=20), db, if_match='"1"'
        )

        assert (edited.steps, edited.date, edited.version) == (20, _DAY, 2)

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_steps(db, user.id, steps=10)
        health_record_crud.edit(
            _SPEC, record.id, user.id, health_steps_schema.HealthStepsUpdate(steps=11), db, if_match='"1"'
        )

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_record_crud.edit(
                _SPEC, record.id, user.id, health_steps_schema.HealthStepsUpdate(steps=99), db, if_match='"1"'
            )

        assert db.get(health_steps_models.HealthSteps, record.id).steps == 11

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_record_crud.edit(
                _SPEC, theirs.id, user.id, health_steps_schema.HealthStepsUpdate(steps=1), db, if_match='"1"'
            )

    def test_a_move_onto_a_taken_day_is_the_given_conflict(self, db, user):
        make_health_steps(db, user.id, date=_DAY)
        moved = make_health_steps(db, user.id, date=_DAY + timedelta(days=1))

        with pytest.raises(core_exceptions.ConflictError, match="taken"):
            health_record_crud.edit(
                _SPEC,
                moved.id,
                user.id,
                health_steps_schema.HealthStepsUpdate(date=_DAY),
                db,
                if_match='"1"',
                conflict="taken",
            )

    @pytest.mark.parametrize(("sent", "version"), [(75.0, 1), (75.001, 1), (75.5, 2)])
    def test_a_number_that_is_the_stored_value_at_its_scale_changes_nothing(self, db, user, sent, version):
        record = make_health_weight(db, user.id, weight_kg=75.0)

        edited = health_record_crud.edit(
            health_weight_crud.SPEC,
            record.id,
            user.id,
            health_weight_schema.HealthWeightUpdate(weight_kg=sent),
            db,
            if_match='"1"',
        )

        assert edited.version == version
        assert db.get(health_weight_models.HealthWeight, record.id).version == version


class TestDelete:
    def test_the_named_version_deletes_the_row_and_leaves_a_tombstone(self, db, user):
        record = make_health_steps(db, user.id)

        health_record_crud.delete(_SPEC, record.id, user.id, db, if_match='"1"')

        assert db.get(health_steps_models.HealthSteps, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_steps")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_steps(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_record_crud.delete(_SPEC, record.id, user.id, db, if_match='"4"')

        assert db.get(health_steps_models.HealthSteps, record.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_record_crud.delete(_SPEC, theirs.id, user.id, db, if_match='"1"')

        assert db.get(health_steps_models.HealthSteps, theirs.id) is not None
