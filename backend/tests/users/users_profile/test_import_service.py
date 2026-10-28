"""Tests for profile data import service."""

import contextlib
import json
import zipfile
from io import BytesIO
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_water.schema as health_water_schema
import modules.users.users_profile.import_service as profile_import_service
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    JSONParseError,
    MemoryAllocationError,
)


@contextlib.contextmanager
def _storage_of(service):
    """Expose a service's storage provider the way the old runtime patch did."""
    runtime = MagicMock()
    runtime.get_active_platform.return_value.storage = service.storage
    yield runtime


class TestImportPerformanceConfig:
    def test_tier_configs(self) -> None:
        configs = profile_import_service.ImportPerformanceConfig._get_tier_configs()
        assert "high" in configs
        assert "medium" in configs
        assert "low" in configs

    def test_init_defaults(self) -> None:
        config = profile_import_service.ImportPerformanceConfig()
        assert config.batch_size == 125
        assert config.max_memory_mb == 1024
        assert config.max_file_size_mb == 500
        assert config.max_json_mb == 128

    def test_get_auto_config(self, monkeypatch) -> None:
        monkeypatch.setattr(
            profile_utils,
            "detect_system_memory_tier",
            lambda: ("low", 512),
        )
        config = profile_import_service.ImportPerformanceConfig.get_auto_config()
        assert config.batch_size == 50


class TestImportServiceInit:
    def test_init_creates_service(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=mock_db)
        assert service.user_id == 1
        assert service.db is mock_db

    def test_init_with_custom_config(self) -> None:
        mock_db = MagicMock(spec=Session)
        config = profile_import_service.ImportPerformanceConfig(batch_size=10)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
            performance_config=config,
        )
        assert service.performance_config.batch_size == 10


def _make_zip_with_json(files: dict[str, object]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, json.dumps(data))
    return buf.getvalue()


