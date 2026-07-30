"""Tests for profile data export service."""

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import modules.users.users_profile.export_service as profile_export_service
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    DatabaseConnectionError,
    DataCollectionError,
    ExportTimeoutError,
    FileSystemError,
    MemoryAllocationError,
    ZipCreationError,
)


class _FakeZipBytes:
    """Capture ZIP writes for assertions."""

    def __init__(self) -> None:
        self.buf = io.BytesIO()

    @property
    def zipf(self) -> zipfile.ZipFile:
        self.buf.seek(0)
        return zipfile.ZipFile(self.buf, "r")

    def assert_contains(self, name: str) -> None:
        z = self.zipf
        assert name in z.namelist(), f"ZIP missing {name}, got {z.namelist()}"


def _make_activity_mock(activity_id: int) -> MagicMock:
    m = MagicMock()
    m.id = activity_id
    return m


class TestExportPerformanceConfig:
    def test_tier_configs(self) -> None:
        configs = profile_export_service.ExportPerformanceConfig._get_tier_configs()
        assert "high" in configs
        assert "medium" in configs
        assert "low" in configs

    def test_init_defaults(self) -> None:
        config = profile_export_service.ExportPerformanceConfig()
        assert config.batch_size == 125
        assert config.max_memory_mb == 1024
        assert config.compression_level == 6
        assert config.chunk_size == 8192

    def test_get_auto_config_uses_low_tier(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: ("low", 512),
        )
        config = profile_export_service.ExportPerformanceConfig.get_auto_config()
        assert config.batch_size == 50
        assert config.max_memory_mb == 512

    def test_get_auto_config_uses_high_tier(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: ("high", 4096),
        )
        config = profile_export_service.ExportPerformanceConfig.get_auto_config()
        assert config.batch_size == 250
        assert config.max_memory_mb == 2048


