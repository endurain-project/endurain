"""Tests for profile data export service."""

import contextlib
import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import modules.users.contributor_registry as users_contributor_registry
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.export_activity_service as export_activity_service
import modules.users.users_profile.export_media_service as export_media_service
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


@contextlib.contextmanager
def _storage_of(service):
    """Expose a service's storage provider the way the old runtime patch did."""
    runtime = MagicMock()
    runtime.get_active_platform.return_value.storage = service.storage
    yield runtime


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


class _Record(BaseModel):
    """A stored record as a lister returns it."""

    id: int
    user_id: int
    version: int


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

    def test_each_limit_is_kept_as_given(self) -> None:
        config = profile_export_service.ExportPerformanceConfig(timeout_seconds=7200, enable_memory_monitoring=False)

        assert (config.timeout_seconds, config.enable_memory_monitoring, config.chunk_size) == (7200, False, 8192)

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
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        assert service.user_id == 1
        assert service.db is mock_db
        assert "activities" in service.counts

    def test_init_with_custom_config(self) -> None:
        mock_db = MagicMock(spec=Session)
        config = profile_export_service.ExportPerformanceConfig(batch_size=10)
        service = profile_export_service.ExportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
            performance_config=config,
        )
        assert service.performance_config.batch_size == 10


def _service(batch_size: int = 10) -> profile_export_service.ExportService:
    service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
    service.performance_config.batch_size = batch_size
    service.performance_config.enable_memory_monitoring = False
    return service


def _read_json(buf: io.BytesIO, name: str):
    buf.seek(0)
    with zipfile.ZipFile(buf) as archive:
        return json.loads(archive.read(name))


class _GearRecord(BaseModel):
    """A stored record as a section's export returns it."""

    id: int


def _records_section(key: str = "gears", export=None) -> users_profile_contracts.ProfileRecordsSection:
    return users_profile_contracts.ProfileRecordsSection(
        key=key, export=export or (lambda user_id, db: []), restore=lambda records, user_id, ids, db: 0
    )


@pytest.fixture
def sections():
    users_contributor_registry.clear()
    yield users_contributor_registry
    users_contributor_registry.clear()


