"""Tests for profile utility functions."""

import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from pydantic import BaseModel

import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import FileSizeError, JSONParseError, MemoryAllocationError


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
                return {"high": cls(batch_size=5000, max_memory_mb=2048)}

        config = TestConfig.get_auto_config()
        assert config.batch_size == 5000
        assert config.max_memory_mb == 2048

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_unknown_tier_defaults(self, mock_detect):
        mock_detect.return_value = ("unknown", 1024)

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                return {"high": cls(batch_size=5000)}

        config = TestConfig.get_auto_config()
        assert config.batch_size == 1000

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_detect_failure_propagates(self, mock_detect):
        mock_detect.side_effect = RuntimeError("detect failed")

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                return {"high": cls(batch_size=5000)}

        with pytest.raises(RuntimeError, match="detect failed"):
            TestConfig.get_auto_config()

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_broken_tier_configs_propagate(self, mock_detect):
        mock_detect.return_value = ("high", 4096)

        class TestConfig(profile_utils.BasePerformanceConfig):
            @classmethod
            def _get_tier_configs(cls):
                raise RuntimeError("broken tier configs")

        with pytest.raises(RuntimeError, match="broken tier configs"):
            TestConfig.get_auto_config()

    @patch("modules.users.users_profile.utils.detect_system_memory_tier")
    def test_get_auto_config_without_tier_configs_raises(self, mock_detect):
        mock_detect.return_value = ("high", 4096)

        with pytest.raises(NotImplementedError):
            profile_utils.BasePerformanceConfig.get_auto_config()