class TestExportServiceInit:
    def test_init_creates_service(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        assert service.user_id == 1
        assert service.db is mock_db
        assert "activities" in service.counts

    def test_init_with_custom_config(self) -> None:
        mock_db = MagicMock(spec=Session)
        config = profile_export_service.ExportPerformanceConfig(batch_size=10)
        service = profile_export_service.ExportService(
            user_id=1,
            db=mock_db,
            performance_config=config,
        )
        assert service.performance_config.batch_size == 10


class TestExportServiceCollectUserActivities:
    def test_no_activities_writes_empty(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(service, "_get_activities_batch", return_value=[]),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                result = service.collect_user_activities_data(z)

        assert result == []
        mock_write.assert_called_once()

    def test_collects_activities_in_batches(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 2
            service.performance_config.enable_memory_monitoring = False

            batch1 = [_make_activity_mock(1), _make_activity_mock(2)]
            batch2 = [_make_activity_mock(3)]

            with (
                patch.object(
                    service,
                    "_get_activities_batch",
                    side_effect=[batch1, batch2, []],
                ),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
            ):
                result = service.collect_user_activities_data(z)

        assert len(result) == 3
        assert result[0].id == 1
        assert result[2].id == 3

    def test_get_activities_batch_calls_crud_and_returns_activities(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        mock_activity = _make_activity_mock(1)

        with patch(
            "modules.users.users_profile.export_service.activities_integration.list_user_activities_page",
            return_value=[mock_activity],
        ):
            result = service._get_activities_batch(0, 10)

        assert len(result) == 1
        assert result[0].id == 1

    def test_get_activities_batch_raises_on_exception(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)

        with (
            patch(
                "modules.users.users_profile.export_service.activities_integration.list_user_activities_page",
                side_effect=Exception("db error"),
            ),
            pytest.raises(Exception, match="db error"),
        ):
            service._get_activities_batch(0, 10)

    def test_get_activities_batch_loop_continues_on_failure(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 2
            service.performance_config.enable_memory_monitoring = False

            batch1 = [_make_activity_mock(1), _make_activity_mock(2)]
            # First call returns batch1, second raises, third returns batch2
            batch2 = [_make_activity_mock(3)]
            calls = [batch1, Exception("transient error"), batch2, []]

            call_results = []

            def side_effect(*args, **kwargs):
                val = calls.pop(0)
                if isinstance(val, Exception):
                    raise val
                call_results.append(val)
                return val

            with (
                patch.object(service, "_get_activities_batch", side_effect=side_effect),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
            ):
                result = service.collect_user_activities_data(z)

        assert len(result) == 3
        assert result[0].id == 1
        assert result[2].id == 3

    def test_activities_batch_sqlalchemy_error_propagates(self) -> None:
        """SQLAlchemyError from a batch propagates as DatabaseConnectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(
                    service,
                    "_get_activities_batch",
                    side_effect=SQLAlchemyError("db down"),
                ),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
                pytest.raises(DatabaseConnectionError),
            ):
                service.collect_user_activities_data(z)

    def test_get_activities_batch_memory_error_propagates(self) -> None:
        """MemoryAllocationError from a batch propagates through batch loop."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(
                    service,
                    "_get_activities_batch",
                    side_effect=MemoryAllocationError("oom"),
                ),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
                pytest.raises(MemoryAllocationError),
            ):
                service.collect_user_activities_data(z)

    def test_component_data_collection_error_propagates_unwrapped(self) -> None:
        """DataCollectionError from component processing propagates unwrapped."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            activity = _make_activity_mock(1)

            with (
                patch.object(service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(
                    service,
                    "_collect_and_write_activity_components",
                    side_effect=DataCollectionError("component failure"),
                ),
                pytest.raises(DataCollectionError, match="component failure"),
            ):
                service.collect_user_activities_data(z)


class TestExportServiceCollectGearData:
    def test_collect_gear_empty_components(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch("modules.users.users_profile.export_service.gear_crud.get_gear_user", return_value=[]),
                patch(
                    "modules.users.users_profile.export_service.gear_components_crud.get_gear_components_user",
                    return_value=[],
                ),
            ):
                service.collect_gear_data(z)

    def test_collect_gear_with_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False
            mock_gears = [MagicMock(), MagicMock()]

            with (
                patch(
                    "modules.users.users_profile.export_service.gear_crud.get_gear_user",
                    return_value=mock_gears,
                ),
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
            ):
                service.collect_gear_data(z)

        assert service.counts["gears"] == 2

    def test_collect_gear_no_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with patch(
                "modules.users.users_profile.export_service.gear_crud.get_gear_user",
                return_value=[],
            ):
                service.collect_gear_data(z)

        # Empty data: no count increment
        assert service.counts.get("gears", 0) == 0

    def test_collect_gear_with_exception_raises_data_collection_error(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.gear_crud.get_gear_user",
                    side_effect=Exception("unexpected"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_gear_data(z)

    def test_collect_gear_components_exception_raises_data_collection_error(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.gear_crud.get_gear_user",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.gear_components_crud.get_gear_components_user",
                    side_effect=Exception("components fail"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_gear_data(z)


class TestExportServiceCollectHealthWeight:
    def test_collect_health_weight_with_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False
            mock_health = [MagicMock(), MagicMock()]

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_crud.get_all_health_weight_by_user_id",
                    return_value=mock_health,
                ),
                patch(
                    "modules.users.users_profile.export_service.health_targets_crud.get_health_targets_by_user_id",
                    return_value=MagicMock(),
                ),
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
            ):
                service.collect_health_weight(z)

        assert service.counts.get("health_weight", 0) >= 2

    def test_collect_health_weight_crud_exception_raises_data_collection_error(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_crud.get_all_health_weight_by_user_id",
                    side_effect=Exception("unexpected"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_health_weight(z)

    def test_collect_health_weight_no_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_crud.get_all_health_weight_by_user_id",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.health_targets_crud.get_health_targets_by_user_id",
                    return_value=None,
                ),
            ):
                service.collect_health_weight(z)


class TestExportServiceCollectUserSettings:
    def test_collect_settings_all_empty(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.user_goals_crud.get_user_goals_by_user_id",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_crud.get_user_integrations_by_user_id",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_crud.get_user_privacy_settings_by_user_id",
                    return_value=None,
                ),
            ):
                service.collect_user_settings_data(z)

    def test_collect_settings_all_present(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    return_value=MagicMock(),
                ),
                patch(
                    "modules.users.users_profile.export_service.user_goals_crud.get_user_goals_by_user_id",
                    return_value=[MagicMock()],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_crud.get_user_integrations_by_user_id",
                    return_value=MagicMock(),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_crud.get_user_privacy_settings_by_user_id",
                    return_value=MagicMock(),
                ),
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
            ):
                service.collect_user_settings_data(z)

        assert service.counts.get("user_default_gear", 0) >= 1
        assert service.counts.get("user_goals", 0) >= 1

    def test_identity_providers_not_in_export_zip(self) -> None:
        """Verify identity-link data is never written to the export ZIP (security boundary)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.user_goals_crud.get_user_goals_by_user_id",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_crud.get_user_integrations_by_user_id",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_crud.get_user_privacy_settings_by_user_id",
                    return_value=None,
                ),
            ):
                service.collect_user_settings_data(z)

        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert "data/user_identity_providers.json" not in z.namelist()

    def test_collect_settings_with_db_error_caught_inner(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    side_effect=Exception("fail"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_settings_data(z)


class TestExportServiceActivityFiles:
    def test_add_activity_files_none_stored(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch(
                "modules.users.users_profile.export_service.activity_file_storage_service.get_activity_file",
                return_value=None,
            ):
                service.add_activity_files_to_zip(z, [_make_activity_mock(1)])

        assert service.counts.get("activity_files", 0) == 0

    def test_add_activity_files_no_activities(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            service.add_activity_files_to_zip(z, [])
            # Should return early without error

    def test_add_activity_files_with_files(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch(
                "modules.users.users_profile.export_service.activity_file_storage_service.get_activity_file",
                return_value=("1.gpx", b"<gpx></gpx>"),
            ):
                service.add_activity_files_to_zip(z, [_make_activity_mock(1)])

        assert service.counts["activity_files"] == 1
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert "activity_files/1.gpx" in z.namelist()


class TestExportServiceActivityMedia:
    def test_add_activity_media_missing_dir(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch("modules.users.users_profile.export_service.platform_runtime") as runtime:
                runtime.get_active_platform.return_value.storage.list_keys.return_value = []
                service.add_activity_media_to_zip(z, [_make_activity_mock(1)])

        assert service.counts["media"] == 0

    def test_add_activity_media_no_activities(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            service.add_activity_media_to_zip(z, [])
            # Should return early without error

    def test_add_activity_media_with_files(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch("modules.users.users_profile.export_service.platform_runtime") as runtime:
                storage = runtime.get_active_platform.return_value.storage
                storage.list_keys.return_value = ["1_image.jpg"]
                storage.get.return_value = b"image-bytes"
                service.add_activity_media_to_zip(z, [_make_activity_mock(1)])

        assert service.counts["media"] == 1
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as written:
            assert written.read("activity_media/1_image.jpg") == b"image-bytes"

    def test_add_activity_media_skips_a_missing_blob(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch("modules.users.users_profile.export_service.platform_runtime") as runtime:
                storage = runtime.get_active_platform.return_value.storage
                storage.list_keys.return_value = ["1_image.jpg"]
                storage.get.return_value = None
                service.add_activity_media_to_zip(z, [_make_activity_mock(1)])

        assert service.counts["media"] == 0


def _make_scandir_mock(entries: list) -> MagicMock:
    """Create a mock context manager for os.scandir."""
    m = MagicMock()
    m.__enter__.return_value = entries
    m.__exit__.return_value = None
    return m


class TestExportServiceUserImages:
    """User photos are exported through the StorageProvider, not a local walk."""

    @staticmethod
    def _export(user_id: int, keys: list[str], blob: bytes | None = b"image-bytes"):
        buf = io.BytesIO()
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=user_id, db=mock_db)
        service.performance_config.enable_memory_monitoring = False

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch("modules.users.users_profile.export_service.platform_runtime") as runtime,
        ):
            storage = runtime.get_active_platform.return_value.storage
            storage.list_keys.return_value = keys
            storage.get.return_value = blob
            service.add_user_images_to_zip(z)
        return service, buf, storage

    def test_no_stored_photo(self) -> None:
        service, _, _ = self._export(1, [])

        assert service.counts["user_images"] == 0

    def test_writes_the_blob_under_its_key(self) -> None:
        service, buf, storage = self._export(1, ["1.jpg"])

        assert service.counts["user_images"] == 1
        storage.list_keys.assert_called_once_with("user_images", "1.")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as written:
            assert written.read("user_images/1.jpg") == b"image-bytes"

    def test_only_the_owner_prefix_is_listed(self) -> None:
        """Listing by prefix is what stops user 1's export leaking user 12's photo."""
        _, _, storage = self._export(1, ["1.jpg"])

        assert storage.list_keys.call_args.args[1] == "1."

    def test_skips_a_missing_blob(self) -> None:
        service, _, _ = self._export(1, ["1.jpg"], blob=None)

        assert service.counts["user_images"] == 0

    def test_large_image_is_still_exported(self) -> None:
        service, _, _ = self._export(1, ["1.jpg"], blob=b"x" * (11 * 1024 * 1024))

        assert service.counts["user_images"] == 1

    def test_a_listing_failure_is_logged_not_raised(self) -> None:
        buf = io.BytesIO()
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch("modules.users.users_profile.export_service.platform_runtime") as runtime,
        ):
            runtime.get_active_platform.return_value.storage.list_keys.side_effect = OSError("perms")
            service.add_user_images_to_zip(z)

        assert service.counts["user_images"] == 0

    def test_a_read_failure_skips_only_that_blob(self) -> None:
        service, _, _ = self._export(1, ["1.jpg"], blob=None)

        assert service.counts["user_images"] == 0


class TestExportServiceGenerateExportArchive:
    def test_generate_archive_streams_bytes(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        user_dict = {"id": 1, "username": "test"}

        with (
            patch.object(
                service,
                "collect_user_activities_data",
                return_value=[_make_activity_mock(1)],
            ),
            patch.object(service, "collect_gear_data"),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(service, "add_activity_files_to_zip"),
            patch.object(service, "add_activity_media_to_zip"),
            patch.object(service, "add_user_images_to_zip"),
        ):
            chunks = list(service.generate_export_archive(user_dict, timeout_seconds=60))

        assert len(chunks) > 0
        assert all(isinstance(c, bytes) for c in chunks)

    def test_generate_archive_memory_error_raised(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        user_dict = {"id": 1, "username": "test"}

        with (
            patch.object(service, "collect_user_activities_data", side_effect=MemoryAllocationError("oom")),
            pytest.raises(MemoryAllocationError),
        ):
            list(service.generate_export_archive(user_dict))


class TestExportPerformanceConfigEdgeCases:
    """Cover custom tier edge cases in ExportPerformanceConfig."""

    def test_unknown_tier_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: ("ultra", 9999),
        )
        config = profile_export_service.ExportPerformanceConfig.get_auto_config()
        assert config.batch_size == 125  # default, not from tier configs

    def test_get_auto_config_exception_falls_back(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: (_ for _ in ()).throw(Exception("detection failed")),
        )
        config = profile_export_service.ExportPerformanceConfig.get_auto_config()
        assert config.batch_size == 125


class TestExportServiceCollectUserActivitiesEdgeCases:
    """Cover lines 218-219, 225-236."""

    def test_no_valid_activity_ids(self) -> None:
        """Activities collected but all have None IDs (lines 218-219)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            activity = MagicMock()
            activity.id = None

            with (
                patch.object(service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
            ):
                result = service.collect_user_activities_data(z)

        assert len(result) == 1

    def test_exercise_titles_collected_successfully(self) -> None:
        """Exercise titles collected and written (lines 228-234)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            activity = _make_activity_mock(1)

            with (
                patch.object(service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
                patch(
                    "modules.users.users_profile.export_service.activities_integration.list_exercise_titles",
                    return_value=[MagicMock(), MagicMock()],
                ),
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"title": "t"}),
            ):
                service.collect_user_activities_data(z)

    def test_exercise_titles_collection_exception_raises(self) -> None:
        """Exception during exercise titles raises DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            activity = _make_activity_mock(1)

            with (
                patch.object(service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(service, "_collect_and_write_activity_components"),
                patch(
                    "modules.users.users_profile.export_service.activities_integration.list_exercise_titles",
                    side_effect=Exception("boom"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_activities_data(z)


class TestExportServiceCollectActivityComponents:
    """Cover lines 306-356 (_collect_and_write_activity_components)."""

    def test_components_loop_calls_chunked_and_simple(self) -> None:
        """Both splittable and non-splittable component paths executed."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            activity_ids = [1]
            user_activities = [_make_activity_mock(1)]

            with (
                patch.object(service, "_collect_and_write_component_chunked") as mock_chunked,
                patch.object(service, "_collect_and_write_component_simple") as mock_simple,
                patch.object(profile_utils, "write_json_to_zip"),
            ):
                service._collect_and_write_activity_components(z, activity_ids, user_activities)

            assert mock_chunked.call_count == 3
            assert mock_simple.call_count == 2


class TestExportServiceCollectComponentChunkedDetailed:
    """Cover lines 388-472 of _collect_and_write_component_chunked."""

    def _make_service(self, batch_size: int = 4) -> tuple:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.batch_size = batch_size
        service.performance_config.enable_memory_monitoring = False
        return service

    def test_chunked_single_batch_all_written_at_once(self) -> None:
        """Single batch fits in one write; file_counter==0 path (lines 444-450)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=10)

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: [MagicMock()] * len(ids) if ids else [],
                    [1, 2],
                    [_make_activity_mock(1), _make_activity_mock(2)],
                    5,
                )

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[1] == "data/activity_laps.json"

    def test_chunked_multiple_chunks_written(self) -> None:
        """Buffer exceeds max_items_per_file, multiple chunk files (lines 413-428)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=10)

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: [MagicMock()] * (len(ids) + 1) if ids else [],
                    [1, 2],
                    [_make_activity_mock(1), _make_activity_mock(2)],
                    2,
                )

            assert mock_write.call_count >= 2

    def test_chunked_remaining_buffer_written(self) -> None:
        """Remaining items at end written with numbered filename (lines 451-462)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=4)

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: [MagicMock()] * len(ids) if ids else [],
                    [1, 2, 3],
                    [_make_activity_mock(1), _make_activity_mock(2), _make_activity_mock(3)],
                    2,
                )

            assert mock_write.call_count == 2

    def test_chunked_empty_result_writes_empty_file(self) -> None:
        """No items collected -> empty file written (lines 464-469)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=10)

            with (
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: [],
                    [1, 2],
                    [_make_activity_mock(1), _make_activity_mock(2)],
                    5,
                )

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[1] == "data/activity_laps.json"
            assert args[2] == []

    def test_chunked_crud_exception_raises_data_collection_error(self) -> None:
        """CRUD exception raises DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=10)

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip"),
                pytest.raises(DataCollectionError),
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: (_ for _ in ()).throw(Exception("fail")),
                    [1, 2, 3],
                    [_make_activity_mock(1), _make_activity_mock(2), _make_activity_mock(3)],
                    2,
                )

    def test_chunked_memory_error_propagates(self) -> None:
        """MemoryAllocationError from check_memory_usage propagates."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = self._make_service(batch_size=10)

            with (
                patch.object(
                    profile_utils,
                    "check_memory_usage",
                    side_effect=MemoryAllocationError("oom"),
                ),
                pytest.raises(MemoryAllocationError),
            ):
                service._collect_and_write_component_chunked(
                    z,
                    "laps",
                    "data/activity_laps.json",
                    lambda ids, uid, db, acts: [],
                    [1, 2],
                    [_make_activity_mock(1), _make_activity_mock(2)],
                    5,
                )


class TestExportServiceCollectComponentSimpleDetailed:
    """Cover lines 499-542 of _collect_and_write_component_simple."""

    def test_simple_with_data(self) -> None:
        """Component data collected and written (lines 529-537)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            mock_crud = MagicMock(return_value=[MagicMock(), MagicMock()])
            captured = []

            def capture_write(zipf, filename, data, counts):
                captured[:] = data

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip", side_effect=capture_write) as mock_write,
            ):
                service._collect_and_write_component_simple(
                    z,
                    "steps",
                    "data/activity_workout_steps.json",
                    mock_crud,
                    [1],
                    [_make_activity_mock(1)],
                    5,
                )

            mock_crud.assert_called_once()
            mock_write.assert_called_once()
            assert len(captured) == 2

    def test_simple_crud_exception_raises_data_collection_error(self) -> None:
        """CRUD exception raises DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 2
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(profile_utils, "sqlalchemy_obj_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip"),
                pytest.raises(DataCollectionError),
            ):
                service._collect_and_write_component_simple(
                    z,
                    "steps",
                    "data/activity_workout_steps.json",
                    lambda ids, uid, db, acts: (_ for _ in ()).throw(Exception("fail")),
                    [1, 2, 3],
                    [_make_activity_mock(1), _make_activity_mock(2), _make_activity_mock(3)],
                    2,
                )

    def test_simple_memory_error_propagates(self) -> None:
        """MemoryAllocationError from check_memory_usage propagates."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(
                    profile_utils,
                    "check_memory_usage",
                    side_effect=MemoryAllocationError("oom"),
                ),
                pytest.raises(MemoryAllocationError),
            ):
                service._collect_and_write_component_simple(
                    z,
                    "steps",
                    "data/activity_workout_steps.json",
                    lambda ids, uid, db, acts: [],
                    [1],
                    [_make_activity_mock(1)],
                    5,
                )

    def test_simple_empty_result_writes_empty_file(self) -> None:
        """No data collected -> empty file written (lines 539-544)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.batch_size = 10
            service.performance_config.enable_memory_monitoring = False

            with (
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                service._collect_and_write_component_simple(
                    z,
                    "steps",
                    "data/activity_workout_steps.json",
                    lambda ids, uid, db, acts: [],
                    [1],
                    [_make_activity_mock(1)],
                    5,
                )

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[2] == []


class TestExportServiceDbErrorWrapsDataCollectionError:
    def test_gear_db_error_wraps_as_data_collection_error(self) -> None:
        with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = profile_export_service.ExportService(user_id=1, db=MagicMock(spec=Session))
            service.performance_config.enable_memory_monitoring = False
            with (
                patch(
                    "modules.users.users_profile.export_service.gear_crud.get_gear_user",
                    side_effect=SQLAlchemyError("db down"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_gear_data(z)

    def test_health_weight_db_error_wraps_as_data_collection_error(self) -> None:
        with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = profile_export_service.ExportService(user_id=1, db=MagicMock(spec=Session))
            service.performance_config.enable_memory_monitoring = False
            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_crud.get_all_health_weight_by_user_id",
                    side_effect=SQLAlchemyError("db down"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_health_weight(z)


class TestExportServiceCollectUserSettingsEdgeCases:
    """Cover exception handlers in collect_user_settings_data."""

    def test_settings_inner_crud_exception_raises_data_collection_error(self) -> None:
        """Settings CRUD exception raises DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    side_effect=Exception("gear fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.user_goals_crud.get_user_goals_by_user_id",
                    side_effect=Exception("goals fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_crud.get_user_integrations_by_user_id",
                    side_effect=Exception("integrations fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_crud.get_user_privacy_settings_by_user_id",
                    side_effect=Exception("privacy fail"),
                ),
                patch.object(profile_utils, "write_json_to_zip"),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_settings_data(z)

    def test_settings_db_error_wraps_as_data_collection_error(self) -> None:
        """Settings CRUD exception wraps as DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                    side_effect=SQLAlchemyError("db down"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_settings_data(z)


class TestExportServiceActivityFilesEdgeCases:
    """Cover the storage-backed add_activity_files_to_zip edge cases."""

    def test_activity_without_stored_file_skipped(self) -> None:
        """An activity with no retained source file is skipped (get returns None)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch(
                "modules.users.users_profile.export_service.activity_file_storage_service.get_activity_file",
                return_value=None,
            ):
                service.add_activity_files_to_zip(z, [_make_activity_mock(1)])

        assert service.counts.get("activity_files", 0) == 0

    def test_read_error_continues(self) -> None:
        """An OSError reading one activity's file is caught and the loop continues."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch(
                "modules.users.users_profile.export_service.activity_file_storage_service.get_activity_file",
                side_effect=[OSError("read failed"), ("2.gpx", b"<gpx></gpx>")],
            ):
                service.add_activity_files_to_zip(z, [_make_activity_mock(1), _make_activity_mock(2)])

        # The first activity errored and was skipped; the second still exported.
        assert service.counts["activity_files"] == 1
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert "activity_files/2.gpx" in z.namelist()


class TestExportServiceActivityMediaEdgeCases:
    """Failure handling while reading media blobs out of storage."""

    def test_a_failing_blob_does_not_abort_the_rest(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch("modules.users.users_profile.export_service.platform_runtime") as runtime:
                storage = runtime.get_active_platform.return_value.storage
                storage.list_keys.return_value = ["1_bad.jpg", "1_good.jpg"]
                storage.get.side_effect = [OSError("backend down"), b"good-bytes"]
                service.add_activity_media_to_zip(z, [_make_activity_mock(1)])

        assert service.counts.get("media", 0) == 1

    def test_media_listing_failure_does_not_abort_the_export(self) -> None:
        """A storage outage skips that activity's media rather than failing the export."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, db=mock_db)

            with patch("modules.users.users_profile.export_service.platform_runtime") as runtime:
                storage = runtime.get_active_platform.return_value.storage
                storage.list_keys.side_effect = OSError("permission denied")
                service.add_activity_media_to_zip(z, [_make_activity_mock(1)])

        assert service.counts.get("media", 0) == 0


class _MockNamedTempFile:
    """Mock for NamedTemporaryFile used in streaming tests."""

    def __init__(self, raise_on_read: bool = False) -> None:
        self.buf = io.BytesIO()
        self._raise_on_read = raise_on_read
        self._read_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def write(self, data: bytes) -> int:
        return self.buf.write(data)

    def fileno(self) -> int:
        return 12345

    def tell(self) -> int:
        return self.buf.tell()

    def seek(self, pos: int) -> int:
        return self.buf.seek(pos)

    def read(self, size: int = -1) -> bytes:
        self._read_calls += 1
        if self._raise_on_read and self._read_calls > 1:
            raise MemoryError("simulated OOM")
        return self.buf.read(size)

    def flush(self) -> None:
        pass


class TestExportServiceGenerateExportArchiveEdgeCases:
    """Cover error handling lines 1076-1124 of generate_export_archive."""

    def test_bad_zip_file_raises_zip_creation_error(self) -> None:
        """BadZipFile during ZIP creation raises ZipCreationError (lines 1076-1077)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False

        with (
            patch(
                "modules.users.users_profile.export_service.zipfile.ZipFile",
                side_effect=zipfile.BadZipFile("corrupt"),
            ),
            pytest.raises(ZipCreationError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_large_zip_file_raises_zip_creation_error(self) -> None:
        """LargeZipFile during ZIP creation raises ZipCreationError (lines 1079-1080)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False

        with (
            patch(
                "modules.users.users_profile.export_service.zipfile.ZipFile",
                side_effect=zipfile.LargeZipFile("too large"),
            ),
            pytest.raises(ZipCreationError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_exception_re_raised(self) -> None:
        """Non-specific exception from collection re-raised (lines 1083-1084)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(
                service,
                "collect_user_activities_data",
                side_effect=DataCollectionError("collect failed"),
            ),
            pytest.raises(DataCollectionError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_export_timeout_re_raised(self) -> None:
        """ExportTimeoutError re-raised through inner except Exception (lines 1083-1084)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(
                profile_utils,
                "check_timeout",
                side_effect=ExportTimeoutError("timed out"),
            ),
            patch.object(service, "collect_user_activities_data", return_value=[]),
            patch.object(service, "collect_gear_data"),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(service, "add_activity_files_to_zip"),
            patch.object(service, "add_activity_media_to_zip"),
            patch.object(service, "add_user_images_to_zip"),
            pytest.raises(ExportTimeoutError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_memory_error_during_streaming(self) -> None:
        """MemoryError from tmp.read raises MemoryAllocationError (lines 1109-1111)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        tmp_mock = _MockNamedTempFile(raise_on_read=True)

        with (
            patch("tempfile.NamedTemporaryFile", return_value=tmp_mock),
            patch("os.fsync"),
            patch.object(service, "collect_user_activities_data", return_value=[]),
            patch.object(service, "collect_gear_data"),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(service, "add_activity_files_to_zip"),
            patch.object(service, "add_activity_media_to_zip"),
            patch.object(service, "add_user_images_to_zip"),
            pytest.raises(MemoryAllocationError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_outer_os_error_raises_file_system_error(self) -> None:
        """OSError in outer try block raises FileSystemError (lines 1119-1121)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch("os.fsync", side_effect=OSError("fsync failed")),
            patch.object(service, "collect_user_activities_data", return_value=[]),
            patch.object(service, "collect_gear_data"),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(service, "add_activity_files_to_zip"),
            patch.object(service, "add_activity_media_to_zip"),
            patch.object(service, "add_user_images_to_zip"),
            pytest.raises(FileSystemError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))

    def test_outer_memory_error_raises_memory_allocation_error(self) -> None:
        """MemoryError in outer try block raises MemoryAllocationError (lines 1122-1124)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch("os.fsync", side_effect=MemoryError("OOM")),
            patch.object(service, "collect_user_activities_data", return_value=[]),
            patch.object(service, "collect_gear_data"),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(service, "add_activity_files_to_zip"),
            patch.object(service, "add_activity_media_to_zip"),
            patch.object(service, "add_user_images_to_zip"),
            pytest.raises(MemoryAllocationError),
        ):
            list(service.generate_export_archive({"id": 1}, timeout_seconds=60))
