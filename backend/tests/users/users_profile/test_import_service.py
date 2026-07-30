"""Tests for profile data import service."""

import json
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

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
        assert config.max_file_size_mb == 1000

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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(user_id=1, db=mock_db, websocket_manager=mock_ws)
        assert service.user_id == 1
        assert service.db is mock_db
        assert service.websocket_manager is mock_ws

    def test_init_with_custom_config(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        config = profile_import_service.ImportPerformanceConfig(batch_size=10)
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.max_file_size_mb = 0.001

        with pytest.raises(FileSizeError, match="exceeds maximum"):
            await service.import_from_zip_data(b"x" * 2000)

    async def test_bad_zip_format(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.max_file_size_mb = 100

        with pytest.raises(FileFormatError, match="Invalid ZIP"):
            await service.import_from_zip_data(b"not-a-zip")


class TestImportServiceReadZipEntry:
    def test_read_zip_entry_exceeds_size(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        zip_data = _make_zip_with_json({"data/activities.json": [{"id": 1}]})
        with zipfile.ZipFile(BytesIO(zip_data)) as z, pytest.raises(FileSizeError):
            service._read_zip_entry(z, "data/activities.json", max_bytes=1)


class TestImportServiceLoadSingleJson:
    def test_load_single_json_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({"data/gears.json": [{"id": 1}]})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/gears.json")

        assert result == [{"id": 1}]

    def test_load_single_json_not_found(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/nonexistent.json")

        assert result == []

    def test_load_single_json_invalid_json(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data/bad.json", "not-json")

        with zipfile.ZipFile(BytesIO(buf.getvalue())) as z, pytest.raises(JSONParseError):
            service._load_single_json(z, "data/bad.json")

    def test_load_single_json_type_guard_non_list_returns_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        for non_list_data in (None, {}, "string", 42):
            zip_data = _make_zip_with_json({"data/test.json": non_list_data})
            with zipfile.ZipFile(BytesIO(zip_data)) as z:
                result = service._load_single_json(z, "data/test.json")
            assert result == [], f"Expected [] for {type(non_list_data).__name__}"

    def test_load_single_json_missing_file_returns_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        zip_data = _make_zip_with_json({"other.json": []})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_single_json(z, "data/missing.json")

        assert result == []


class TestImportServiceGetSplitFiles:
    def test_get_split_files_list_returns_sorted(self) -> None:
        service = profile_import_service.ImportService(
            user_id=1,
            db=MagicMock(spec=Session),
            websocket_manager=MagicMock(),
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
            db=MagicMock(spec=Session),
            websocket_manager=MagicMock(),
        )
        file_list = {"data/activity_laps.json", "data/other.json"}
        result = service._get_split_files_list(file_list, "data/activity_laps")
        assert result == ["data/activity_laps.json"]

    def test_get_split_files_list_empty(self) -> None:
        service = profile_import_service.ImportService(
            user_id=1,
            db=MagicMock(spec=Session),
            websocket_manager=MagicMock(),
        )
        result = service._get_split_files_list(set(), "data/activity_laps")
        assert result == []


class TestImportServiceGears:
    async def test_collect_and_import_gears(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_new_gear = MagicMock()
        mock_new_gear.id = 10

        with patch(
            "modules.users.users_profile.import_service.gear_crud.create_gear",
            return_value=mock_new_gear,
        ):
            mapping = await service.collect_and_import_gears_data([{"id": 5, "nickname": "Garmin", "gear_type": 1}])

        assert mapping == {5: 10}

    async def test_collect_and_import_gears_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mapping = await service.collect_and_import_gears_data([])
        assert mapping == {}

    async def test_collect_and_import_gear_components(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch("modules.users.users_profile.import_service.gear_components_crud.create_gear_component"):
            await service.collect_and_import_gear_components_data(
                [{"gear_id": 5, "type": "chain", "brand": "Shimano", "model": "Ultegra"}],
                {5: 10},
            )

        assert service.counts["gear_components"] == 1

    async def test_collect_and_import_gear_components_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        await service.collect_and_import_gear_components_data([], {})
        assert service.counts.get("gear_components", 0) == 0


class TestImportServiceUserData:
    async def test_collect_and_import_user_default_gear_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        await service.collect_and_import_user_default_gear([], {})
        assert service.counts["user_default_gear"] == 0

    async def test_collect_and_import_user_default_gear_creates_when_missing(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        with (
            patch(
                "modules.users.users_profile.import_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                return_value=None,
            ),
            patch(
                "modules.users.users_profile.import_service.user_default_gear_crud.create_user_default_gear"
            ) as mock_create,
            patch("modules.users.users_profile.import_service.user_default_gear_crud.edit_user_default_gear"),
        ):
            mock_create.return_value.id = 99
            await service.collect_and_import_user_default_gear([{"run_gear_id": 5}], {5: 10})
        assert service.counts["user_default_gear"] == 1
        mock_create.assert_called_once_with(1, mock_db)

    async def test_collect_and_import_user_default_gear_with_remapping(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        mock_existing = MagicMock()
        mock_existing.id = 99
        with (
            patch(
                "modules.users.users_profile.import_service.user_default_gear_crud.get_user_default_gear_by_user_id",
                return_value=mock_existing,
            ),
            patch("modules.users.users_profile.import_service.user_default_gear_crud.edit_user_default_gear"),
        ):
            await service.collect_and_import_user_default_gear(
                [{"run_gear_id": 5, "ride_gear_id": 7}],
                {5: 10, 7: 20},
            )
        assert service.counts["user_default_gear"] == 1

    async def test_collect_and_import_user_integrations_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        await service.collect_and_import_user_integrations([])
        assert service.counts.get("user_integrations", 0) == 0

    async def test_collect_and_import_user_goals_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        await service.collect_and_import_user_goals([])
        assert service.counts.get("user_goals", 0) == 0

    async def test_collect_and_import_user_privacy_settings_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        await service.collect_and_import_user_privacy_settings([])
        assert service.counts.get("user_privacy_settings", 0) == 0

    async def test_collect_and_import_user_data(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with (
            patch(
                "modules.users.users_profile.import_service.users_crud.edit_profile_user",
                new_callable=AsyncMock,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch(
            "modules.users.users_profile.import_service.user_integrations_crud.edit_user_integrations",
        ):
            await service.collect_and_import_user_integrations([{"strava_sync_gear": True}])

        assert service.counts["user_integrations"] == 1

    async def test_collect_and_import_user_goals(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch("modules.users.users_profile.import_service.user_goals_crud.create_user_goal"):
            await service.collect_and_import_user_goals(
                [{"interval": "daily", "activity_type": "run", "goal_type": "distance", "goal_distance": 5000}]
            )

        assert service.counts["user_goals"] == 1

    async def test_collect_and_import_user_privacy_settings(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch(
            "modules.users.users_profile.import_service.users_privacy_settings_crud.edit_user_privacy_settings",
        ):
            await service.collect_and_import_user_privacy_settings([{"hide_activity_map": True}])

        assert service.counts["user_privacy_settings"] == 1

    async def test_crafted_zip_cannot_recreate_identity_links(self) -> None:
        """A crafted profile ZIP with identity-provider data must not recreate identity links."""
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
            "modules.users.users_profile.import_service.users_crud.edit_profile_user",
            new_callable=AsyncMock,
        ) as mock_edit_profile:
            result = await service.import_from_zip_data(zip_data)

        assert result["detail"] == "Import completed"
        mock_edit_profile.assert_awaited_once()
        assert service.counts["user"] == 1
        assert service.counts.get("user_identity_providers", 0) == 0


class TestImportServiceHealth:
    async def test_collect_and_import_health_weight(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_health_target = MagicMock()
        mock_health_target.id = 1

        with (
            patch("modules.users.users_profile.import_service.health_weight_crud.create_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_crud.get_health_targets_by_user_id",
                return_value=mock_health_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_crud.edit_health_target"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": 75.5}],
                [{"weight": 80.0, "steps": 10000}],
            )

        assert service.counts["health_weight"] == 1
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_weight_string_conversion_errors(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_target = MagicMock()
        mock_target.id = 1

        with (
            patch("modules.users.users_profile.import_service.health_weight_crud.create_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_crud.get_health_targets_by_user_id",
                return_value=mock_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_crud.edit_health_target"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": "abc", "physique_rating": "xyz", "metabolic_age": "invalid"}],
                [{"weight": "bad", "steps": "wrong", "sleep": "nope"}],
            )

        assert service.counts["health_weight"] == 1
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_weight_no_targets(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with (
            patch("modules.users.users_profile.import_service.health_weight_crud.create_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_crud.get_health_targets_by_user_id",
                return_value=None,
            ),
            patch("modules.users.users_profile.import_service.health_targets_crud.create_health_targets"),
        ):
            await service.collect_and_import_health_weight(
                [{"weight": 75.5}],
                [],
            )

        assert service.counts["health_weight"] == 1


class TestImportServiceActivities:
    async def test_collect_and_import_activities_batched_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
    async def test_collect_and_import_activity_components_empty_laps(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        await service.collect_and_import_activity_components(
            [],
            [],
            [],
            [],
            [],
            [],
            1,
            10,
        )
        assert service.counts.get("activity_laps", 0) == 0

    async def test_collect_and_import_activity_components_with_laps(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_activity = MagicMock(id=10, user_id=1)
        with patch("modules.users.users_profile.import_service.activities_integration.restore_activity_laps"):
            await service.collect_and_import_activity_components(
                [{"activity_id": 1, "lap_index": 1}],
                [],
                [],
                [],
                [],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_laps") == 1

    async def test_collect_and_import_activity_components_with_sets(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_activity = MagicMock(id=10, user_id=1)
        with patch("modules.users.users_profile.import_service.activities_integration.restore_activity_sets"):
            await service.collect_and_import_activity_components(
                [],
                [{"activity_id": 1, "duration": 30.0, "set_type": "manual", "start_time": "2024-01-01T00:00:00"}],
                [],
                [],
                [],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_sets") == 1

    async def test_collect_and_import_activity_components_with_streams(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_activity = MagicMock(id=10, user_id=1)
        with patch(
            "modules.users.users_profile.import_service.activities_integration.restore_activity_streams",
        ):
            await service.collect_and_import_activity_components(
                [],
                [],
                [{"activity_id": 1, "stream_type": 1, "stream_waypoints": []}],
                [],
                [],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_streams") == 1

    async def test_collect_and_import_activity_components_with_workout_steps(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_activity = MagicMock(id=10, user_id=1)
        with patch("modules.users.users_profile.import_service.activities_integration.restore_activity_workout_steps"):
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [{"activity_id": 1, "message_index": 0, "duration_type": "time"}],
                [],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_workout_steps") == 1

    async def test_collect_and_import_activity_components_with_exercise_titles(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_activity = MagicMock(id=10, user_id=1)
        with patch("modules.users.users_profile.import_service.activities_integration.restore_exercise_titles"):
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [],
                [],
                [{"activity_id": 1, "exercise_category": 1, "exercise_name": 1, "wkt_step_name": "Running"}],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_exercise_titles") == 1


class TestImportServiceFromZip:
    async def test_import_from_zip_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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

    async def test_import_from_zip_os_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_activity_files_from_zip(z, {"activity_files/abc.gpx"}, {})

    async def test_add_activity_media_from_zip_skips_non_numeric(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_activity_media_from_zip(z, {"activity_media/abc.jpg"}, {})

    async def test_add_user_images_from_zip(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            await service.add_user_images_from_zip(z, set())


class TestImportServiceReadZipEntryDecompressed:
    async def test_read_zip_entry_decompressed_exceeds_limit(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            result = service._load_components_for_batch(z, [], [], "laps")
        assert result == []

    def test_load_components_for_batch_success(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with (
            patch(
                "modules.users.users_profile.import_service.file_uploads.resolve_storage_path",
                return_value="/safe/path/10_photo.jpg",
            ),
            patch("modules.users.users_profile.import_service.activities_integration.restore_activity_media"),
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [],
                [{"activity_id": 1, "media_path": "1_photo.jpg", "media_type": 1}],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_media") == 1

    async def test_collect_and_import_activity_components_rejects_a_key_with_a_separator(self) -> None:
        """A key carrying a path separator is skipped.

        The archive is untrusted: such a value would address a blob outside the
        flat media area, where the deletion cleanup could never find it again.
        """
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch(
            "modules.users.users_profile.import_service.activities_integration.restore_activity_media"
        ) as mock_create:
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [],
                [{"activity_id": 1, "media_path": "../../etc/1_passwd.jpg", "media_type": 1}],
                [],
                1,
                mock_activity,
            )

        mock_create.assert_not_called()
        assert service.counts.get("activity_media", 0) == 0

    async def test_collect_and_import_activity_components_with_media_invalid_key(self) -> None:
        """A media entry whose key carries no ``{activity_id}_`` prefix is skipped."""
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch(
            "modules.users.users_profile.import_service.activities_integration.restore_activity_media"
        ) as mock_create:
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [],
                [{"activity_id": 1, "media_path": "nounderscore.jpg", "media_type": 1}],
                [],
                1,
                mock_activity,
            )

        mock_create.assert_not_called()
        assert service.counts.get("activity_media", 0) == 0

    async def test_collect_and_import_activity_components_with_media_multiple(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with (
            patch(
                "modules.users.users_profile.import_service.file_uploads.resolve_storage_path",
                return_value="/safe/path/10_photo.jpg",
            ),
            patch("modules.users.users_profile.import_service.activities_integration.restore_activity_media"),
        ):
            mock_activity = MagicMock(id=10, user_id=1)
            await service.collect_and_import_activity_components(
                [],
                [],
                [],
                [],
                [
                    {"activity_id": 1, "media_path": "1_a.jpg", "media_type": 1},
                    {"activity_id": 1, "media_path": "1_b.jpg", "media_type": 1},
                    {"activity_id": 2, "media_path": "2_c.jpg", "media_type": 1},
                ],
                [],
                1,
                mock_activity,
            )

        assert service.counts.get("activity_media") == 2


class TestImportServiceActivitiesDataBatched:
    async def test_collect_and_import_activities_batched_single_batch(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                "modules.users.users_profile.import_service.activities_integration.restore_activity",
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

    async def test_collect_and_import_activities_batched_no_original_id(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                "modules.users.users_profile.import_service.activities_integration.restore_activity",
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                "modules.users.users_profile.import_service.activity_file_storage_service.store_activity_file"
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("activity_files/999.gpx", b"<gpx></gpx>")
        zip_data = buf.getvalue()

        with (
            patch(
                "modules.users.users_profile.import_service.activity_file_storage_service.store_activity_file"
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

    async def test_add_activity_files_from_zip_http_exception(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                side_effect=HTTPException(status_code=400, detail="invalid file"),
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
            patch("modules.users.users_profile.import_service.platform_runtime") as runtime,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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

    async def test_add_activity_media_from_zip_http_exception(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                side_effect=HTTPException(status_code=400, detail="invalid image"),
            ),
            patch("modules.users.users_profile.import_service.platform_runtime") as runtime,
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
    async def test_add_user_images_from_zip_valid(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
            patch("modules.users.users_profile.import_service.platform_runtime") as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_user_images_from_zip(z, {"user_images/old_photo.jpg"})

        assert service.counts["user_images"] == 1
        # The archive's filename is discarded: the key is minted for the
        # importing user so a crafted ZIP cannot write over someone else's blob.
        runtime.get_active_platform.return_value.storage.save.assert_called_once_with(
            "user_images", "1.jpg", b"image-data"
        )

    async def test_add_user_images_from_zip_http_exception(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
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
                side_effect=HTTPException(status_code=400, detail="invalid image"),
            ),
            patch("modules.users.users_profile.import_service.platform_runtime") as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            await service.add_user_images_from_zip(z, {"user_images/old_photo.jpg"})

        assert service.counts.get("user_images", 0) == 0
        runtime.get_active_platform.return_value.storage.save.assert_not_called()


class TestImportServiceHealthEmptyBranches:
    async def test_collect_and_import_health_weight_empty_data(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        mock_target = MagicMock()
        mock_target.id = 1

        with (
            patch(
                "modules.users.users_profile.import_service.health_targets_crud.get_health_targets_by_user_id",
                return_value=mock_target,
            ),
            patch("modules.users.users_profile.import_service.health_targets_crud.edit_health_target"),
        ):
            await service.collect_and_import_health_weight([], [{"weight": 80.0}])

        assert service.counts.get("health_weight", 0) == 0
        assert service.counts["health_targets"] == 1

    async def test_collect_and_import_health_targets_no_current(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with (
            patch("modules.users.users_profile.import_service.health_weight_crud.create_health_weight"),
            patch(
                "modules.users.users_profile.import_service.health_targets_crud.get_health_targets_by_user_id",
                return_value=None,
            ),
            patch("modules.users.users_profile.import_service.health_targets_crud.edit_health_target"),
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
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )

        with patch("modules.users.users_profile.import_service.health_weight_crud.create_health_weight"):
            await service.collect_and_import_health_weight([{"weight": 75.5}], [])

        assert service.counts["health_weight"] == 1
        assert service.counts.get("health_targets", 0) == 0


class TestImportServiceFromZipExtended:
    async def test_import_from_zip_json_decode_error(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_ws = MagicMock()
        service = profile_import_service.ImportService(
            user_id=1,
            db=mock_db,
            websocket_manager=mock_ws,
        )
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/gears.json", "not-valid-json")
        zip_data = buf.getvalue()

        with pytest.raises(JSONParseError, match="Failed to parse JSON"):
            await service.import_from_zip_data(zip_data)
