"""Tests for profile utility functions."""

from unittest.mock import MagicMock, patch

import pytest

import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import MemoryAllocationError


class TestBasePerformanceConfig:
    """Test suite for BasePerformanceConfig."""

    def test_default_values(self):
        config = profile_utils.BasePerformanceConfig()
        assert config.batch_size == 1000
        assert config.max_memory_mb == 1024
        assert config.timeout_seconds == 3600
        assert config.chunk_size == 8192
        assert config.enable_memory_monitoring is True

    def test_custom_values(self):
        config = profile_utils.BasePerformanceConfig(
            batch_size=100,
            max_memory_mb=512,
            timeout_seconds=1800,
            chunk_size=4096,
            enable_memory_monitoring=False,
        )
        assert config.batch_size == 100
        assert config.max_memory_mb == 512
        assert config.timeout_seconds == 1800
        assert config.chunk_size == 4096
        assert config.enable_memory_monitoring is False

    def test_get_tier_configs_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            profile_utils.BasePerformanceConfig._get_tier_configs()

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_calls_get_tier_configs(self, mock_detect):
        mock_detect.return_value = ("high", 4096)

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                return {"high": {"batch_size": 5000, "max_memory_mb": 2048}}

        config = TestConfig.get_auto_config()
        assert config.batch_size == 5000
        assert config.max_memory_mb == 2048

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_unknown_tier_defaults(self, mock_detect):
        mock_detect.return_value = ("unknown", 1024)

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                return {"high": {"batch_size": 5000}}

        config = TestConfig.get_auto_config()
        assert config.batch_size == 1000

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_detect_failure_defaults(self, mock_detect):
        mock_detect.side_effect = Exception("detect failed")

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                return {"high": {"batch_size": 5000}}

        config = TestConfig.get_auto_config()
        assert config.batch_size == 1000


class TestSQLAlchemyObjToDict:
    """Test suite for sqlalchemy_obj_to_dict function."""

    def test_with_sqlalchemy_object(self):
        col_id = MagicMock()
        col_id.name = "id"
        col_name = MagicMock()
        col_name.name = "name"

        table_mock = MagicMock()
        table_mock.columns.__iter__.return_value = iter([col_id, col_name])

        obj = MagicMock()
        obj.__table__ = table_mock
        obj.id = 1
        obj.name = "Test"

        result = profile_utils.sqlalchemy_obj_to_dict(obj)
        assert result == {"id": 1, "name": "Test"}

    def test_without_table_attribute(self):
        result = profile_utils.sqlalchemy_obj_to_dict("not_an_sa_obj")
        assert result == "not_an_sa_obj"

    def test_with_dict(self):
        result = profile_utils.sqlalchemy_obj_to_dict({"key": "value"})
        assert result == {"key": "value"}


class TestWriteJsonToZip:
    """Test suite for write_json_to_zip function."""

    def test_with_data_list(self):
        mock_zip = MagicMock()
        counts = {}

        profile_utils.write_json_to_zip(mock_zip, "activities/data.json", [{"id": 1}], counts)

        assert counts["data"] == 1
        mock_zip.writestr.assert_called_once()
        args = mock_zip.writestr.call_args[0]
        assert args[0] == "activities/data.json"

    def test_with_data_dict(self):
        mock_zip = MagicMock()
        counts = {}

        profile_utils.write_json_to_zip(mock_zip, "user/profile.json", {"name": "test"}, counts)

        assert counts["profile"] == 1

    def test_with_empty_dict_writes_to_zip(self):
        mock_zip = MagicMock()
        counts = {}

        profile_utils.write_json_to_zip(mock_zip, "activities/data.json", {}, counts)

        assert counts["data"] == 1
        mock_zip.writestr.assert_called_once()

    def test_with_empty_list_writes_to_zip(self):
        mock_zip = MagicMock()
        counts = {}

        profile_utils.write_json_to_zip(mock_zip, "activities/data.json", [], counts)

        assert counts["data"] == 0
        mock_zip.writestr.assert_called_once()

    def test_with_none_data_coerces_to_empty_list(self):
        mock_zip = MagicMock()
        counts = {}

        profile_utils.write_json_to_zip(mock_zip, "activities/data.json", None, counts)

        assert counts["data"] == 0
        mock_zip.writestr.assert_called_once()
        _, written_content = mock_zip.writestr.call_args[0]
        assert written_content == "[]"


class TestCheckTimeout:
    """Test suite for check_timeout function."""

    @patch("modules.users.users_profile.utils.time.time")
    def test_timeout_not_exceeded(self, mock_time):
        mock_time.return_value = 5.0

        profile_utils.check_timeout(10, 0.0, TimeoutError, "test")

    @patch("modules.users.users_profile.utils.time.time")
    def test_timeout_exceeded(self, mock_time):
        mock_time.return_value = 15.0

        with pytest.raises(TimeoutError, match="test exceeded 10 seconds"):
            profile_utils.check_timeout(10, 0.0, TimeoutError, "test")

    def test_timeout_none_skips_check(self):
        profile_utils.check_timeout(None, 0.0, TimeoutError, "test")