def _collect(service, timeout_calls=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        writer = profile_utils.ZipArchiveWriter(z, service.counts)
        files = service.collect_profile_sections(
            writer, (lambda: timeout_calls.append(1)) if timeout_calls is not None else lambda: None
        )
    return buf, files


class TestExportServiceCollectProfileSections:
    def _service(self):
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        return service

    def test_a_records_section_writes_its_entry_and_counts_it(self, sections) -> None:
        sections.register_profile_section(
            _records_section("gears", lambda user_id, db: [_GearRecord(id=1), _GearRecord(id=2)])
        )
        service = self._service()

        buf, files = _collect(service)

        assert _read_json(buf, "data/gears.json") == [{"id": 1}, {"id": 2}]
        assert service.counts["gears"] == 2
        assert files == []

    def test_an_empty_section_still_writes_its_entry_and_count(self, sections) -> None:
        sections.register_profile_section(_records_section("gear_components"))
        service = self._service()

        buf, _ = _collect(service)

        assert _read_json(buf, "data/gear_components.json") == []
        assert service.counts["gear_components"] == 0

    def test_sections_run_in_registration_order_after_a_timeout_check_each(self, sections) -> None:
        order: list[str] = []
        for key in ("b", "a", "c"):
            sections.register_profile_section(
                _records_section(key, lambda user_id, db, key=key: order.append(key) or [])
            )
        timeout_calls: list[int] = []

        _collect(self._service(), timeout_calls)

        assert order == ["b", "a", "c"]
        assert len(timeout_calls) == 3

    def test_an_archive_section_gets_the_context_and_its_files_are_returned(self, sections) -> None:
        seen = []
        after_commit = MagicMock()

        def export(context: users_profile_contracts.ProfileExportContext):
            seen.append(context)
            context.archive.write_json("data/extra.json", [_GearRecord(id=7)])
            return after_commit

        sections.register_profile_section(
            users_profile_contracts.ProfileArchiveSection(key="extra", export=export, restore=lambda context: None)
        )
        service = self._service()

        _, files = _collect(service)

        assert files == [after_commit]
        assert seen[0].user_id == 1
        assert seen[0].counts is service.counts
        assert seen[0].batch_size == service.performance_config.batch_size
        assert service.counts["extra"] == 1
        after_commit.assert_not_called()

    def test_an_unexpected_error_becomes_a_data_collection_error_naming_the_section(self, sections) -> None:
        sections.register_profile_section(_records_section("gears", MagicMock(side_effect=Exception("unexpected"))))

        with pytest.raises(DataCollectionError, match="Failed to collect gears: unexpected"):
            _collect(self._service())

    def test_a_database_error_becomes_a_database_connection_error(self, sections) -> None:
        sections.register_profile_section(_records_section("gears", MagicMock(side_effect=SQLAlchemyError("db down"))))

        with pytest.raises(DatabaseConnectionError):
            _collect(self._service())

    @pytest.mark.parametrize("error", [MemoryAllocationError("memory"), ExportTimeoutError("late"), OSError("disk")])
    def test_memory_timeout_and_file_errors_pass_through(self, sections, error) -> None:
        sections.register_profile_section(_records_section("gears", MagicMock(side_effect=error)))

        with pytest.raises(type(error)):
            _collect(self._service())

    def test_an_archive_section_error_is_wrapped_too(self, sections) -> None:
        sections.register_profile_section(
            users_profile_contracts.ProfileArchiveSection(
                key="extra", export=MagicMock(side_effect=SQLAlchemyError("db down")), restore=lambda context: None
            )
        )

        with pytest.raises(DatabaseConnectionError):
            _collect(self._service())

    def test_no_registered_section_is_an_error(self, sections) -> None:
        with pytest.raises(RuntimeError, match="configure_user_contributors"):
            _collect(self._service())


class TestExportServiceCollectHealthWeight:
    def test_collect_health_weight_with_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False
            mock_health = [MagicMock(), MagicMock()]

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_integration.list_health_weight",
                    return_value=mock_health,
                ),
                patch(
                    "modules.users.users_profile.export_service.health_targets_integration.get_health_targets",
                    return_value=MagicMock(),
                ),
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
            ):
                service.collect_health_weight(z)

        assert service.counts.get("health_weight", 0) >= 2

    def test_collect_health_weight_crud_exception_raises_data_collection_error(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_integration.list_health_weight",
                    side_effect=Exception("unexpected"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_health_weight(z)

    def test_collect_health_weight_no_data(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_integration.list_health_weight",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.health_targets_integration.get_health_targets",
                    return_value=None,
                ),
            ):
                service.collect_health_weight(z)


class TestExportServiceCollectHealthRecords:
    _NAMES = ("health_sleep", "health_steps", "health_water", "health_fasting", "health_poop")

    def _service(self) -> profile_export_service.ExportService:
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        return service

    def _listers(self, rows: dict[str, list] | None = None, failure: Exception | None = None):
        def lister(name: str):
            if failure is not None:
                return MagicMock(side_effect=failure)
            return MagicMock(return_value=(rows or {}).get(name, []))

        return patch.dict(profile_export_service._HEALTH_RECORD_LISTERS, {name: lister(name) for name in self._NAMES})

    def test_writes_every_record_kind_to_its_own_file(self) -> None:
        buf = io.BytesIO()
        service = self._service()
        rows = {name: [_Record(id=1, user_id=1, version=1)] for name in self._NAMES}

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, self._listers(rows):
            service.collect_health_records(z)

        with zipfile.ZipFile(buf) as z:
            for name in self._NAMES:
                assert json.loads(z.read(f"data/{name}.json")) == [{"id": 1, "user_id": 1, "version": 1}]
        assert all(service.counts[name] == 1 for name in self._NAMES)

    def test_a_kind_without_records_still_gets_an_empty_file(self) -> None:
        buf = io.BytesIO()
        service = self._service()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, self._listers():
            service.collect_health_records(z)

        with zipfile.ZipFile(buf) as z:
            assert all(json.loads(z.read(f"data/{name}.json")) == [] for name in self._NAMES)

    def test_a_failing_read_raises_data_collection_error(self) -> None:
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z,
            self._listers(failure=Exception("boom")),
            pytest.raises(DataCollectionError),
        ):
            self._service().collect_health_records(z)

    def test_a_database_error_raises_database_connection_error(self) -> None:
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z,
            self._listers(failure=SQLAlchemyError("db")),
            pytest.raises(DatabaseConnectionError),
        ):
            self._service().collect_health_records(z)


