"""The sleep records' application rules, on the real database."""

import uuid
from datetime import date, timedelta

import pytest

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.timezone as core_timezone
import modules.health.constants as health_constants
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service
from tests._factories.health import make_health_sleep
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)
# Deep, light and REM make up the total of 8 hours; awake time is counted apart.
_FULL_NIGHT = {
    "total_sleep_seconds": 28800,
    "deep_sleep_seconds": 5184,
    "light_sleep_seconds": 14400,
    "rem_sleep_seconds": 6480,
    "awake_sleep_seconds": 720,
    "awake_count": 0,
    "restless_moments_count": 0,
    "avg_sleep_stress": 20,
}


def _today() -> date:
    return core_timezone.today_in(core_timezone.or_default(None))


def _stored(db, record_id):
    return db.get(health_sleep_models.HealthSleep, record_id)


def _create(db, user, **fields):
    return health_sleep_service.create_health_sleep(
        user.id, health_sleep_schema.HealthSleepCreate(**{"date": _DAY, **fields}), db
    )


def _edit(db, user, record, *, if_match=None, **changes):
    return health_sleep_service.edit_health_sleep(
        user.id,
        record.id,
        health_sleep_schema.HealthSleepUpdate(**changes),
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
    def test_the_record_is_stored_and_scored(self, db, user):
        created = _create(db, user, **_FULL_NIGHT)

        assert health_sleep_service.get_health_sleep(user.id, created.id, db) == created
        assert (created.user_id, created.date, created.source) == (user.id, _DAY, "manual")
        assert created.sleep_score_overall is not None
        assert created.sleep_score_duration == "EXCELLENT"

    def test_without_a_date_the_record_is_for_the_users_today(self, db, user):
        assert _create(db, user, date=None).date == _today()

    def test_a_date_after_the_users_today_is_refused_and_nothing_is_stored(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _create(db, user, date=_today() + timedelta(days=1))

        assert health_sleep_service.list_health_sleep(user.id, db).total == 0

    def test_a_day_that_has_a_record_is_a_conflict_and_the_record_is_unchanged(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            first = make_health_sleep(db, user.id, date=_DAY, total_sleep_seconds=20000)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _create(db, user, total_sleep_seconds=30000)

        with committed_sessions() as db:
            assert _stored(db, first.id).total_sleep_seconds == 20000


class TestGet:
    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_sleep(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_service.get_health_sleep(user.id, theirs.id, db)

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_service.get_health_sleep(user.id, uuid.uuid4(), db)


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = _create(db, user, **_FULL_NIGHT)

        edited = _edit(db, user, record, resting_heart_rate=47)

        assert (edited.resting_heart_rate, edited.version) == (47, record.version + 1)
        assert _stored(db, record.id).resting_heart_rate == 47

    def test_a_scoring_input_rescores_the_merged_record_not_the_partial_body(self, db, user):
        record = _create(db, user, **_FULL_NIGHT)

        edited = _edit(db, user, record, awake_count=2)

        assert (edited.sleep_score_duration, edited.awake_count_score) == ("EXCELLENT", "GOOD")
        assert edited.total_sleep_seconds == 28800

    def test_a_change_without_a_scoring_input_keeps_every_score(self, db, user):
        record = _create(db, user, **_FULL_NIGHT)

        edited = _edit(db, user, record, resting_heart_rate=50)

        assert edited.sleep_score_overall == record.sleep_score_overall
        assert edited.awake_count_score == record.awake_count_score

    def test_a_score_the_client_sends_is_ignored(self, db, user):
        record = _create(db, user, **_FULL_NIGHT)

        edited = health_sleep_service.edit_health_sleep(
            user.id,
            record.id,
            health_sleep_schema.HealthSleepUpdate.model_construct(awake_count=2, sleep_score_overall=1),
            db,
            if_match='"1"',
        )

        assert edited.sleep_score_overall != 1

    def test_a_stale_version_is_refused_and_the_record_keeps_the_newer_value(self, db, user):
        record = _create(db, user)
        _edit(db, user, record, resting_heart_rate=47)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, user, record, resting_heart_rate=99)

        assert _stored(db, record.id).resting_heart_rate == 47

    def test_a_date_after_the_users_today_is_refused_and_the_record_keeps_its_date(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _edit(db, user, record, date=_today() + timedelta(days=1))

        assert _stored(db, record.id).date == _DAY

    def test_moving_to_a_taken_day_is_a_conflict_and_the_record_keeps_its_day(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            make_health_sleep(db, user.id, date=date(2025, 3, 1))
            moved = make_health_sleep(db, user.id, date=date(2025, 3, 2))
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _edit(db, user, moved, date=date(2025, 3, 1))

        with committed_sessions() as db:
            row = _stored(db, moved.id)
            assert (row.date, row.version) == (date(2025, 3, 2), 1)

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_sleep(db, other.id, resting_heart_rate=50)

        with pytest.raises(core_exceptions.NotFoundError):
            _edit(db, user, theirs, resting_heart_rate=60)

        assert _stored(db, theirs.id).resting_heart_rate == 50

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_service.edit_health_sleep(
                user.id, uuid.uuid4(), health_sleep_schema.HealthSleepUpdate(resting_heart_rate=60), db, if_match='"1"'
            )


class TestDelete:
    def test_the_record_is_gone_afterwards(self, db, user):
        record = _create(db, user)

        health_sleep_service.delete_health_sleep(user.id, record.id, db, if_match='"1"')

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_service.get_health_sleep(user.id, record.id, db)

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_sleep_service.delete_health_sleep(user.id, record.id, db, if_match='"7"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_sleep(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_service.delete_health_sleep(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None


class TestList:
    @pytest.fixture
    def records(self, db, user):
        today = _today()
        return {
            offset: make_health_sleep(db, user.id, date=today - timedelta(days=offset)) for offset in (0, 3, 20, 400)
        }

    def _dates(self, page):
        return [item.date for item in page.items]

    def test_a_page_holds_its_slice_and_the_total_counts_every_record(self, db, user, records):
        page = health_sleep_service.list_health_sleep(user.id, db, page_number=2, num_records=3)

        assert (len(page.items), page.total) == (1, 4)

    def test_an_interval_looks_back_from_the_users_today(self, db, user, records):
        today = _today()

        page = health_sleep_service.list_health_sleep(user.id, db, interval=health_constants.Interval.LAST_7_DAYS)

        assert self._dates(page) == [today, today - timedelta(days=3)]
        assert page.total == 2

    def test_no_interval_means_no_lower_bound(self, db, user, records):
        assert health_sleep_service.list_health_sleep(user.id, db).total == 4

    def test_a_date_range_replaces_the_interval(self, db, user, records):
        today = _today()
        window = core_date_range.DateRange(start_date=today - timedelta(days=25), end_date=today - timedelta(days=10))

        page = health_sleep_service.list_health_sleep(
            user.id, db, interval=health_constants.Interval.LAST_7_DAYS, date_range=window
        )

        assert self._dates(page) == [today - timedelta(days=20)]

    def test_the_resting_heart_rate_filter_reaches_the_count_and_the_page(self, db, user):
        make_health_sleep(db, user.id, date=date(2025, 3, 1), resting_heart_rate=50)
        make_health_sleep(db, user.id, date=date(2025, 3, 2))

        page = health_sleep_service.list_health_sleep(user.id, db, has_resting_heart_rate=False)

        assert (self._dates(page), page.total) == ([date(2025, 3, 2)], 1)

    def test_another_users_records_are_not_listed(self, db, user, other):
        make_health_sleep(db, other.id)

        assert health_sleep_service.list_health_sleep(user.id, db).total == 0


class TestChart:
    def test_the_totals_of_the_window_are_charted_by_day(self, db, user):
        today = _today()
        make_health_sleep(db, user.id, date=today, total_sleep_seconds=30000, resting_heart_rate=48)
        make_health_sleep(db, user.id, date=today - timedelta(days=1), total_sleep_seconds=20000)
        make_health_sleep(db, user.id, date=today - timedelta(days=30), total_sleep_seconds=1)

        totals = health_sleep_service.get_health_sleep_chart(user.id, health_constants.Interval.LAST_7_DAYS, db)
        rate = health_sleep_service.get_health_sleep_resting_heart_rate_chart(
            user.id, health_constants.Interval.LAST_7_DAYS, db
        )

        assert [(p.date, p.value) for p in totals.points] == [(today - timedelta(days=1), 20000.0), (today, 30000.0)]
        assert [(p.date, p.value) for p in rate.points] == [(today, 48.0)]


class TestRestoreProfileRecords:
    def test_an_archived_night_is_stored_and_a_second_one_of_the_day_updates_it(self, db, user):
        archived = {"date": "2025-03-10", "total_sleep_seconds": 25000, "source": "garmin"}

        assert health_sleep_service.restore_profile_records([archived], user.id, {}, db) == 1
        assert (
            health_sleep_service.restore_profile_records([{**archived, "total_sleep_seconds": 26000}], user.id, {}, db)
            == 1
        )

        page = health_sleep_service.list_health_sleep(user.id, db)
        assert [(i.total_sleep_seconds, i.source) for i in page.items] == [(26000, "garmin")]

    def test_a_record_the_schema_refuses_is_skipped_and_the_rest_restored(self, db, user):
        rows = [{"date": "2025-03-09", "total_sleep_seconds": -5}, {"date": "2025-03-10", "total_sleep_seconds": 3600}]

        assert health_sleep_service.restore_profile_records(rows, user.id, {}, db) == 1

        assert [i.date for i in health_sleep_service.list_health_sleep(user.id, db).items] == [_DAY]
