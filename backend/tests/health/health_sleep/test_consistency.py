"""A manual sleep record whose stages or total contradict each other is refused; a provider's is stored."""

from datetime import UTC, date, datetime, timedelta

import pytest

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_sleep.service as sleep_service
from tests._factories.users import make_user

_BED = datetime(2026, 1, 1, 22, 0, tzinfo=UTC)
_DAY = date(2026, 1, 2)

# A night as Garmin Connect reports it: the total is deep + light + rem, awake time is counted apart and the
# span from falling asleep to waking holds all of them.
_GARMIN_NIGHT = {
    "sleep_start_time_gmt": _BED,
    "sleep_end_time_gmt": _BED + timedelta(hours=8, minutes=30),
    "total_sleep_seconds": 27000,
    "deep_sleep_seconds": 5400,
    "light_sleep_seconds": 16200,
    "rem_sleep_seconds": 5400,
    "awake_sleep_seconds": 1800,
}


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


def _create(db, user, **fields):
    return sleep_service.create_health_sleep(user.id, sleep_schema.HealthSleepCreate(date=_DAY, **fields), db)


def _edit(db, user, record, **changes):
    return sleep_service.edit_health_sleep(
        user.id,
        record.id,
        sleep_schema.HealthSleepUpdate(**changes),
        db,
        if_match=core_etag.format_etag(record.version),
    )


class TestCreate:
    def test_a_garmin_shaped_night_is_accepted(self, db, user):
        assert _create(db, user, **_GARMIN_NIGHT).total_sleep_seconds == 27000

    def test_stages_beyond_the_total_are_refused(self, db, user):
        fields = {**_GARMIN_NIGHT, "deep_sleep_seconds": 20000}

        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, **fields)

    def test_stages_a_minute_over_the_total_are_tolerated_but_not_more(self, db, user):
        _create(db, user, total_sleep_seconds=3600, deep_sleep_seconds=3660)

        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, total_sleep_seconds=3600, deep_sleep_seconds=3661)

    def test_a_total_longer_than_the_span_is_refused(self, db, user):
        fields = {**_GARMIN_NIGHT, "sleep_end_time_gmt": _BED + timedelta(hours=2), "awake_sleep_seconds": 0}

        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, **fields)

    def test_the_local_times_bound_the_total_when_there_are_no_gmt_times(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError):
            _create(
                db,
                user,
                sleep_start_time_local=_BED,
                sleep_end_time_local=_BED + timedelta(hours=1),
                total_sleep_seconds=7200,
            )

    def test_a_total_without_times_or_stages_is_accepted(self, db, user):
        assert _create(db, user, total_sleep_seconds=28800).total_sleep_seconds == 28800

    def test_a_refused_record_is_not_stored(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, total_sleep_seconds=60, deep_sleep_seconds=7200)

        assert sleep_service.list_health_sleep(user.id, db).total == 0


class TestReadingRanges:
    def test_a_min_heart_rate_above_the_max_is_refused(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, min_heart_rate=90, max_heart_rate=50)

    def test_a_lowest_spo2_above_the_highest_is_refused(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, user, lowest_spo2_percent=98, highest_spo2_percent=90)

    def test_equal_or_one_sided_readings_are_accepted(self, db, user):
        assert _create(db, user, min_heart_rate=50, max_heart_rate=50).min_heart_rate == 50

    def test_an_edit_is_checked_against_the_stored_other_side(self, db, user):
        record = _create(
            db, user, min_heart_rate=50, max_heart_rate=80, lowest_spo2_percent=90, highest_spo2_percent=97
        )

        with pytest.raises(core_exceptions.InvalidInputError):
            _edit(db, user, record, min_heart_rate=90)
        with pytest.raises(core_exceptions.InvalidInputError):
            _edit(db, user, record, highest_spo2_percent=85)


class TestEdit:
    def test_a_stage_beyond_the_stored_total_is_refused(self, db, user):
        record = _create(db, user, **_GARMIN_NIGHT)

        with pytest.raises(core_exceptions.InvalidInputError):
            _edit(db, user, record, deep_sleep_seconds=26000)

    def test_a_total_beyond_the_stored_span_is_refused(self, db, user):
        record = _create(db, user, **_GARMIN_NIGHT)

        with pytest.raises(core_exceptions.InvalidInputError):
            _edit(db, user, record, sleep_end_time_gmt=_BED + timedelta(hours=3))

    def test_a_consistent_edit_is_accepted_and_scored(self, db, user):
        record = _create(db, user, **_GARMIN_NIGHT)

        edited = _edit(db, user, record, total_sleep_seconds=28800, rem_sleep_seconds=7200)

        assert edited.total_sleep_seconds == 28800
        assert edited.sleep_score_quality is not None

    def test_an_edit_that_changes_nothing_about_the_sleep_is_accepted(self, db, user):
        record = _create(db, user, **_GARMIN_NIGHT)

        assert _edit(db, user, record, avg_heart_rate=55).avg_heart_rate == 55


class TestProviderUpsert:
    def test_a_provider_record_is_stored_as_given(self, db, user):
        record = sleep_schema.HealthSleepImport(date=_DAY, **_GARMIN_NIGHT, source="garmin")

        assert sleep_integration.upsert_health_sleep(user.id, record, db).total_sleep_seconds == 27000
