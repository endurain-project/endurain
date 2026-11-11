from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import modules.health.health_dashboard.service as health_dashboard_service
import modules.health.health_targets.schema as health_targets_schema

_PREFIX = "modules.health.health_dashboard.service"


@pytest.fixture
def peers():
    """Patch every peer read the dashboard makes, keyed by metric."""
    targets = {
        "sleep": "health_sleep_integration.get_health_sleep_by_date",
        "weight": "health_weight_integration.get_latest_health_weight",
        "steps": "health_steps_integration.get_health_steps_by_date",
        "fasting": "health_fasting_integration.get_active_fasting",
        "water": "health_water_integration.get_health_water_by_date",
        "poop": "health_poop_integration.list_health_poop_by_date",
        "targets": "health_targets_integration.get_health_targets",
    }
    patchers = {name: patch(f"{_PREFIX}.{target}", return_value=None) for name, target in targets.items()}
    with patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15)):
        mocks = {name: patcher.start() for name, patcher in patchers.items()}
        try:
            yield mocks
        finally:
            for patcher in patchers.values():
                patcher.stop()


class TestGetDailyStats:
    def test_all_data_present(self, peers, mock_db):
        peers["sleep"].return_value = MagicMock(
            total_sleep_seconds=28800, resting_heart_rate=50, hrv_status="balanced", avg_skin_temp_deviation=0.1
        )
        peers["weight"].return_value = MagicMock(weight_kg=75.5, bmi=24.5)
        peers["steps"].return_value = MagicMock(steps=8000)
        peers["fasting"].return_value = MagicMock(
            id=1,
            fast_start_time=date(2024, 1, 15),
            fast_end_time=None,
            status="in_progress",
            actual_duration_seconds=3600,
        )
        peers["water"].return_value = MagicMock(amount_ml=1500.0)
        peers["poop"].return_value = [MagicMock(), MagicMock()]
        targets = health_targets_schema.HealthTargetsRead(
            updated_at="2024-01-01T00:00:00Z",
            id=2,
            user_id=1,
            version=3,
            sleep_seconds=28800,
            steps=8000,
            weight_kg=70.0,
            fasting_seconds=57600,
            water_ml=2000,
            poop_count=1,
        )
        peers["targets"].return_value = targets

        result = health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True)

        assert result.sleep.total_sleep_seconds == 28800
        assert result.weight.weight_kg == 75.5
        assert result.steps.steps == 8000
        assert result.fasting.status == "in_progress"
        assert result.water.amount_ml == 1500.0
        assert result.poop.count == 2
        peers["weight"].assert_called_once_with(1, date(2024, 1, 15), mock_db)
        assert result.targets == targets
        peers["targets"].assert_called_once_with(1, mock_db)

    def test_all_data_missing(self, peers, mock_db):
        result = health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True)

        assert result.model_dump() == dict.fromkeys(("sleep", "weight", "steps", "fasting", "water", "poop", "targets"))

    def test_reads_every_day_metric_for_the_users_own_today(self, peers, mock_db):
        health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True)

        for name in ("sleep", "steps", "water", "poop"):
            assert peers[name].call_args.args == (1, "2024-01-15", mock_db)

    def test_sleep_without_hrv_status_is_still_shown(self, peers, mock_db):
        peers["sleep"].return_value = MagicMock(
            total_sleep_seconds=27000, resting_heart_rate=None, hrv_status=None, avg_skin_temp_deviation=None
        )

        sleep = health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True).sleep

        assert sleep is not None
        assert sleep.total_sleep_seconds == 27000
        assert sleep.hrv_status is None

    def test_sleep_with_hrv_status_carries_it(self, peers, mock_db):
        peers["sleep"].return_value = MagicMock(
            total_sleep_seconds=27000, resting_heart_rate=48, hrv_status="BALANCED", avg_skin_temp_deviation=0.2
        )

        assert health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True).sleep.hrv_status == "BALANCED"

    def test_water_without_an_amount_is_left_out(self, peers, mock_db):
        peers["water"].return_value = MagicMock(amount_ml=None)

        assert health_dashboard_service.get_daily_stats(1, mock_db, include_targets=True).water is None

    def test_targets_are_not_read_without_the_scope(self, peers, mock_db):
        peers["targets"].return_value = MagicMock()

        result = health_dashboard_service.get_daily_stats(1, mock_db, include_targets=False)

        assert result.targets is None
        peers["targets"].assert_not_called()