class TestModelToDict:
    def test_a_schema_is_dumped_as_json(self):
        class Record(BaseModel):
            day: date
            amount: Decimal

        assert profile_utils.model_to_dict(Record(day=date(2026, 1, 2), amount=Decimal("1.5"))) == {
            "day": "2026-01-02",
            "amount": "1.5",
        }


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
        assert counts["user_images"] == 0
        assert counts["user"] == 0
        assert len(counts) == 7

    def test_with_user_count(self):
        counts = profile_utils.initialize_operation_counts(include_user_count=True)
        assert counts["user"] == 1

    def test_all_expected_keys_present(self):
        counts = profile_utils.initialize_operation_counts()
        expected_keys = {
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


class TestWriteJsonArrayToZip:
    """The streamed entry is what ``write_json_to_zip`` writes for the same items, held a batch at a time."""

    @staticmethod
    def _entry(write) -> tuple[str, dict[str, int]]:
        import io
        import zipfile

        buf = io.BytesIO()
        counts: dict[str, int] = {}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            write(archive, counts)
        with zipfile.ZipFile(buf) as archive:
            return archive.read("data/items.json").decode(), counts

    def test_matches_the_in_memory_writer_byte_for_byte(self):
        items = [{"id": 1, "name": "Corrida ☀"}, {"id": 2, "when": __import__("datetime").date(2026, 1, 2)}, {"id": 3}]

        streamed, streamed_counts = self._entry(
            lambda z, c: profile_utils.write_json_array_to_zip(z, "data/items.json", [items[:2], items[2:]], c)
        )
        whole, whole_counts = self._entry(lambda z, c: profile_utils.write_json_to_zip(z, "data/items.json", items, c))

        assert streamed == whole
        assert streamed_counts == whole_counts == {"items": 3}

    def test_no_batches_is_an_empty_array(self):
        raw, counts = self._entry(lambda z, c: profile_utils.write_json_array_to_zip(z, "data/items.json", [], c))

        assert raw == "[]"
        assert counts == {"items": 0}

    def test_empty_batches_are_ignored(self):
        raw, counts = self._entry(
            lambda z, c: profile_utils.write_json_array_to_zip(z, "data/items.json", [[], [{"id": 1}], []], c)
        )

        assert raw == '[{"id": 1}]'
        assert counts == {"items": 1}

    def test_batches_are_read_lazily(self):
        seen: list[str] = []

        def batches():
            seen.append("first")
            yield [{"id": 1}]
            seen.append("second")
            yield [{"id": 2}]

        self._entry(lambda z, c: profile_utils.write_json_array_to_zip(z, "data/items.json", batches(), c))

        assert seen == ["first", "second"]


def _zip_of(files: dict[str, bytes]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


def _reader(z, **overrides) -> profile_utils.ZipArchiveReader:
    limits = {
        "max_json_bytes": 1024 * 1024,
        "max_uncompressed_bytes": 10 * 1024 * 1024,
        "max_memory_mb": 1024,
        "enable_memory_monitoring": False,
    }
    return profile_utils.ZipArchiveReader(z, **{**limits, **overrides})


class _Row(BaseModel):
    id: int


class TestZipArchiveWriter:
    def test_write_json_writes_the_entry_and_counts_it_by_stem(self):
        buf = io.BytesIO()
        counts: dict[str, int] = {}
        with zipfile.ZipFile(buf, "w") as z:
            profile_utils.ZipArchiveWriter(z, counts).write_json("data/gears.json", [_Row(id=1), _Row(id=2)])

        with zipfile.ZipFile(buf) as z:
            assert json.loads(z.read("data/gears.json")) == [{"id": 1}, {"id": 2}]
        assert counts == {"gears": 2}

    def test_an_empty_write_counts_zero(self):
        counts: dict[str, int] = {}
        with zipfile.ZipFile(io.BytesIO(), "w") as z:
            profile_utils.ZipArchiveWriter(z, counts).write_json("data/gear_components.json", [])

        assert counts == {"gear_components": 0}

    def test_write_json_stream_matches_write_json_and_counts_every_record(self):
        buf = io.BytesIO()
        counts: dict[str, int] = {}
        with zipfile.ZipFile(buf, "w") as z:
            writer = profile_utils.ZipArchiveWriter(z, counts)
            writer.write_json_stream("data/streamed.json", iter([[_Row(id=1)], [], [_Row(id=2), _Row(id=3)]]))
            writer.write_json("data/whole.json", [_Row(id=1), _Row(id=2), _Row(id=3)])

        with zipfile.ZipFile(buf) as z:
            assert z.read("data/streamed.json") == z.read("data/whole.json")
        assert counts == {"streamed": 3, "whole": 3}

    def test_write_bytes_writes_the_entry_without_counting(self):
        buf = io.BytesIO()
        counts: dict[str, int] = {}
        with zipfile.ZipFile(buf, "w") as z:
            profile_utils.ZipArchiveWriter(z, counts).write_bytes("activity_files/1.gpx", b"<gpx/>")

        with zipfile.ZipFile(buf) as z:
            assert z.read("activity_files/1.gpx") == b"<gpx/>"
        assert counts == {}


class TestZipArchiveReader:
    def test_names_lists_the_entries(self):
        reader = _reader(_zip_of({"data/a.json": b"[]", "user_images/1.png": b"x"}))

        assert reader.names == frozenset({"data/a.json", "user_images/1.png"})

    def test_load_json_returns_the_objects(self):
        reader = _reader(_zip_of({"data/gears.json": b'[{"id": 1}, 7, "gear", null, {"id": 2}]'}))

        assert reader.load_json("data/gears.json") == [{"id": 1}, {"id": 2}]

    def test_an_absent_entry_loads_as_empty(self):
        assert _reader(_zip_of({})).load_json("data/missing.json") == []

    @pytest.mark.parametrize("content", [b"null", b"{}", b'"string"', b"42"])
    def test_an_entry_that_is_not_a_list_loads_as_empty(self, content):
        assert _reader(_zip_of({"data/t.json": content})).load_json("data/t.json") == []

    def test_invalid_json_raises(self):
        with pytest.raises(JSONParseError):
            _reader(_zip_of({"data/bad.json": b"not-json"})).load_json("data/bad.json")

    def test_an_oversized_json_entry_is_refused_before_it_is_parsed(self):
        reader = _reader(_zip_of({"data/gears.json": b"[" + b'{"id": 1},' * 50 + b"{}]"}), max_json_bytes=10)

        with pytest.raises(FileSizeError):
            reader.load_json("data/gears.json")

    def test_load_json_checks_memory_after_parsing_unless_told_not_to(self):
        reader = _reader(_zip_of({"data/a.json": b"[]"}))

        with patch.object(profile_utils, "check_memory_usage") as check:
            reader.load_json("data/a.json")
            reader.load_json("data/a.json", check_memory=False)

        check.assert_called_once_with("loading data/a.json", 1024, False)

    def test_memory_over_the_limit_raises(self):
        reader = _reader(_zip_of({"data/a.json": b"[]"}), enable_memory_monitoring=True, max_memory_mb=0)

        with pytest.raises(MemoryAllocationError):
            reader.load_json("data/a.json")

    def test_read_bytes_refuses_an_entry_declared_over_the_cap(self):
        reader = _reader(_zip_of({"activity_files/1.gpx": b"x" * 100}))

        with pytest.raises(FileSizeError, match="exceeds maximum"):
            reader.read_bytes("activity_files/1.gpx", max_bytes=10)

    def test_read_bytes_enforces_the_cap_against_the_decompressed_bytes(self):
        z = _zip_of({"data/test.json": b"x" * 2048})
        reader = _reader(z)
        info = z.getinfo("data/test.json")

        with (
            patch.object(type(info), "file_size", new_callable=PropertyMock, return_value=10),
            patch.object(z, "open", return_value=io.BytesIO(b"x" * 100)),
            pytest.raises(FileSizeError, match="decompressed size exceeds"),
        ):
            reader.read_bytes("data/test.json", max_bytes=50)

    def test_the_bytes_read_across_entries_are_capped(self):
        reader = _reader(
            _zip_of({"data/a.json": b'["' + b"x" * 60 + b'"]', "data/b.json": b'["' + b"y" * 60 + b'"]'}),
            max_uncompressed_bytes=100,
        )

        reader.load_json("data/a.json")
        with pytest.raises(FileSizeError, match="uncompressed"):
            reader.load_json("data/b.json")

    def test_load_json_part_returns_the_objects_of_a_part(self):
        reader = _reader(_zip_of({"data/laps_000.json": b'[{"activity_id": 1}, 3]'}))

        assert reader.load_json_part("data/laps_000.json") == [{"activity_id": 1}]

    @pytest.mark.parametrize("content", [b"not-valid-json", b"{}"])
    def test_a_bad_part_is_skipped(self, content):
        assert _reader(_zip_of({"data/laps_000.json": content})).load_json_part("data/laps_000.json") == []

    def test_a_part_over_the_cap_is_skipped(self):
        reader = _reader(_zip_of({"data/laps_000.json": b'[{"activity_id": 1}]'}), max_json_bytes=5)

        assert reader.load_json_part("data/laps_000.json") == []

    def test_a_part_that_breaks_the_archive_cap_is_skipped(self):
        reader = _reader(
            _zip_of({"data/a.json": b'["' + b"x" * 60 + b'"]', "data/laps_000.json": b'[{"activity_id": 1}]'}),
            max_uncompressed_bytes=70,
        )

        reader.load_json("data/a.json")

        assert reader.load_json_part("data/laps_000.json") == []

    def test_a_memory_error_while_reading_a_part_propagates(self):
        reader = _reader(_zip_of({"data/laps_000.json": b"[]"}))

        with (
            patch.object(profile_utils.ZipArchiveReader, "_read", side_effect=MemoryAllocationError("oom")),
            pytest.raises(MemoryAllocationError),
        ):
            reader.load_json_part("data/laps_000.json")