class TestImportServiceZipValidation:
    async def test_file_size_exceeds_limit(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.max_file_size_mb = 0.001

        with pytest.raises(FileSizeError, match="exceeds maximum"):
            await service.import_from_zip_data(b"x" * 2000)

    async def test_bad_zip_format(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.max_file_size_mb = 100

        with pytest.raises(FileFormatError, match="Invalid ZIP"):
            await service.import_from_zip_data(b"not-a-zip")


class TestImportServiceArchiveCaps:
    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    async def test_an_archive_with_too_many_entries_is_refused_before_anything_is_read(self) -> None:
        service = self._service()
        service.performance_config.max_entries = 2
        zip_data = _make_zip_with_json({f"data/f{i}.json": [] for i in range(3)})

        with pytest.raises(FileSizeError, match="entries"):
            await service.import_from_zip_data(zip_data)

    def test_the_bytes_read_across_entries_are_capped(self) -> None:
        service = self._service()
        service.performance_config.max_uncompressed_mb = 0.0001
        zip_data = _make_zip_with_json({"data/a.json": ["x" * 60], "data/b.json": ["y" * 60]})

        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            service._read_zip_entry(z, "data/a.json")
            with pytest.raises(FileSizeError, match="uncompressed"):
                service._read_zip_entry(z, "data/b.json")


class TestImportedRowsLoseTheirIdentity:
    """An archive's rows carry the exporting account's id, owner and version, which an import must not write."""

    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    async def test_a_goal_exported_with_its_version_is_still_imported(self) -> None:
        service = self._service()
        row = {
            "id": 9,
            "user_id": 3,
            "version": 4,
            "interval": "weekly",
            "activity_type": "run",
            "goal_type": "calories",
            "goal_calories": 5000,
        }

        with patch.object(profile_import_service.users_goals_integration, "create_goal") as create:
            await service.collect_and_import_user_goals([row])

        create.assert_called_once()
        assert service.counts["user_goals"] == 1

    async def test_privacy_settings_exported_with_their_version_are_still_imported(self) -> None:
        service = self._service()
        row = {"id": 9, "user_id": 3, "version": 4, "hide_activity_map": True}

        with patch.object(profile_import_service.users_privacy_settings_integration, "edit_privacy_settings") as edit:
            await service.collect_and_import_user_privacy_settings([row])

        edit.assert_called_once()
        assert service.counts["user_privacy_settings"] == 1


class TestImportServiceReadZipEntry:
    def test_read_zip_entry_exceeds_size(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json({"data/activities.json": [{"id": 1}]})
        with zipfile.ZipFile(BytesIO(zip_data)) as z, pytest.raises(FileSizeError):
            service._read_zip_entry(z, "data/activities.json", max_bytes=1)


class TestImportServiceLoadSingleJson:
    def test_load_single_json_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({"data/gears.json": [{"id": 1}]})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/gears.json")

        assert result == [{"id": 1}]

    def test_load_single_json_not_found(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/nonexistent.json")

        assert result == []

    def test_load_single_json_invalid_json(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data/bad.json", "not-json")

        with zipfile.ZipFile(BytesIO(buf.getvalue())) as z, pytest.raises(JSONParseError):
            service._load_single_json(z, "data/bad.json")

    def test_load_single_json_type_guard_non_list_returns_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        for non_list_data in (None, {}, "string", 42):
            zip_data = _make_zip_with_json({"data/test.json": non_list_data})
            with zipfile.ZipFile(BytesIO(zip_data)) as z:
                result = service._load_single_json(z, "data/test.json")
            assert result == [], f"Expected [] for {type(non_list_data).__name__}"

    def test_load_single_json_missing_file_returns_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json({"other.json": []})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/missing.json")

        assert result == []


class TestImportServiceGetSplitFiles:
    def test_get_split_files_list_returns_sorted(self) -> None:
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=MagicMock(spec=Session),
        )
        file_list = {
            "data/activity_laps_000.json",
            "data/activity_laps_001.json",
            "data/activity_laps.json",
            "data/other.json",
        }
        result = service._get_split_files_list(file_list, "data/activity_laps")
        assert result == ["data/activity_laps_000.json", "data/activity_laps_001.json"]

    def test_get_split_files_list_falls_back_to_single(self) -> None:
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=MagicMock(spec=Session),
        )
        file_list = {"data/activity_laps.json", "data/other.json"}
        result = service._get_split_files_list(file_list, "data/activity_laps")
        assert result == ["data/activity_laps.json"]

    def test_get_split_files_list_empty(self) -> None:
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=MagicMock(spec=Session),
        )
        result = service._get_split_files_list(set(), "data/activity_laps")
        assert result == []


class TestImportServiceGears:
    async def test_collect_and_import_gears(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        mock_new_gear = MagicMock()
        mock_new_gear.id = 10

        with (
            patch(
                "modules.users.users_profile.import_service.gear_integration.get_gear_user_by_nickname",
                return_value=None,
            ),
            patch(
                "modules.users.users_profile.import_service.gear_integration.create_gear",
                return_value=mock_new_gear,
            ),
        ):
            mapping = await service.collect_and_import_gears_data([{"id": 5, "nickname": "Garmin", "gear_type": 1}])

        assert mapping == {5: 10}

    async def test_import_maps_onto_a_gear_with_the_same_nickname(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        existing = MagicMock()
        existing.id = 77

        with (
            patch(
                "modules.users.users_profile.import_service.gear_integration.get_gear_user_by_nickname",
                return_value=existing,
            ),
            patch("modules.users.users_profile.import_service.gear_integration.create_gear") as mock_create,
        ):
            mapping = await service.collect_and_import_gears_data([{"id": 5, "nickname": "Garmin", "gear_type": 1}])

        assert mapping == {5: 77}
        mock_create.assert_not_called()

    async def test_import_drops_provider_ids_that_are_taken(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        created = MagicMock()
        created.id = 10

        with (
            patch(
                "modules.users.users_profile.import_service.gear_integration.get_gear_user_by_nickname",
                return_value=None,
            ),
            patch(
                "modules.users.users_profile.import_service.gear_integration.create_gear",
                side_effect=[core_exceptions.ConflictError("taken"), created],
            ) as mock_create,
        ):
            mapping = await service.collect_and_import_gears_data(
                [{"id": 5, "nickname": "Garmin", "gear_type": 1, "strava_gear_id": "b1"}]
            )

        assert mapping == {5: 10}
        assert mock_create.call_args.args[0].strava_gear_id is None

    async def test_collect_and_import_gears_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        mapping = await service.collect_and_import_gears_data([])
        assert mapping == {}

    async def test_collect_and_import_gear_components(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch("modules.users.users_profile.import_service.gear_components_integration.create_gear_component"):
            await service.collect_and_import_gear_components_data(
                [{"gear_id": 5, "type": "chain", "brand": "Shimano", "model": "Ultegra"}],
                {5: 10},
            )

        assert service.counts["gear_components"] == 1

    async def test_collect_and_import_gear_components_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        await service.collect_and_import_gear_components_data([], {})
        assert service.counts.get("gear_components", 0) == 0


class TestImportServiceUserData:
    async def test_collect_and_import_user_default_gear_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        await service.collect_and_import_user_default_gear([], {})
        assert service.counts["user_default_gear"] == 0

    async def test_collect_and_import_user_default_gear_creates_when_missing(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        with (
            patch(
                "modules.users.users_profile.import_service.users_default_gear_integration.get_default_gear",
                return_value=None,
            ),
            patch(
                "modules.users.users_profile.import_service.users_default_gear_integration.create_default_gear"
            ) as mock_create,
            patch("modules.users.users_profile.import_service.users_default_gear_integration.edit_default_gear"),
        ):
            mock_create.return_value.id = 99
            await service.collect_and_import_user_default_gear([{"run_gear_id": 5}], {5: 10})
        assert service.counts["user_default_gear"] == 1
        mock_create.assert_called_once_with(1, mock_db)

    async def test_collect_and_import_user_default_gear_with_remapping(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        mock_existing = MagicMock()
        mock_existing.id = 99
        with (
            patch(
                "modules.users.users_profile.import_service.users_default_gear_integration.get_default_gear",
                return_value=mock_existing,
            ),
            patch("modules.users.users_profile.import_service.users_default_gear_integration.edit_default_gear"),
        ):
            await service.collect_and_import_user_default_gear(
                [{"run_gear_id": 5, "ride_gear_id": 7}],
                {5: 10, 7: 20},
            )
        assert service.counts["user_default_gear"] == 1

    async def test_collect_and_import_user_integrations_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        await service.collect_and_import_user_integrations([])
        assert service.counts.get("user_integrations", 0) == 0

    async def test_goals_the_user_already_has_or_that_are_invalid_are_skipped(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        goals = [
            {"id": 1, "interval": "weekly", "activity_type": "run", "goal_type": "distance", "goal_distance": 5000},
            {"id": 2, "interval": "nonsense"},
            {"id": 3, "interval": "daily", "activity_type": "run", "goal_type": "distance", "goal_distance": 100},
        ]
        with patch(
            "modules.users.users_profile.import_service.users_goals_integration.create_goal",
            side_effect=[None, core_exceptions.ConflictError("exists")],
        ) as create:
            await service.collect_and_import_user_goals(goals)

        assert create.call_count == 2
        assert service.counts["user_goals"] == 1

    async def test_invalid_singleton_settings_are_skipped_not_fatal(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        base = "modules.users.users_profile.import_service"
        with (
            patch(f"{base}.users_privacy_settings_integration.edit_privacy_settings") as privacy,
            patch(f"{base}.user_integrations_integration.edit_integrations") as integrations,
            patch(f"{base}.users_default_gear_integration.get_default_gear"),
            patch(f"{base}.users_default_gear_integration.edit_default_gear") as default_gear,
        ):
            await service.collect_and_import_user_privacy_settings([{"default_activity_visibility": "bogus"}])
            await service.collect_and_import_user_integrations([{"strava_sync_gear": "not-a-bool"}])
            await service.collect_and_import_user_default_gear([{"unknown_field": 1}], {})

        privacy.assert_not_called()
        integrations.assert_not_called()
        default_gear.assert_not_called()
        assert service.counts["user_privacy_settings"] == 0

    async def test_an_oversized_json_entry_is_refused_before_it_is_parsed(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.max_json_mb = 0.0001
        zip_data = _make_zip_with_json({"data/gears.json": [{"id": i, "nickname": "x" * 50} for i in range(50)]})

        with zipfile.ZipFile(BytesIO(zip_data)) as z, pytest.raises(FileSizeError):
            service._load_single_json(z, "data/gears.json")

    async def test_collect_and_import_user_goals_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        await service.collect_and_import_user_goals([])
        assert service.counts.get("user_goals", 0) == 0

    async def test_collect_and_import_user_privacy_settings_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        await service.collect_and_import_user_privacy_settings([])
        assert service.counts.get("user_privacy_settings", 0) == 0

    async def test_collect_and_import_user_data(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with (
            patch(
                "modules.users.users_profile.import_service.users_integration.edit_profile",
            ),
            patch.object(service, "collect_and_import_user_default_gear", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_user_goals", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_user_integrations", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_user_privacy_settings", new_callable=AsyncMock),
        ):
            await service.collect_and_import_user_data(
                [{"photo_path": "data/user_images/old_user.jpg"}],
                [],
                [],
                [],
                [],
                {},
            )

        assert service.counts["user"] == 1

    async def test_collect_and_import_user_data_empty_still_imports_sub_settings(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with (
            patch.object(service, "collect_and_import_user_default_gear", new_callable=AsyncMock) as mock_gear,
            patch.object(service, "collect_and_import_user_goals", new_callable=AsyncMock) as mock_goals,
            patch.object(service, "collect_and_import_user_integrations", new_callable=AsyncMock) as mock_int,
            patch.object(service, "collect_and_import_user_privacy_settings", new_callable=AsyncMock) as mock_priv,
        ):
            await service.collect_and_import_user_data([], [], [], [], [], {})

        assert service.counts.get("user", 0) == 0
        mock_gear.assert_called_once()
        mock_goals.assert_called_once()
        mock_int.assert_called_once()
        mock_priv.assert_called_once()

    async def test_collect_and_import_user_integrations(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch(
            "modules.users.users_profile.import_service.user_integrations_integration.edit_integrations",
        ):
            await service.collect_and_import_user_integrations([{"strava_sync_gear": True}])

        assert service.counts["user_integrations"] == 1

    async def test_user_integrations_import_drops_credentials_and_oauth_state(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        crafted = {
            "id": 99,
            "user_id": 2,
            "strava_client_id": "stolen-id",
            "strava_client_secret": "stolen-secret",
            "strava_state": "state",
            "strava_token": "stolen-token",
            "strava_refresh_token": "stolen-refresh",
            "garminconnect_token": {"di_token": "stolen"},
            "strava_sync_gear": True,
            "garminconnect_sync_gear": False,
        }

        with patch(
            "modules.users.users_profile.import_service.user_integrations_integration.edit_integrations",
        ) as mock_edit:
            await service.collect_and_import_user_integrations([crafted])

        applied = mock_edit.call_args.args[0]
        assert applied.model_dump(exclude_unset=True) == {"strava_sync_gear": True, "garminconnect_sync_gear": False}

    async def test_user_integrations_import_with_only_credentials_imports_nothing(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

        with patch(
            "modules.users.users_profile.import_service.user_integrations_integration.edit_integrations",
        ) as mock_edit:
            await service.collect_and_import_user_integrations([{"strava_token": "stolen"}])

        mock_edit.assert_not_called()
        assert service.counts["user_integrations"] == 0

    async def test_collect_and_import_user_goals(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch("modules.users.users_profile.import_service.users_goals_integration.create_goal"):
            await service.collect_and_import_user_goals(
                [{"interval": "daily", "activity_type": "run", "goal_type": "distance", "goal_distance": 5000}]
            )

        assert service.counts["user_goals"] == 1

    async def test_collect_and_import_user_privacy_settings(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch(
            "modules.users.users_profile.import_service.users_privacy_settings_integration.edit_privacy_settings",
        ):
            await service.collect_and_import_user_privacy_settings([{"hide_activity_map": True}])

        assert service.counts["user_privacy_settings"] == 1

    async def test_crafted_zip_cannot_recreate_identity_links(self) -> None:
        """A crafted profile ZIP with identity-provider data must not recreate identity links."""
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        zip_data = _make_zip_with_json(
            {
                "data/gears.json": [],
                "data/gear_components.json": [],
                "data/user.json": [{"name": "Crafted Import"}],
                "data/user_default_gear.json": [],
                "data/user_goals.json": [],
                "data/user_integrations.json": [],
                "data/user_privacy_settings.json": [],
                "data/user_identity_providers.json": [
                    {
                        "user_id": 999,
                        "idp_id": 1,
                        "idp_subject": "attacker-subject",
                    }
                ],
                "data/activities.json": [],
                "data/notifications.json": [],
                "data/health_weight.json": [],
                "data/health_targets.json": [],
            }
        )

        assert not hasattr(service, "collect_and_import_user_identity_providers")
        with patch(
            "modules.users.users_profile.import_service.users_integration.edit_profile",
        ) as mock_edit_profile:
            result = await service.import_from_zip_data(zip_data)

        assert result["detail"] == "Import completed"
        mock_edit_profile.assert_called_once()
        assert service.counts["user"] == 1
        assert service.counts.get("user_identity_providers", 0) == 0


class TestImportServiceHealthRecords:
    _SCHEMAS: ClassVar[dict[str, type]] = {
        "health_sleep": health_sleep_schema.HealthSleepCreate,
        "health_steps": health_steps_schema.HealthStepsCreate,
        "health_water": health_water_schema.HealthWaterCreate,
        "health_fasting": health_fasting_schema.HealthFastingCreate,
        "health_poop": health_poop_schema.HealthPoopCreate,
    }

    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    def _writers(self, stored: bool = True) -> tuple[dict[str, MagicMock], Any]:
        writers = {name: MagicMock(return_value=stored) for name in self._SCHEMAS}
        patched = patch.dict(
            profile_import_service._HEALTH_RECORD_IMPORTS,
            {name: (schema, writers[name]) for name, schema in self._SCHEMAS.items()},
        )
        return writers, patched

    async def test_imports_each_kind_without_the_row_identity(self) -> None:
        service = self._service()
        identity = {"id": 9, "user_id": 999, "version": 4}
        records = {
            "health_sleep": [{"date": "2024-01-15", "total_sleep_seconds": 28800, **identity}],
            "health_steps": [{"date": "2024-01-15", "steps": 9000, **identity}],
            "health_water": [{"date": "2024-01-15", "amount_ml": 1500, **identity}],
            "health_fasting": [{"fast_start_time": "2024-01-15T20:00:00Z", "status": "completed", **identity}],
            "health_poop": [{"date_time": "2024-01-15T08:00:00Z", **identity}],
        }
        writers, patched = self._writers()

        with patched:
            await service.collect_and_import_health_records(records)

        for writer in writers.values():
            writer.assert_called_once()
            assert writer.call_args.args[0] == 1
        assert writers["health_sleep"].call_args.args[1].total_sleep_seconds == 28800
        assert writers["health_steps"].call_args.args[1].steps == 9000
        assert all(service.counts[name] == 1 for name in records)

    async def test_a_skipped_duplicate_is_not_counted(self) -> None:
        service = self._service()
        _, patched = self._writers(stored=False)

        with patched:
            await service.collect_and_import_health_records({"health_poop": [{"date_time": "2024-01-15T08:00:00Z"}]})

        assert service.counts["health_poop"] == 0

    async def test_an_invalid_row_is_skipped_and_the_rest_imported(self) -> None:
        service = self._service()
        writers, patched = self._writers()

        with patched:
            await service.collect_and_import_health_records(
                {"health_steps": [{"steps": "many"}, {"unknown": 1}, {"date": "2024-01-16", "steps": 100}]}
            )

        writers["health_steps"].assert_called_once()
        assert service.counts["health_steps"] == 1

    async def test_an_archive_without_the_files_imports_nothing(self) -> None:
        service = self._service()
        writers, patched = self._writers()

        with patched:
            await service.collect_and_import_health_records({})

        assert not any(writer.called for writer in writers.values())


class TestImportServiceHealth:
    async def test_collect_and_import_health_weight(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        mock_health_target = MagicMock()
        mock_health_target.id = 1

        with (
            patch("modules.users.users_profile.import_service.health_weight_integration.upsert_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_integration.get_health_targets",
                return_value=mock_health_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_integration.edit_health_targets"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": 75.5}],
                [{"weight": 80.0, "steps": 10000}],
            )

        assert service.counts["health_weight"] == 1
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_weight_string_conversion_errors(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        mock_target = MagicMock()
        mock_target.id = 1

        with (
            patch("modules.users.users_profile.import_service.health_weight_integration.upsert_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_integration.get_health_targets",
                return_value=mock_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_integration.edit_health_targets"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": "abc", "physique_rating": "xyz", "metabolic_age": "invalid"}],
                [{"weight": "bad", "steps": "wrong", "sleep": "nope"}],
            )

        # A weight that cannot be read leaves a record without its value, which cannot be stored.
        assert service.counts["health_weight"] == 0
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_weight_no_targets(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with (
            patch("modules.users.users_profile.import_service.health_weight_integration.upsert_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_integration.get_health_targets",
                return_value=None,
            ),
            patch("modules.users.users_profile.import_service.health_targets_integration.create_health_targets"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": 75.5}],
                [],
            )

        assert service.counts["health_weight"] == 1


class TestImportServiceActivities:
    async def test_collect_and_import_activities_batched_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json({"data/activities.json": []})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            mapping = await service.collect_and_import_activities_data_batched(
                z,
                set(),
                {},
                0,
                3600,
            )

        assert mapping == {}

    async def test_activity_limit_exceeded(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.max_activities = 1

        zip_data = _make_zip_with_json({"data/activities.json": [{"id": 1}, {"id": 2}]})
        with zipfile.ZipFile(BytesIO(zip_data)) as z, pytest.raises(ActivityLimitError):
            await service.collect_and_import_activities_data_batched(
                z,
                set(),
                {},
                0,
                3600,
            )


class TestImportServiceActivityComponents:
    @pytest.mark.parametrize(
        ("key", "count_key"),
        [
            ("laps", "activity_laps"),
            ("sets", "activity_sets"),
            ("streams", "activity_streams"),
            ("workout_steps", "activity_workout_steps"),
        ],
    )
    async def test_collect_and_import_activity_components_uses_contributor(
        self,
        key: str,
        count_key: str,
    ) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        contributor = MagicMock(key=key, count_key=count_key)
        contributor.restore.return_value = 1
        records = [{"activity_id": 1}]
        new_activity = MagicMock(id=10, user_id=1)

        with patch.object(
            profile_import_service.activities_contributor_registry,
            "profile_activity_contributors",
            return_value=(contributor,),
        ):
            await service.collect_and_import_activity_components(
                {key: records},
                1,
                new_activity,
            )

        contributor.restore.assert_called_once_with(records, 1, new_activity, mock_db)
        assert service.counts[count_key] == 1

    async def test_collect_and_import_activity_components_passes_empty_records(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        contributor = MagicMock(key="laps", count_key="activity_laps")
        contributor.restore.return_value = 0
        new_activity = MagicMock(id=10, user_id=1)

        with patch.object(
            profile_import_service.activities_contributor_registry,
            "profile_activity_contributors",
            return_value=(contributor,),
        ):
            await service.collect_and_import_activity_components({}, 1, new_activity)

        contributor.restore.assert_called_once_with([], 1, new_activity, mock_db)
        assert service.counts["activity_laps"] == 0

    def test_restore_global_activity_components_once(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        contributor = MagicMock(
            key="exercise_titles",
            archive_path="data/activity_exercise_titles.json",
            count_key="activity_exercise_titles",
        )
        contributor.restore.return_value = 2
        records = [{"exercise_name": 1}, {"exercise_name": 2}]
        zipf = MagicMock()

        with (
            patch.object(
                profile_import_service.activities_contributor_registry,
                "profile_global_contributors",
                return_value=(contributor,),
            ),
            patch.object(service, "_load_single_json", return_value=records) as load_json,
        ):
            service._restore_global_activity_components(zipf)

        load_json.assert_called_once_with(zipf, contributor.archive_path, check_memory=False)
        contributor.restore.assert_called_once_with(records, mock_db)
        assert service.counts["activity_exercise_titles"] == 2
        # Restore only stages the rows; the whole import commits once, later.
        mock_db.commit.assert_not_called()


class TestImportServiceFromZip:
    async def test_import_from_zip_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        zip_data = _make_zip_with_json(
            {
                "data/gears.json": [{"id": 1, "nickname": "Garmin", "gear_type": 1}],
                "data/gear_components.json": [],
                "data/user.json": [{"username": "test"}],
                "data/user_default_gear.json": [],
                "data/user_goals.json": [],
                "data/user_integrations.json": [],
                "data/user_privacy_settings.json": [],
                "data/activities.json": [],
                "data/notifications.json": [],
                "data/health_weight.json": [],
                "data/health_targets.json": [],
            }
        )

        async def _increment_gears(_data):
            service.counts["gears"] = 1
            return {}

        with (
            patch.object(service, "collect_and_import_gears_data", side_effect=_increment_gears),
            patch.object(service, "collect_and_import_gear_components_data", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_user_data", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_activities_data_batched", return_value={}),
            patch.object(service, "collect_and_import_health_weight", new_callable=AsyncMock),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_activity_media_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_user_images_from_zip", new_callable=AsyncMock),
        ):
            result = await service.import_from_zip_data(zip_data)

        assert "imported" in result

    @staticmethod
    def _atomic_service():
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100
        return service, mock_db

    async def test_the_database_part_commits_once_before_any_file_is_written(self) -> None:
        service, mock_db = self._atomic_service()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        zip_data = _make_zip_with_json({"data/gears.json": [{"id": 1, "nickname": "Bike"}]})

        with (
            patch.object(service, "collect_and_import_gears_data", new_callable=AsyncMock, return_value={}) as gears,
            patch.object(
                service, "collect_and_import_activities_data_batched", new_callable=AsyncMock, return_value={}
            ),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock) as files,
            patch.object(service, "add_activity_media_from_zip", new_callable=AsyncMock) as media,
            patch.object(service, "add_user_images_from_zip", new_callable=AsyncMock) as images,
        ):
            order.attach_mock(gears, "gears")
            order.attach_mock(files, "files")
            order.attach_mock(media, "media")
            order.attach_mock(images, "images")
            service.counts["gears"] = 1
            await service.import_from_zip_data(zip_data)

        names = [call[0] for call in order.mock_calls]
        assert names.count("commit") == 1
        assert names.index("commit") < names.index("files") < names.index("media") < names.index("images")
        mock_db.rollback.assert_not_called()

    @pytest.mark.parametrize("failing", ["collect_and_import_gears_data", "collect_and_import_activities_data_batched"])
    async def test_a_failure_in_the_database_part_rolls_everything_back(self, failing) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": []})

        with (
            patch.object(service, "collect_and_import_gears_data", new_callable=AsyncMock, return_value={}),
            patch.object(
                service, "collect_and_import_activities_data_batched", new_callable=AsyncMock, return_value={}
            ),
            patch.object(service, failing, new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock) as files,
            pytest.raises(RuntimeError),
        ):
            await service.import_from_zip_data(zip_data)

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()
        files.assert_not_called()

    async def test_a_failure_writing_files_keeps_the_committed_rows(self) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": [], "activity_files/1.gpx": []})

        with (
            patch.object(service, "collect_and_import_gears_data", new_callable=AsyncMock, return_value={}),
            patch.object(
                service, "collect_and_import_activities_data_batched", new_callable=AsyncMock, return_value={}
            ),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock, side_effect=OSError("disk")),
            pytest.raises(FileSystemError),
        ):
            await service.import_from_zip_data(zip_data)

        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    async def test_an_archive_with_nothing_to_import_is_rejected_before_the_commit(self) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": []})

        with (
            patch.object(service, "collect_and_import_gears_data", new_callable=AsyncMock, return_value={}),
            patch.object(
                service, "collect_and_import_activities_data_batched", new_callable=AsyncMock, return_value={}
            ),
            pytest.raises(FileFormatError, match="zero items"),
        ):
            await service.import_from_zip_data(zip_data)

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()

    async def test_the_commit_callback_fires_once_the_rows_are_committed(self) -> None:
        mock_db = MagicMock(spec=Session)
        calls = []
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
            on_database_committed=lambda: calls.append(mock_db.commit.call_count),
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100
        zip_data = _make_zip_with_json({"data/gears.json": [], "user_images/a.png": []})

        with (
            patch.object(service, "collect_and_import_gears_data", new_callable=AsyncMock, return_value={}),
            patch.object(
                service, "collect_and_import_activities_data_batched", new_callable=AsyncMock, return_value={}
            ),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_activity_media_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_user_images_from_zip", new_callable=AsyncMock),
        ):
            service.counts["user_images"] = 1
            await service.import_from_zip_data(zip_data)

        assert calls == [1]

    async def test_a_rejected_archive_rolls_back(self) -> None:
        service, mock_db = self._atomic_service()

        with pytest.raises(FileFormatError):
            await service.import_from_zip_data(b"not a zip")

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()

    async def test_import_from_zip_os_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        zip_data = _make_zip_with_json({"data/gears.json": []})

        with (
            patch.object(service, "collect_and_import_gears_data", side_effect=OSError("disk full")),
            pytest.raises(FileSystemError),
        ):
            await service.import_from_zip_data(zip_data)

    async def test_import_from_zip_all_empty_raises_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        zip_data = _make_zip_with_json(
            {
                "data/gears.json": [],
                "data/gear_components.json": [],
                "data/user.json": [],
                "data/user_default_gear.json": [],
                "data/user_goals.json": [],
                "data/user_identity_providers.json": [],
                "data/user_integrations.json": [],
                "data/user_privacy_settings.json": [],
                "data/activities.json": [],
                "data/notifications.json": [],
                "data/health_weight.json": [],
                "data/health_targets.json": [],
            }
        )

        with (
            patch.object(service, "collect_and_import_gears_data", return_value={}),
            patch.object(service, "collect_and_import_gear_components_data", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_user_data", new_callable=AsyncMock),
            patch.object(service, "collect_and_import_activities_data_batched", return_value={}),
            patch.object(service, "collect_and_import_health_weight", new_callable=AsyncMock),
            patch.object(service, "add_activity_files_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_activity_media_from_zip", new_callable=AsyncMock),
            patch.object(service, "add_user_images_from_zip", new_callable=AsyncMock),
            pytest.raises(FileFormatError, match="zero items"),
        ):
            await service.import_from_zip_data(zip_data)


class TestImportServiceFiles:
    async def test_add_activity_files_from_zip_skips_non_numeric(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_activity_files_from_zip(z, {"activity_files/abc.gpx"}, {})

    async def test_add_activity_media_from_zip_skips_non_numeric(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_activity_media_from_zip(z, {"activity_media/abc.jpg"}, {})

    async def test_add_user_images_from_zip(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_user_images_from_zip(z, set())


class TestImportServiceReadZipEntryDecompressed:
    async def test_read_zip_entry_decompressed_exceeds_limit(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/test.json", b"x" * 2048)
        zip_bytes = buf.getvalue()

        with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
            info = z.getinfo("data/test.json")
            fake_src = BytesIO(b"x" * 100)
            with (
                patch.object(type(info), "file_size", new_callable=PropertyMock, return_value=10),
                patch.object(z, "open", return_value=fake_src),
                pytest.raises(FileSizeError, match="decompressed size exceeds"),
            ):
                service._read_zip_entry(z, "data/test.json", max_bytes=50)


class TestImportServiceLoadComponentsForBatch:
    def test_load_components_for_batch_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_components_for_batch(z, [], [], "laps")
        assert result == []

    def test_load_components_for_batch_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        zip_data = _make_zip_with_json(
            {
                "data/activity_laps_000.json": [
                    {"activity_id": 1, "lap_index": 1},
                    {"activity_id": 2, "lap_index": 1},
                ],
            }
        )
        activities_batch = [{"id": 1}, {"id": 3}]

        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_components_for_batch(
                z,
                ["data/activity_laps_000.json"],
                activities_batch,
                "laps",
            )

        assert len(result) == 1
        assert result[0]["activity_id"] == 1

    def test_load_components_for_batch_json_decode_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/bad.json", "not-valid-json")
        zip_data = buf.getvalue()

        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_components_for_batch(
                z,
                ["data/bad.json"],
                [{"id": 1}],
                "laps",
            )
        assert result == []

    def test_load_components_for_batch_file_format_error_caught(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/laps.json", b"x" * 2048)
        zip_data = buf.getvalue()

        with (
            zipfile.ZipFile(BytesIO(zip_data)) as z,
            patch.object(
                service,
                "_read_zip_entry",
                side_effect=FileFormatError("bad format"),
            ),
        ):
            result = service._load_components_for_batch(
                z,
                ["data/laps.json"],
                [{"id": 1}],
                "laps",
            )
        assert result == []

    def test_load_components_for_batch_memory_error_propagates(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        zip_data = _make_zip_with_json({"data/laps.json": [{"activity_id": 1}]})
        with (
            zipfile.ZipFile(BytesIO(zip_data)) as z,
            patch.object(
                service,
                "_read_zip_entry",
                side_effect=MemoryAllocationError("oom"),
            ),
            pytest.raises(MemoryAllocationError),
        ):
            service._load_components_for_batch(
                z,
                ["data/laps.json"],
                [{"id": 1}],
                "laps",
            )


class TestImportServiceActivityComponentsMedia:
    async def test_collect_and_import_activity_components_with_media_valid_path(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        import modules.activities.activity_media.integration_service as media_integration

        contributor = media_integration.profile_contributor()
        records = [{"activity_id": 1, "media_path": "1_photo.jpg", "media_type": 1}]
        with (
            patch.object(
                profile_import_service.activities_contributor_registry,
                "profile_activity_contributors",
                return_value=(contributor,),
            ),
            patch.object(media_integration, "_restore_media_records") as restore_media,
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                {"media": records},
                1,
                mock_activity,
            )

        restore_media.assert_called_once()
        assert records[0]["media_path"] == "1_photo.jpg"
        assert service.counts.get("activity_media") == 1

    async def test_collect_and_import_activity_components_rejects_a_key_with_a_separator(self) -> None:
        """A key carrying a path separator is skipped.

        The archive is untrusted: such a value would address a blob outside the
        flat media area, where the deletion cleanup could never find it again.
        """
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        import modules.activities.activity_media.integration_service as media_integration

        contributor = media_integration.profile_contributor()
        with (
            patch.object(
                profile_import_service.activities_contributor_registry,
                "profile_activity_contributors",
                return_value=(contributor,),
            ),
            patch.object(media_integration, "_restore_media_records") as mock_create,
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                {"media": [{"activity_id": 1, "media_path": "../../etc/1_passwd.jpg", "media_type": 1}]},
                1,
                mock_activity,
            )

        mock_create.assert_not_called()
        assert service.counts.get("activity_media", 0) == 0

    async def test_collect_and_import_activity_components_with_media_invalid_key(self) -> None:
        """A media entry whose key carries no ``{activity_id}_`` prefix is skipped."""
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        import modules.activities.activity_media.integration_service as media_integration

        contributor = media_integration.profile_contributor()
        with (
            patch.object(
                profile_import_service.activities_contributor_registry,
                "profile_activity_contributors",
                return_value=(contributor,),
            ),
            patch.object(media_integration, "_restore_media_records") as mock_create,
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                {"media": [{"activity_id": 1, "media_path": "nounderscore.jpg", "media_type": 1}]},
                1,
                mock_activity,
            )

        mock_create.assert_not_called()
        assert service.counts.get("activity_media", 0) == 0

    async def test_collect_and_import_activity_components_with_media_multiple(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        import modules.activities.activity_media.integration_service as media_integration

        contributor = media_integration.profile_contributor()
        with (
            patch.object(
                profile_import_service.activities_contributor_registry,
                "profile_activity_contributors",
                return_value=(contributor,),
            ),
            patch.object(media_integration, "_restore_media_records"),
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                {
                    "media": [
                        {"activity_id": 1, "media_path": "1_a.jpg", "media_type": 1},
                        {"activity_id": 1, "media_path": "1_b.jpg", "media_type": 1},
                        {"activity_id": 2, "media_path": "2_c.jpg", "media_type": 1},
                    ]
                },
                1,
                mock_activity,
            )

        assert service.counts.get("activity_media") == 2


class TestImportServiceActivitiesDataBatched:
    async def test_collect_and_import_activities_batched_single_batch(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json(
            {
                "data/activities.json": [
                    {
                        "id": 1,
                        "gear_id": 5,
                        "distance": 1000,
                        "name": "Morning Run",
                        "activity_type": 1,
                        "start_time": "2024-01-01T08:00:00",
                        "end_time": "2024-01-01T09:00:00",
                    },
                ],
                "data/activity_laps_000.json": [{"activity_id": 1, "lap_index": 1}],
                "data/activity_sets_000.json": [
                    {"activity_id": 1, "duration": 30.0, "set_type": "manual", "start_time": "2024-01-01T00:00:00"}
                ],
                "data/activity_streams_000.json": [{"activity_id": 1, "stream_type": 1, "stream_waypoints": []}],
                "data/activity_workout_steps.json": [],
                "data/activity_media.json": [],
                "data/activity_exercise_titles.json": [],
            }
        )

        mock_new_activity = MagicMock()
        mock_new_activity.id = 10

        import time

        with (
            patch(
                "modules.users.users_profile.import_service.activity_integration.restore_activity",
                return_value=mock_new_activity,
            ),
            patch.object(service, "collect_and_import_activity_components", new_callable=AsyncMock),
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            file_list = set(z.namelist())
            mapping = await service.collect_and_import_activities_data_batched(
                z,
                file_list,
                {5: 20},
                time.time(),
                3600,
            )

        assert mapping == {1: 10}
        assert service.counts["activities"] == 1
        # The restore functions only stage; the import commits once at the end.
        mock_db.commit.assert_not_called()

    async def test_collect_and_import_activities_batched_no_original_id(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json(
            {
                "data/activities.json": [
                    {
                        "distance": 1000,
                        "name": "Test",
                        "activity_type": 1,
                        "gear_id": 5,
                        "start_time": "2024-01-01T08:00:00",
                        "end_time": "2024-01-01T09:00:00",
                    },
                ],
                "data/activity_laps_000.json": [{"activity_id": 1, "lap_index": 1}],
                "data/activity_sets_000.json": [],
                "data/activity_streams_000.json": [],
                "data/activity_workout_steps.json": [],
                "data/activity_media.json": [],
                "data/activity_exercise_titles.json": [],
            }
        )

        mock_new_activity = MagicMock()
        mock_new_activity.id = 10

        import time

        with (
            patch(
                "modules.users.users_profile.import_service.activity_integration.restore_activity",
                return_value=mock_new_activity,
            ),
            patch.object(service, "collect_and_import_activity_components", new_callable=AsyncMock) as mock_components,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            file_list = set(z.namelist())
            mapping = await service.collect_and_import_activities_data_batched(
                z,
                file_list,
                {5: 20},
                time.time(),
                3600,
            )

        assert mapping == {}
        assert service.counts["activities"] == 1
        mock_components.assert_not_called()


class TestImportServiceAddActivityFiles:
    async def test_add_activity_files_from_zip_valid(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_files/1.gpx", b"<gpx></gpx>")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_activity_file_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes", new_callable=AsyncMock),
            patch(
                "modules.users.users_profile.import_service.activity_file_storage_integration.store_activity_file"
            ) as mock_store,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_files_from_zip(
                z,
                {"activity_files/1.gpx"},
                {1: 10},
            )

        assert service.counts["activity_files"] == 1
        mock_store.assert_called_once()

    async def test_add_activity_files_from_zip_no_mapping(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_files/999.gpx", b"<gpx></gpx>")
        zip_data = buf.getvalue()

        with (
            patch(
                "modules.users.users_profile.import_service.activity_file_storage_integration.store_activity_file"
            ) as mock_store,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_files_from_zip(
                z,
                {"activity_files/999.gpx"},
                {1: 10},
            )

        mock_store.assert_not_called()
        assert service.counts.get("activity_files", 0) == 0

    async def test_add_activity_files_from_zip_domain_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_files/1.gpx", b"<gpx></gpx>")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_activity_file_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch(
                "modules.users.users_profile.import_service.file_uploads.validate_bytes",
                new_callable=AsyncMock,
                side_effect=core_exceptions.InvalidInputError("invalid file"),
            ),
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_files_from_zip(
                z,
                {"activity_files/1.gpx"},
                {1: 10},
            )

        assert service.counts.get("activity_files", 0) == 0


class TestImportServiceAddActivityMediaFromZip:
    async def test_add_activity_media_from_zip_valid(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_media/1_photo.jpg", b"image-data")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes", new_callable=AsyncMock),
            _storage_of(service) as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_media_from_zip(
                z,
                {"activity_media/1_photo.jpg"},
                {1: 10},
            )

        assert service.counts["media"] == 1
        # Re-keyed onto the new activity id and written through the provider.
        runtime.get_active_platform.return_value.storage.save.assert_called_once_with(
            "activity_media", "10_photo.jpg", b"image-data"
        )

    async def test_add_activity_media_from_zip_no_mapping(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_media/999_photo.jpg", b"image-data")
        zip_data = buf.getvalue()

        with (
            patch(
                "modules.users.users_profile.import_service.file_uploads.save_validated_bytes", new_callable=AsyncMock
            ) as mock_save,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_media_from_zip(
                z,
                {"activity_media/999_photo.jpg"},
                {1: 10},
            )

        mock_save.assert_not_called()
        assert service.counts.get("media", 0) == 0

    async def test_add_activity_media_from_zip_domain_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_media/1_bad.jpg", b"image-data")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch(
                "modules.users.users_profile.import_service.file_uploads.validate_bytes",
                new_callable=AsyncMock,
                side_effect=core_exceptions.InvalidInputError("invalid image"),
            ),
            _storage_of(service) as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_activity_media_from_zip(
                z,
                {"activity_media/1_bad.jpg"},
                {1: 10},
            )

        assert service.counts.get("media", 0) == 0
        # A rejected image is never stored.
        runtime.get_active_platform.return_value.storage.save.assert_not_called()

    async def test_add_activity_media_from_zip_value_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_media/abc_photo.jpg", b"image-data")
        zip_data = buf.getvalue()

        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_activity_media_from_zip(
                z,
                {"activity_media/abc_photo.jpg"},
                {},
            )

        assert service.counts.get("media", 0) == 0


class TestImportServiceAddUserImages:
    async def test_add_user_images_from_zip_accepts_webp_like_the_upload_does(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("user_images/photo.WEBP", b"image-data")
        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000

        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes", new_callable=AsyncMock),
            patch("modules.users.users_profile.import_service.users_integration.store_user_photo") as mock_store,
            zipfile.ZipFile(BytesIO(buf.getvalue())) as z,
        ):
            await service.add_user_images_from_zip(z, {"user_images/photo.WEBP"})

        assert mock_store.call_args.args[:3] == (1, ".webp", b"image-data")

    async def test_add_user_images_from_zip_valid(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("user_images/old_photo.jpg", b"image-data")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes", new_callable=AsyncMock),
            patch("modules.users.users_profile.import_service.users_integration.store_user_photo") as mock_store,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_user_images_from_zip(z, {"user_images/old_photo.jpg"})

        assert service.counts["user_images"] == 1
        # The archive's filename is discarded: the key is minted for the
        # importing user so a crafted ZIP cannot write over someone else's blob.
        mock_store.assert_called_once_with(1, ".jpg", b"image-data", service.storage, mock_db)

    async def test_add_user_images_from_zip_domain_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("user_images/old_photo.jpg", b"image-data")
        zip_data = buf.getvalue()

        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000
        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch(
                "modules.users.users_profile.import_service.file_uploads.validate_bytes",
                new_callable=AsyncMock,
                side_effect=core_exceptions.InvalidInputError("invalid image"),
            ),
            _storage_of(service) as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_user_images_from_zip(z, {"user_images/old_photo.jpg"})

        assert service.counts.get("user_images", 0) == 0
        runtime.get_active_platform.return_value.storage.save.assert_not_called()


class TestImportServiceHealthEmptyBranches:
    async def test_collect_and_import_health_weight_empty_data(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        mock_target = MagicMock()
        mock_target.id = 1

        with (
            patch(
                "modules.users.users_profile.import_service.health_targets_integration.get_health_targets",
                return_value=mock_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_integration.edit_health_targets"),
        ):
            await service.collect_and_import_health_weight([], [{"weight": 80.0}])

        assert service.counts.get("health_weight", 0) == 0
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_targets_no_current(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with (
            patch("modules.users.users_profile.import_service.health_weight_integration.upsert_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_integration.get_health_targets",
                return_value=None,
            ),
            patch("modules.users.users_profile.import_service.health_targets_integration.edit_health_targets"),
            patch(
                "modules.users.users_profile.import_service.health_targets_schema.HealthTargetsUpdate",
                return_value=MagicMock(),
            ),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": 75.5}],
                [{"weight": 80.0, "id": 99}],
            )

        assert service.counts["health_weight"] == 1
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_weight_empty_targets(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch("modules.users.users_profile.import_service.health_weight_integration.upsert_health_weight"):
            await service.collect_and_import_health_weight([{"weight": 75.5}], [])

        assert service.counts["health_weight"] == 1
        assert service.counts.get("health_targets", 0) == 0


class TestImportServiceFromZipExtended:
    async def test_import_from_zip_json_decode_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/gears.json", "not-valid-json")
        zip_data = buf.getvalue()

        with pytest.raises(JSONParseError, match="Failed to parse JSON"):
            await service.import_from_zip_data(zip_data)


class TestArchiveFileNames:
    """A file whose name carries no activity id is skipped and logged; no other ValueError is hidden by that."""

    @staticmethod
    def _service_and_zip(names: list[str]):
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in names:
                archive.writestr(name, b"data")
        return service, zipfile.ZipFile(BytesIO(buffer.getvalue()))

    async def test_an_activity_file_without_a_numeric_id_is_skipped_and_logged(self) -> None:
        service, archive = self._service_and_zip(["activity_files/notes.gpx"])
        with (
            patch.object(profile_import_service.activity_file_storage_integration, "store_activity_file") as store,
            patch.object(profile_import_service.logger, "debug") as debug,
        ):
            await service.add_activity_files_from_zip(archive, set(archive.namelist()), {1: 2})

        store.assert_not_called()
        assert any("without an activity id" in str(call.args[0]) for call in debug.call_args_list)

    async def test_a_value_error_from_storing_an_activity_file_is_not_swallowed(self) -> None:
        service, archive = self._service_and_zip(["activity_files/1.gpx"])
        with (
            patch.object(profile_import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
            patch.object(
                profile_import_service.activity_file_storage_integration,
                "store_activity_file",
                side_effect=ValueError("storage rejected the key"),
            ),
            pytest.raises(ValueError, match="storage rejected"),
        ):
            await service.add_activity_files_from_zip(archive, set(archive.namelist()), {1: 2})

    async def test_activity_media_without_a_numeric_id_is_skipped_and_logged(self) -> None:
        service, archive = self._service_and_zip(["activity_media/abc_photo.png"])
        with (
            patch.object(profile_import_service.activity_media_integration, "store_media_blob") as store,
            patch.object(profile_import_service.logger, "debug") as debug,
        ):
            await service.add_activity_media_from_zip(archive, set(archive.namelist()), {1: 2})

        store.assert_not_called()
        assert any("without an activity id" in str(call.args[0]) for call in debug.call_args_list)

    async def test_a_value_error_from_storing_activity_media_is_not_swallowed(self) -> None:
        service, archive = self._service_and_zip(["activity_media/1_photo.png"])
        with (
            patch.object(profile_import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
            patch.object(
                profile_import_service.activity_media_integration,
                "store_media_blob",
                side_effect=ValueError("storage rejected the key"),
            ),
            pytest.raises(ValueError, match="storage rejected"),
        ):
            await service.add_activity_media_from_zip(archive, set(archive.namelist()), {1: 2})
