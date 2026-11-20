"""The weight records' application rules, on the real database."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from tests._factories.health import make_health_weight
from tests._factories.users import make_user

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.timezone as core_timezone
import modules.health.constants as health_constants
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service

_DAY = date(2025, 3, 10)


def _today() -> date:
    """The user's today: the tests' users have no timezone, and the code reads the day from the platform clock."""
    return core_timezone.today_in(core_timezone.or_default(None))


def _stored(db, record_id):
    return db.get(health_weight_models.HealthWeight, record_id)


def _create(db, user, **fields):
    return health_weight_service.create_health_weight(
        user.id, health_weight_schema.HealthWeightCreate(**{"date": _DAY, "weight_kg": 75.0, **fields}), db
    )


def _edit(db, user, record, *, if_match=None, **changes):
    return health_weight_service.edit_health_weight(
        user.id,
        record.id,
        health_weight_schema.HealthWeightUpdate(**changes),
        db,
        if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
    )


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


class TestCreate:
    def test_the_record_is_stored_and_committed(self, db, user):
        created = _create(db, user, weight_kg=71.5)

        assert health_weight_service.get_health_weight(user.id, created.id, db) == created
        assert (created.user_id, created.date, created.weight_kg, created.source) == (user.id, _DAY, 71.5, "manual")

    def test_without_a_date_the_record_is_for_the_users_today(self, db, user):
        created = _create(db, user, date=None)

        assert created.date == _today()

    def test_a_date_after_the_users_today_is_refused_and_nothing_is_stored(self, db, user):
        tomorrow = _today() + timedelta(days=1)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _create(db, user, date=tomorrow)

        assert health_weight_crud.get_health_weight_number_by_user_id(user.id, db) == 0

    def test_the_users_today_is_accepted(self, db, user):
        assert _create(db, user, date=_today()).date == _today()

    def test_a_day_that_has_a_record_is_a_conflict_and_the_record_is_unchanged(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            first = make_health_weight(db, user.id, date=_DAY, weight_kg=70.0)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _create(db, user, weight_kg=99.0)

        with committed_sessions() as db:
            assert _stored(db, first.id).weight_kg == Decimal("70.00")
            assert health_weight_crud.get_health_weight_number_by_user_id(user.id, db) == 1


class TestGet:
    def test_a_record_the_user_does_not_have_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError, match="Health weight not found"):
            health_weight_service.get_health_weight(user.id, uuid.uuid4(), db)

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_weight(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_service.get_health_weight(user.id, theirs.id, db)


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = _create(db, user, weight_kg=70.0)

        edited = _edit(db, user, record, weight_kg=68.0)

        assert (edited.weight_kg, edited.version) == (68.0, record.version + 1)
        assert _stored(db, record.id).weight_kg == Decimal("68.00")

    def test_a_stale_version_is_refused_and_the_record_keeps_the_newer_value(self, db, user):
        record = _create(db, user, weight_kg=70.0)
        _edit(db, user, record, weight_kg=71.0)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, user, record, weight_kg=99.0)

        assert _stored(db, record.id).weight_kg == Decimal("71.00")

    def test_a_date_after_the_users_today_is_refused_and_the_record_keeps_its_date(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _edit(db, user, record, date=_today() + timedelta(days=1))

        assert _stored(db, record.id).date == _DAY

    def test_moving_to_a_taken_day_is_a_conflict_and_the_record_keeps_its_day(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            make_health_weight(db, user.id, date=date(2025, 3, 1))
            moved = make_health_weight(db, user.id, date=date(2025, 3, 2))
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _edit(db, user, moved, date=date(2025, 3, 1))

        with committed_sessions() as db:
            row = _stored(db, moved.id)
            assert (row.date, row.version) == (date(2025, 3, 2), 1)

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_weight(db, other.id, weight_kg=75.0)

        with pytest.raises(core_exceptions.NotFoundError):
            _edit(db, user, theirs, weight_kg=1.0)

        assert (_stored(db, theirs.id).weight_kg, _stored(db, theirs.id).version) == (Decimal("75.00"), 1)

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_service.edit_health_weight(
                user.id, uuid.uuid4(), health_weight_schema.HealthWeightUpdate(weight_kg=1.0), db, if_match='"1"'
            )


class TestDelete:
    def test_the_record_is_gone_afterwards(self, db, user):
        record = _create(db, user)

        health_weight_service.delete_health_weight(
            user.id, record.id, db, if_match=core_etag.format_etag(record.version)
        )

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_service.get_health_weight(user.id, record.id, db)

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_weight_service.delete_health_weight(user.id, record.id, db, if_match='"7"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_weight(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_service.delete_health_weight(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None


class TestList:
    @pytest.fixture
    def records(self, db, user):
        today = _today()
        return {
            offset: make_health_weight(db, user.id, date=today - timedelta(days=offset)) for offset in (0, 3, 20, 400)
        }

    def _page(self, db, user, **kwargs):
        return health_weight_service.list_health_weight(user.id, db, **kwargs)

    @pytest.mark.usefixtures("records")
    def test_without_an_interval_every_record_is_listed_newest_first_with_the_total(self, db, user):
        page = self._page(db, user)

        assert [r.date for r in page.items] == [_today() - timedelta(days=d) for d in (0, 3, 20, 400)]
        assert (page.total, page.page, page.num_records, page.next) == (4, 1, 25, None)

    @pytest.mark.usefixtures("records")
    @pytest.mark.parametrize(
        ("interval", "kept_offsets"),
        [
            (health_constants.Interval.LAST_7_DAYS, (0, 3)),
            (health_constants.Interval.LAST_30_DAYS, (0, 3, 20)),
            (health_constants.Interval.LAST_YEAR, (0, 3, 20)),
            (health_constants.Interval.ALL_TIME, (0, 3, 20, 400)),
        ],
    )
    def test_an_interval_keeps_the_records_looking_back_from_the_users_today(self, db, user, interval, kept_offsets):
        page = self._page(db, user, interval=interval)

        assert [r.date for r in page.items] == [_today() - timedelta(days=d) for d in kept_offsets]
        assert page.total == len(kept_offsets)

    @pytest.mark.usefixtures("records")
    def test_a_date_range_replaces_the_interval(self, db, user):
        window = core_date_range.DateRange(_today() - timedelta(days=400), _today() - timedelta(days=20))

        page = self._page(db, user, interval=health_constants.Interval.LAST_7_DAYS, date_range=window)

        assert [r.date for r in page.items] == [_today() - timedelta(days=d) for d in (20, 400)]
        assert page.total == 2

    @pytest.mark.usefixtures("records")
    def test_the_total_counts_every_record_in_the_window_while_the_page_holds_its_slice(self, db, user):
        first = self._page(db, user, page_number=1, num_records=3)
        second = self._page(db, user, page_number=2, num_records=3)

        assert (len(first.items), first.total, first.next) == (3, 4, 2)
        assert (len(second.items), second.total, second.next) == (1, 4, None)

    def test_another_users_records_are_not_listed(self, db, user, other):
        make_health_weight(db, other.id, date=_today())

        page = self._page(db, user)

        assert (page.items, page.total) == ([], 0)


class TestChart:
    def test_a_window_is_one_averaged_point_per_day_with_a_value(self, db, user):
        today = _today()
        make_health_weight(db, user.id, date=today, weight_kg=70.0)
        make_health_weight(db, user.id, date=today - timedelta(days=2), weight_kg=72.0)
        make_health_weight(db, user.id, date=today - timedelta(days=30), weight_kg=99.0)

        series = health_weight_service.get_health_weight_chart(user.id, health_constants.Interval.LAST_7_DAYS, db)

        assert series.bucket == health_constants.ChartBucket.DAY
        assert [(p.date, p.value) for p in series.points] == [(today - timedelta(days=2), 72.0), (today, 70.0)]

    def test_a_date_range_replaces_the_interval(self, db, user):
        make_health_weight(db, user.id, date=date(2025, 3, 1), weight_kg=70.0)

        series = health_weight_service.get_health_weight_chart(
            user.id,
            health_constants.Interval.LAST_7_DAYS,
            db,
            date_range=core_date_range.DateRange(date(2025, 3, 1), date(2025, 3, 2)),
        )

        assert [(p.date, p.value) for p in series.points] == [(date(2025, 3, 1), 70.0)]


class TestRestoreProfileRecords:
    def _restore(self, db, user, records):
        return health_weight_service.restore_profile_records(records, user.id, {}, db)

    def test_the_archived_records_are_stored_for_the_importing_user_not_the_exporter(self, db, user):
        exporter, archived_id = uuid.uuid4(), uuid.uuid4()
        record = {
            "id": str(archived_id),
            "user_id": str(exporter),
            "version": 9,
            "updated_at": "2020-01-01T00:00:00Z",
            "date": "2025-03-01",
            "weight_kg": 70.5,
            "source": "garmin",
            "bmi": 21.5,
        }

        assert self._restore(db, user, [record]) == 1

        stored = health_weight_crud.get_all_health_weight_by_user_id(user.id, db)
        assert [(r.user_id, r.date, r.weight_kg, r.source, r.bmi, r.version) for r in stored] == [
            (user.id, date(2025, 3, 1), 70.5, "garmin", 21.5, 1)
        ]
        assert stored[0].id != archived_id

    def test_numbers_archived_as_text_are_read_as_numbers(self, db, user):
        record = {"date": "2025-03-01", "weight_kg": "70.5", "body_fat_percent": "18.25", "physique_rating": "4"}

        self._restore(db, user, [record])

        (stored,) = health_weight_crud.get_all_health_weight_by_user_id(user.id, db)
        assert (stored.weight_kg, stored.body_fat_percent, stored.physique_rating) == (70.5, 18.25, 4)

    def test_a_record_that_is_invalid_is_skipped_and_the_rest_are_stored(self, db, user):
        records = [
            {"date": "2025-03-01", "weight_kg": "not a number"},
            {"date": "2025-03-02", "weight_kg": 600.0},
            {"date": "2025-03-03", "weight_kg": 70.0},
        ]

        assert self._restore(db, user, records) == 1

        stored = health_weight_crud.get_all_health_weight_by_user_id(user.id, db)
        assert [r.date for r in stored] == [date(2025, 3, 3)]

    def test_a_record_for_a_day_the_user_has_updates_it(self, db, user):
        existing = make_health_weight(db, user.id, date=date(2025, 3, 1), weight_kg=70.0)

        self._restore(db, user, [{"date": "2025-03-01", "weight_kg": 65.0}])

        stored = health_weight_crud.get_all_health_weight_by_user_id(user.id, db)
        assert [(r.id, r.weight_kg) for r in stored] == [(existing.id, 65.0)]

    def test_an_empty_archive_stores_nothing(self, db, user):
        assert self._restore(db, user, []) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(health_weight_models.HealthWeight)) == 0


class TestUpsert:
    def _upsert(self, db, user, **fields):
        record = health_weight_schema.HealthWeightImport(**{"date": _DAY, "weight_kg": 75.0, **fields})
        return health_weight_service.stage_upsert_health_weight(user.id, record, db)

    def test_a_new_day_is_created_with_the_source_it_came_from(self, db, user):
        staged = self._upsert(db, user, source="garmin")

        assert (staged.source, staged.version) == ("garmin", 1)

    def test_a_day_that_has_a_record_is_updated_instead_of_conflicting(self, db, user):
        first = self._upsert(db, user, weight_kg=70.0, source="garmin")

        second = self._upsert(db, user, weight_kg=71.0, source="garmin")

        assert (second.id, second.weight_kg) == (first.id, 71.0)
        assert health_weight_crud.get_health_weight_number_by_user_id(user.id, db) == 1

    def test_without_a_date_the_record_is_for_the_users_today(self, db, user):
        assert self._upsert(db, user, date=None).date == _today()

    def test_another_users_record_of_the_day_is_left_alone(self, db, user, other):
        theirs = make_health_weight(db, other.id, date=_DAY, weight_kg=60.0)

        mine = self._upsert(db, user, weight_kg=75.0)

        assert mine.id != theirs.id
        assert _stored(db, theirs.id).weight_kg == Decimal("60.00")