class TestExportServiceCollectUserSettings:
    def test_collect_settings_all_empty(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_goals_integration.list_goals",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_integration.get_user_integrations",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_integration.get_privacy_settings",
                    return_value=None,
                ),
            ):
                service.collect_user_settings_data(z)

    def test_collect_settings_all_present(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    return_value=MagicMock(),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_goals_integration.list_goals",
                    return_value=[MagicMock()],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_integration.get_user_integrations",
                    return_value=MagicMock(),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_integration.get_privacy_settings",
                    return_value=MagicMock(),
                ),
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
            ):
                service.collect_user_settings_data(z)

        assert service.counts.get("user_default_gear", 0) >= 1
        assert service.counts.get("user_goals", 0) >= 1

    def test_identity_providers_not_in_export_zip(self) -> None:
        """Verify identity-link data is never written to the export ZIP (security boundary)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_goals_integration.list_goals",
                    return_value=[],
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_integration.get_user_integrations",
                    return_value=None,
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_integration.get_privacy_settings",
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
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    side_effect=Exception("fail"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_settings_data(z)


class TestExportServiceGenerateExportArchive:
    def test_generate_archive_streams_bytes(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        user_dict = {"id": 1, "username": "test"}

        with (
            patch.object(
                export_activity_service,
                "collect_user_activities_data",
                return_value=[_make_activity_mock(1)],
            ),
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(export_media_service, "add_activity_files_to_zip"),
            patch.object(export_media_service, "add_activity_media_to_zip"),
            patch.object(export_media_service, "add_user_images_to_zip"),
        ):
            archive = service.build_export_archive(user_dict, timeout_seconds=60)

        assert archive.read(4) == b"PK\x03\x04"
        archive.close()

    def test_generate_archive_memory_error_raised(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        user_dict = {"id": 1, "username": "test"}

        with (
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(
                export_activity_service, "collect_user_activities_data", side_effect=MemoryAllocationError("oom")
            ),
            pytest.raises(MemoryAllocationError),
        ):
            service.build_export_archive(user_dict)


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

    def test_get_auto_config_detection_failure_propagates(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: (_ for _ in ()).throw(RuntimeError("detection failed")),
        )
        with pytest.raises(RuntimeError, match="detection failed"):
            profile_export_service.ExportPerformanceConfig.get_auto_config()


class TestExportServiceDbErrorWrapsDataCollectionError:
    def test_health_weight_db_error_wraps_as_data_collection_error(self) -> None:
        with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
            service.performance_config.enable_memory_monitoring = False
            with (
                patch(
                    "modules.users.users_profile.export_service.health_weight_integration.list_health_weight",
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
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    side_effect=Exception("gear fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_goals_integration.list_goals",
                    side_effect=Exception("goals fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.user_integrations_integration.get_user_integrations",
                    side_effect=Exception("integrations fail"),
                ),
                patch(
                    "modules.users.users_profile.export_service.users_privacy_settings_integration.get_privacy_settings",
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
            service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
            service.performance_config.enable_memory_monitoring = False

            with (
                patch(
                    "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                    side_effect=SQLAlchemyError("db down"),
                ),
                pytest.raises(DataCollectionError),
            ):
                service.collect_user_settings_data(z)


class TestExportServiceGenerateExportArchiveEdgeCases:
    """Cover error handling of build_export_archive."""

    def test_bad_zip_file_raises_zip_creation_error(self) -> None:
        """BadZipFile during ZIP creation raises ZipCreationError (lines 1076-1077)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False

        with (
            patch(
                "modules.users.users_profile.export_service.zipfile.ZipFile",
                side_effect=zipfile.BadZipFile("corrupt"),
            ),
            pytest.raises(ZipCreationError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)

    def test_large_zip_file_raises_zip_creation_error(self) -> None:
        """LargeZipFile during ZIP creation raises ZipCreationError (lines 1079-1080)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False

        with (
            patch(
                "modules.users.users_profile.export_service.zipfile.ZipFile",
                side_effect=zipfile.LargeZipFile("too large"),
            ),
            pytest.raises(ZipCreationError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)

    def test_exception_re_raised(self) -> None:
        """Non-specific exception from collection re-raised (lines 1083-1084)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(
                export_activity_service,
                "collect_user_activities_data",
                side_effect=DataCollectionError("collect failed"),
            ),
            pytest.raises(DataCollectionError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)

    def test_export_timeout_re_raised(self) -> None:
        """ExportTimeoutError re-raised through inner except Exception (lines 1083-1084)."""
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(
                profile_utils,
                "check_timeout",
                side_effect=ExportTimeoutError("timed out"),
            ),
            patch.object(export_activity_service, "collect_user_activities_data", return_value=[]),
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(service, "collect_health_weight"),
            patch.object(service, "collect_user_settings_data"),
            patch.object(export_media_service, "add_activity_files_to_zip"),
            patch.object(export_media_service, "add_activity_media_to_zip"),
            patch.object(export_media_service, "add_user_images_to_zip"),
            pytest.raises(ExportTimeoutError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)

    def test_an_os_error_while_writing_raises_file_system_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(export_activity_service, "collect_user_activities_data", side_effect=OSError("disk full")),
            pytest.raises(FileSystemError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)

    def test_a_memory_error_while_writing_raises_memory_allocation_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.compression_level = 0

        with (
            patch.object(service, "collect_profile_sections", return_value=[]),
            patch.object(export_activity_service, "collect_user_activities_data", side_effect=MemoryError("OOM")),
            pytest.raises(MemoryAllocationError),
        ):
            service.build_export_archive({"id": 1}, timeout_seconds=60)


def test_export_writes_only_the_sync_preferences_of_the_integrations() -> None:
    integrations = MagicMock(
        strava_sync_gear=True,
        garminconnect_sync_gear=False,
        strava_token="enc-token",
        strava_client_secret="enc-secret",
        garminconnect_token={"di_token": "enc"},
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        with (
            patch(
                "modules.users.users_profile.export_service.users_default_gear_integration.get_default_gear",
                return_value=None,
            ),
            patch("modules.users.users_profile.export_service.users_goals_integration.list_goals", return_value=[]),
            patch(
                "modules.users.users_profile.export_service.user_integrations_integration.get_user_integrations",
                return_value=integrations,
            ),
            patch(
                "modules.users.users_profile.export_service.users_privacy_settings_integration.get_privacy_settings",
                return_value=None,
            ),
        ):
            service.collect_user_settings_data(z)

    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        exported = json.loads(z.read("data/user_integrations.json"))

    assert exported == [{"strava_sync_gear": True, "garminconnect_sync_gear": False}]


def test_the_database_phase_ends_before_the_storage_phase() -> None:
    mock_db = MagicMock(spec=Session)
    service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=mock_db)
    service.performance_config.enable_memory_monitoring = False
    order = MagicMock()
    order.attach_mock(mock_db.commit, "commit")

    with (
        patch.object(export_activity_service, "collect_user_activities_data", return_value=[]),
        patch.object(service, "collect_profile_sections", return_value=[]),
        patch.object(service, "collect_health_weight"),
        patch.object(service, "collect_user_settings_data") as settings,
        patch.object(export_media_service, "add_activity_files_to_zip") as files,
        patch.object(export_media_service, "add_activity_media_to_zip"),
        patch.object(export_media_service, "add_user_images_to_zip"),
    ):
        order.attach_mock(settings, "last_db_read")
        order.attach_mock(files, "first_storage_read")
        service.build_export_archive({"id": 1}).close()

    assert [call[0] for call in order.mock_calls] == ["last_db_read", "commit", "first_storage_read"]


def test_a_failed_build_leaves_no_archive_open() -> None:
    service = profile_export_service.ExportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
    service.performance_config.enable_memory_monitoring = False
    opened = []
    real = profile_export_service.tempfile.TemporaryFile

    def tracking(*args, **kwargs):
        handle = real(*args, **kwargs)
        opened.append(handle)
        return handle

    with (
        patch.object(service, "collect_profile_sections", return_value=[]),
        patch("modules.users.users_profile.export_service.tempfile.TemporaryFile", side_effect=tracking),
        patch.object(export_activity_service, "collect_user_activities_data", side_effect=DataCollectionError("boom")),
        pytest.raises(DataCollectionError),
    ):
        service.build_export_archive({"id": 1})

    assert opened and all(handle.closed for handle in opened)
