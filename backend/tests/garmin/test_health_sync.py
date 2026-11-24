"""The Garmin Connect health sync on the real database: body composition, daily steps and sleep."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import garminconnect
import pytest
from sqlalchemy import select

import core.database as core_database
import modules.garmin.health_service as garmin_health_service
import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.models as steps_models
import modules.health.health_weight.models as weight_models
from tests._factories import garmin as garmin_factories
from tests._factories.health import make_health_sleep, make_health_steps, make_health_weight
from tests.garmin.conftest import notifications_of, stored_token

_DAY = date(2026, 9, 29)
_START = datetime(2026, 9, 29, tzinfo=UTC)


def _sync(user, rate_limits, start: datetime = _START, end: datetime = _START):
    return garmin_health_service.get_user_garminconnect_health_by_dates(start, end, user.id, rate_limits)


def _rows(sessions, model, user):
    with sessions() as db:
        return list(db.scalars(select(model).where(model.user_id == user.id).order_by(model.date)))


class TestSleep:
    def test_a_night_is_stored_as_garmin_with_its_id_and_times(self, account, linked, rate_limits, committed_sessions):
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload(
            "2026-09-29", avgHeartRate=52.4, deepSleepSeconds=5400
        )

        assert _sync(linked, rate_limits) is True

        [night] = _rows(committed_sessions, sleep_models.HealthSleep, linked)
        assert (night.date, night.source, night.garminconnect_sleep_id, night.total_sleep_seconds) == (
            _DAY,
            "garmin",
            "1759000000000",
            28800,
        )
        assert (night.avg_heart_rate, night.deep_sleep_seconds) == (52, 5400)
        assert night.sleep_start_time_gmt == datetime.fromtimestamp(1759100000, tz=UTC)

    def test_stages_scores_and_hrv_are_stored_and_unknown_ones_dropped(
        self, account, linked, rate_limits, committed_sessions
    ):
        payload = garmin_factories.sleep_payload(
            "2026-09-29",
            sleepScores={
                "overall": {"value": 81, "qualifierKey": "GOOD"},
                "totalDuration": {"qualifierKey": "EXCELLENT"},
                "stress": {"qualifierKey": "FAIR"},
                "awakeCount": {"qualifierKey": "NOT_A_SCORE"},
            },
        )
        payload["hrvStatus"] = "BALANCED"
        payload["restingHeartRate"] = 48
        payload["sleepLevels"] = [
            {"activityLevel": 0, "startGMT": "2026-09-29T00:00:00.0", "endGMT": "2026-09-29T00:30:00.0"},
            {"activityLevel": 2, "startGMT": "2026-09-29T00:30:00.0", "endGMT": "2026-09-29T01:00:00.0"},
            {"activityLevel": 9, "startGMT": "2026-09-29T01:00:00.0", "endGMT": "2026-09-29T01:30:00.0"},
            {"activityLevel": None, "startGMT": None, "endGMT": None},
            {"activityLevel": 3, "startGMT": None, "endGMT": None},
        ]
        account.sleep["2026-09-29"] = payload

        _sync(linked, rate_limits)

        [night] = _rows(committed_sessions, sleep_models.HealthSleep, linked)
        assert (night.sleep_score_overall, night.sleep_score_quality, night.sleep_score_duration) == (
            81,
            "GOOD",
            "EXCELLENT",
        )
        assert (night.hrv_status, night.resting_heart_rate, night.sleep_stress_score) == ("BALANCED", 48, "FAIR")
        assert night.awake_count_score is None
        assert [(stage["stage_type"], stage["duration_seconds"]) for stage in night.sleep_stages] == [
            (0, 1800),
            (2, 1800),
            (3, None),
        ]

    @pytest.mark.parametrize("payload", [{"dailySleepDTO": {"id": None}}, {}, None])
    def test_a_day_without_sleep_is_skipped(self, account, linked, rate_limits, committed_sessions, payload):
        account.sleep["2026-09-29"] = payload

        _sync(linked, rate_limits)

        assert _rows(committed_sessions, sleep_models.HealthSleep, linked) == []

    def test_a_dto_without_sleep_time_is_skipped(self, account, linked, rate_limits, committed_sessions):
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29", sleepTimeSeconds=None)

        _sync(linked, rate_limits)

        assert _rows(committed_sessions, sleep_models.HealthSleep, linked) == []

    def test_every_day_of_the_window_is_asked_for_once(self, account, linked, rate_limits, committed_sessions):
        for offset in range(3):
            day = (_DAY + timedelta(days=offset)).isoformat()
            account.sleep[day] = garmin_factories.sleep_payload(day, id=100 + offset)

        _sync(linked, rate_limits, end=_START + timedelta(days=2))

        assert account.called("get_sleep_data") == [("2026-09-29",), ("2026-09-30",), ("2026-10-01",)]
        assert len(_rows(committed_sessions, sleep_models.HealthSleep, linked)) == 3

    def test_a_night_another_source_wrote_is_kept(self, account, linked, rate_limits, committed_sessions):
        with committed_sessions() as db:
            make_health_sleep(db, linked.id, date=_DAY, total_sleep_seconds=1000)
            db.commit()
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29")

        _sync(linked, rate_limits)

        [night] = _rows(committed_sessions, sleep_models.HealthSleep, linked)
        assert (night.source, night.total_sleep_seconds) == ("manual", 1000)

    def test_a_night_garmin_wrote_is_updated(self, account, linked, rate_limits, committed_sessions):
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29", sleepTimeSeconds=20000)
        _sync(linked, rate_limits)
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29", sleepTimeSeconds=21000)

        _sync(linked, rate_limits)

        [night] = _rows(committed_sessions, sleep_models.HealthSleep, linked)
        assert night.total_sleep_seconds == 21000

    def test_a_legacy_night_with_a_garmin_sleep_id_is_updated(self, account, linked, rate_limits, committed_sessions):
        with committed_sessions() as db:
            make_health_sleep(db, linked.id, date=_DAY, total_sleep_seconds=1000, garminconnect_sleep_id="123")
            db.commit()
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29")

        _sync(linked, rate_limits)

        [night] = _rows(committed_sessions, sleep_models.HealthSleep, linked)
        assert (night.source, night.total_sleep_seconds) == ("garmin", 28800)


class TestBodyComposition:
    def test_a_weigh_in_is_stored_in_kilograms_as_garmin(self, account, linked, rate_limits, committed_sessions):
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29")]

        _sync(linked, rate_limits)

        [weight] = _rows(committed_sessions, weight_models.HealthWeight, linked)
        assert (weight.date, weight.source, weight.weight_kg) == (_DAY, "garmin", Decimal("75.00"))
        assert (weight.bone_mass_kg, weight.muscle_mass_kg, weight.metabolic_age) == (
            Decimal("3.20"),
            Decimal("35.00"),
            30,
        )

    @pytest.mark.parametrize("metabolic_age", [0, 151])
    def test_a_metabolic_age_outside_one_to_a_hundred_fifty_is_a_bad_reading(
        self, account, linked, rate_limits, committed_sessions, metabolic_age
    ):
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29", metabolicAge=metabolic_age)]

        _sync(linked, rate_limits)

        [weight] = _rows(committed_sessions, weight_models.HealthWeight, linked)
        assert weight.metabolic_age is None

    def test_a_weigh_in_without_a_weight_is_skipped(self, account, linked, rate_limits, committed_sessions):
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29", weight_g=None)]

        _sync(linked, rate_limits)

        assert _rows(committed_sessions, weight_models.HealthWeight, linked) == []

    def test_a_weigh_in_without_bone_or_muscle_mass_stores_none(self, account, linked, rate_limits, committed_sessions):
        account.body_composition = [
            garmin_factories.body_composition_entry("2026-09-29", boneMass=None, muscleMass=None)
        ]

        _sync(linked, rate_limits)

        [weight] = _rows(committed_sessions, weight_models.HealthWeight, linked)
        assert (weight.bone_mass_kg, weight.muscle_mass_kg) == (None, None)

    def test_a_window_with_no_weigh_in_stores_nothing(self, account, linked, rate_limits, committed_sessions):
        assert _sync(linked, rate_limits) is True

        assert _rows(committed_sessions, weight_models.HealthWeight, linked) == []

    def test_a_manual_record_is_kept(self, account, linked, rate_limits, committed_sessions):
        with committed_sessions() as db:
            make_health_weight(db, linked.id, date=_DAY, weight_kg=80)
            db.commit()
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29")]

        _sync(linked, rate_limits)

        [weight] = _rows(committed_sessions, weight_models.HealthWeight, linked)
        assert (weight.source, weight.weight_kg) == ("manual", Decimal("80.00"))

    def test_a_garmin_record_is_updated(self, account, linked, rate_limits, committed_sessions):
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29", weight_g=70000.0)]
        _sync(linked, rate_limits)
        account.body_composition = [garmin_factories.body_composition_entry("2026-09-29", weight_g=71000.0)]

        _sync(linked, rate_limits)

        [weight] = _rows(committed_sessions, weight_models.HealthWeight, linked)
        assert weight.weight_kg == Decimal("71.00")


class TestDailySteps:
    def test_a_day_is_stored_as_garmin(self, account, linked, rate_limits, committed_sessions):
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", 9000)]

        _sync(linked, rate_limits)

        [steps] = _rows(committed_sessions, steps_models.HealthSteps, linked)
        assert (steps.date, steps.steps, steps.source) == (_DAY, 9000, "garmin")

    def test_a_zero_step_first_day_does_not_hide_the_rest_of_the_range(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.daily_steps = [
            garmin_factories.steps_entry("2026-09-29", 0),
            garmin_factories.steps_entry("2026-09-30", 4000),
        ]

        _sync(linked, rate_limits, end=_START + timedelta(days=1))

        assert [
            (row.date.isoformat(), row.steps) for row in _rows(committed_sessions, steps_models.HealthSteps, linked)
        ] == [
            ("2026-09-29", 0),
            ("2026-09-30", 4000),
        ]

    def test_a_day_without_a_step_count_is_skipped(self, account, linked, rate_limits, committed_sessions):
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", None)]

        _sync(linked, rate_limits)

        assert _rows(committed_sessions, steps_models.HealthSteps, linked) == []

    def test_a_manual_record_is_kept(self, account, linked, rate_limits, committed_sessions):
        with committed_sessions() as db:
            make_health_steps(db, linked.id, date=_DAY, steps=100)
            db.commit()
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", 9000)]

        _sync(linked, rate_limits)

        [steps] = _rows(committed_sessions, steps_models.HealthSteps, linked)
        assert (steps.source, steps.steps) == ("manual", 100)

    def test_a_garmin_record_is_updated(self, account, linked, rate_limits, committed_sessions):
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", 100)]
        _sync(linked, rate_limits)
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", 200)]

        _sync(linked, rate_limits)

        [steps] = _rows(committed_sessions, steps_models.HealthSteps, linked)
        assert steps.steps == 200


class TestTheSync:
    def test_a_sync_of_whole_days_reports_that_it_ran(self, account, linked, rate_limits, committed_sessions):
        account.daily_steps = [garmin_factories.steps_entry("2026-09-30", 500)]

        assert (
            garmin_health_service.sync_health_for_dates(_DAY, _DAY + timedelta(days=1), linked.id, rate_limits) is True
        )

        assert account.called("get_daily_steps") == [(("2026-09-29", "2026-09-30"),)]
        assert [row.steps for row in _rows(committed_sessions, steps_models.HealthSteps, linked)] == [500]

    def test_an_unlinked_user_is_skipped(self, account, unlinked, rate_limits):
        assert garmin_health_service.sync_health_for_dates(_DAY, _DAY, unlinked.id, rate_limits) is False

        assert account.calls == []

    def test_an_expired_token_unlinks_the_account_and_tells_the_user(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.fail("get_body_composition", garminconnect.GarminConnectAuthenticationError("401"))

        assert _sync(linked, rate_limits) is False

        assert stored_token(committed_sessions, linked.id) is None
        assert len(notifications_of(committed_sessions, linked.id)) == 1

    @pytest.mark.parametrize("method", ["get_body_composition", "get_daily_steps", "get_sleep_data"])
    def test_a_garmin_error_reaches_the_caller_instead_of_reading_as_no_data(
        self, account, linked, rate_limits, committed_sessions, method
    ):
        account.fail(method, RuntimeError("garmin 500"))

        with pytest.raises(RuntimeError, match="garmin 500"):
            _sync(linked, rate_limits)

        assert stored_token(committed_sessions, linked.id) is not None

    def test_garmin_is_called_with_no_database_connection_checked_out(self, account, linked, rate_limits):
        account.daily_steps = [garmin_factories.steps_entry("2026-09-29", 100)]
        account.sleep["2026-09-29"] = garmin_factories.sleep_payload("2026-09-29")
        checked_out: list[tuple[str, int]] = []
        account.on_call = lambda method: checked_out.append((method, core_database.engine.pool.checkedout()))

        _sync(linked, rate_limits)

        assert {method for method, _ in checked_out} == {"get_body_composition", "get_daily_steps", "get_sleep_data"}
        assert {count for _, count in checked_out} == {0}