class TestGetMemoryUsageMB:
    """Test suite for get_memory_usage_mb function."""

    @patch("modules.users.users_profile.utils.psutil.Process")
    def test_returns_memory_usage(self, mock_process):
        mock_proc = MagicMock()
        mock_proc.memory_info.return_value.rss = 104857600
        mock_process.return_value = mock_proc

        result = profile_utils.get_memory_usage_mb(True)
        assert result == 100.0

    @patch("modules.users.users_profile.utils.psutil.Process")
    def test_monitoring_disabled_returns_zero(self, mock_process):
        result = profile_utils.get_memory_usage_mb(False)
        assert result == 0.0
        mock_process.assert_not_called()

    @patch("modules.users.users_profile.utils.psutil.Process")
    def test_exception_returns_zero(self, mock_process):
        mock_process.side_effect = Exception("process error")

        result = profile_utils.get_memory_usage_mb(True)
        assert result == 0.0


class TestCheckMemoryUsage:
    """Test suite for check_memory_usage function."""

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_memory_within_limits(self, mock_get_memory):
        mock_get_memory.return_value = 500.0

        profile_utils.check_memory_usage("export", 1024)

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_memory_exceeds_limit(self, mock_get_memory):
        mock_get_memory.return_value = 1100.0

        with pytest.raises(MemoryAllocationError):
            profile_utils.check_memory_usage("export", 1024)

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_monitoring_disabled_skips_check(self, mock_get_memory):
        profile_utils.check_memory_usage("export", 1024, enable_monitoring=False)
        mock_get_memory.assert_not_called()

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_memory_intensive_operation_higher_threshold(self, mock_get_memory):
        mock_get_memory.return_value = 1500.0

        profile_utils.check_memory_usage("data collection export", 1024)

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_memory_intensive_operation_still_exceeds(self, mock_get_memory):
        mock_get_memory.return_value = 2000.0

        with pytest.raises(MemoryAllocationError):
            profile_utils.check_memory_usage("data collection export", 1024)

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_custom_memory_intensive_operations_still_exceeds(self, mock_get_memory):
        mock_get_memory.return_value = 2000.0

        with pytest.raises(MemoryAllocationError):
            profile_utils.check_memory_usage("custom operation", 1024, memory_intensive_operations=["custom operation"])

    @patch("modules.users.users_profile.utils.get_memory_usage_mb")
    def test_custom_ops_not_matched_raises_at_normal_limit(self, mock_get_memory):
        mock_get_memory.return_value = 1100.0

        with pytest.raises(MemoryAllocationError):
            profile_utils.check_memory_usage("random task", 1024, memory_intensive_operations=["specific op"])


class TestInitializeOperationCounts:
    """Test suite for initialize_operation_counts function."""

    def test_all_counts_initialized_to_zero(self):
        counts = profile_utils.initialize_operation_counts()
        assert counts["media"] == 0
        assert counts["activities"] == 0
        assert counts["user"] == 0
        assert len(counts) == 20

    def test_with_user_count(self):
        counts = profile_utils.initialize_operation_counts(include_user_count=True)
        assert counts["user"] == 1

    def test_all_expected_keys_present(self):
        counts = profile_utils.initialize_operation_counts()
        expected_keys = {
            "media",
            "activity_files",
            "activities",
            "activity_laps",
            "activity_sets",
            "activity_streams",
            "activity_workout_steps",
            "activity_media",
            "activity_exercise_titles",
            "gears",
            "gear_components",
            "health_weight",
            "health_targets",
            "user_images",
            "user",
            "user_default_gear",
            "user_goals",
            "user_identity_providers",
            "user_integrations",
            "user_privacy_settings",
        }
        assert set(counts.keys()) == expected_keys


class TestDetectSystemMemoryTier:
    """Test suite for detect_system_memory_tier function."""

    @patch("modules.users.users_profile.utils.psutil.virtual_memory")
    def test_high_tier(self, mock_vm):
        mock_mem = MagicMock()
        mock_mem.available = 3000 * 1024 * 1024
        mock_vm.return_value = mock_mem

        tier, mb = profile_utils.detect_system_memory_tier()
        assert tier == "high"
        assert mb == 3000

    @patch("modules.users.users_profile.utils.psutil.virtual_memory")
    def test_medium_tier(self, mock_vm):
        mock_mem = MagicMock()
        mock_mem.available = 1500 * 1024 * 1024
        mock_vm.return_value = mock_mem

        tier, mb = profile_utils.detect_system_memory_tier()
        assert tier == "medium"
        assert mb == 1500

    @patch("modules.users.users_profile.utils.psutil.virtual_memory")
    def test_low_tier(self, mock_vm):
        mock_mem = MagicMock()
        mock_mem.available = 500 * 1024 * 1024
        mock_vm.return_value = mock_mem

        tier, mb = profile_utils.detect_system_memory_tier()
        assert tier == "low"
        assert mb == 500

    @patch("modules.users.users_profile.utils.psutil.virtual_memory")
    def test_exception_defaults_to_medium(self, mock_vm):
        mock_vm.side_effect = Exception("memory detection failed")

        tier, mb = profile_utils.detect_system_memory_tier()
        assert tier == "medium"
        assert mb == 1024
