"""Tests for profile data import service."""

import contextlib
import json
import uuid
import zipfile
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.gears.gear.constants as gear_constants
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear_components.constants as gear_components_constants
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.import_service as profile_import_service
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    ImportAccountMismatchError,
    JSONParseError,
)


@contextlib.contextmanager
def _storage_of(service):
    """Expose a service's storage provider the way the old runtime patch did."""
    runtime = MagicMock()
    runtime.get_active_platform.return_value.storage = service.storage
    yield runtime


@pytest.fixture(autouse=True)
def _gear_sections():
    """Register the gear sections the import runs, as composition does."""
    users_contributor_registry.clear()
    for key, restore in (
        (gear_constants.PROFILE_ARCHIVE_KEY, gear_integration.restore_profile_gears),
        (gear_components_constants.PROFILE_ARCHIVE_KEY, gear_components_integration.restore_profile_gear_components),
    ):
        users_contributor_registry.register_profile_section(
            users_profile_contracts.ProfileRecordsSection(key=key, export=lambda user_id, db: [], restore=restore)
        )
    yield
    users_contributor_registry.clear()


def _reader(service, z: zipfile.ZipFile) -> profile_utils.ZipArchiveReader:
    """Wrap an open archive the way the import does, with the service's limits."""
    config = service.performance_config
    return profile_utils.ZipArchiveReader(
        z,
        max_json_bytes=int(config.max_json_mb * 1024 * 1024),
        max_uncompressed_bytes=int(config.max_uncompressed_mb * 1024 * 1024),
        max_memory_mb=config.max_memory_mb,
        enable_memory_monitoring=config.enable_memory_monitoring,
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


@pytest.fixture(autouse=True)
def _process_memory_is_not_the_suites(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read no process memory: the pytest process holds what earlier tests allocated, which these tests are not about."""
    monkeypatch.setattr("modules.users.users_profile.utils.get_memory_usage_mb", lambda *_args, **_kwargs: 0.0)


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
    def test_file_size_exceeds_limit(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.max_file_size_mb = 0.001

        with pytest.raises(FileSizeError, match="exceeds maximum"):
            service.import_from_zip_data(b"x" * 2000)

    def test_bad_zip_format(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.max_file_size_mb = 100

        with pytest.raises(FileFormatError, match="Invalid ZIP"):
            service.import_from_zip_data(b"not-a-zip")


class _PastTheCheckError(Exception):
    """Stands in for the import going on once the account check has passed."""


class TestImportServiceAccountCheck:
    """An archive is imported only into the account it was exported from."""

    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    def _run(self, archived: dict[str, str], current: dict[str, str]) -> profile_import_service.ImportService:
        service = self._service()
        zip_data = _make_zip_with_json({"data/user.json": [archived], "data/gears.json": [{"nickname": "x"}]})
        account = MagicMock(**current)
        with (
            patch("modules.users.users_profile.import_service.users_integration.require_user", return_value=account),
            patch.object(service, "collect_and_import_user_data", side_effect=_PastTheCheckError) as gears,
        ):
            try:
                service.import_from_zip_data(zip_data)
            except ImportAccountMismatchError:
                gears.assert_not_called()
                service.db.commit.assert_not_called()
                raise
        return service

    def test_an_archive_from_another_account_is_refused_before_anything_is_imported(self) -> None:
        with pytest.raises(ImportAccountMismatchError):
            self._run(
                {"username": "source", "email": "source@example.com"},
                {"username": "other", "email": "other@example.com"},
            )

    def test_the_same_account_passes_the_check(self) -> None:
        with pytest.raises(_PastTheCheckError):
            self._run(
                {"username": "Source", "email": "source@example.com"},
                {"username": "source", "email": "source@example.com"},
            )

    def test_a_renamed_account_still_matches_by_email(self) -> None:
        with pytest.raises(_PastTheCheckError):
            self._run(
                {"username": "old_name", "email": "me@example.com"},
                {"username": "new_name", "email": "ME@example.com"},
            )


class TestImportServiceArchiveCaps:
    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    def test_an_archive_with_too_many_entries_is_refused_before_anything_is_read(self) -> None:
        service = self._service()
        service.performance_config.max_entries = 2
        zip_data = _make_zip_with_json({f"data/f{i}.json": [] for i in range(3)})

        with pytest.raises(FileSizeError, match="entries"):
            service.import_from_zip_data(zip_data)


class TestImportedRowsLoseTheirIdentity:
    """An archive's rows carry the exporting account's id, owner and version, which an import must not write."""

    def _service(self) -> profile_import_service.ImportService:
        return profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

    def test_a_goal_exported_with_its_version_is_still_imported(self) -> None:
        service = self._service()
        row = {
            "id": str(uuid.uuid4()),
            "user_id": 3,
            "version": 4,
            "interval": "weekly",
            "activity_type": "run",
            "goal_type": "calories",
            "goal_calories": 5000,
        }

        with patch.object(profile_import_service.users_goals_integration, "create_goal") as create:
            service.collect_and_import_user_goals([row])

        create.assert_called_once()
        assert service.counts["user_goals"] == 1

    def test_privacy_settings_exported_with_their_version_are_still_imported(self) -> None:
        service = self._service()
        row = {"id": str(uuid.uuid4()), "user_id": 3, "version": 4, "hide_activity_map": True}

        with patch.object(profile_import_service.users_privacy_settings_integration, "edit_privacy_settings") as edit:
            service.collect_and_import_user_privacy_settings([row])

        edit.assert_called_once()
        assert service.counts["user_privacy_settings"] == 1

    def test_the_discoverable_choice_is_imported_and_an_old_archive_without_it_leaves_it_alone(self) -> None:
        service = self._service()

        with patch.object(profile_import_service.users_privacy_settings_integration, "edit_privacy_settings") as edit:
            service.collect_and_import_user_privacy_settings([{"discoverable": False}])
            service.collect_and_import_user_privacy_settings([{"hide_activity_map": True}])

        imported, old_archive = (call.args[1] for call in edit.call_args_list)
        assert imported.model_dump(exclude_unset=True) == {"discoverable": False}
        assert "discoverable" not in old_archive.model_dump(exclude_unset=True)


class TestImportServiceUserData:
    def test_import_user_default_gear_empty(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        with patch(
            "modules.users.users_profile.import_service.users_default_gear_integration.restore_profile_default_gear"
        ) as restore:
            service.import_user_default_gear([], {})
        restore.assert_not_called()
        assert service.counts["user_default_gear"] == 0

    def test_import_user_default_gear_counts_a_staged_record(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=mock_db)
        archived = str(uuid.uuid4())
        ids = {"gears": {archived: uuid.uuid4()}}
        with patch(
            "modules.users.users_profile.import_service.users_default_gear_integration.restore_profile_default_gear",
            return_value=True,
        ) as restore:
            service.import_user_default_gear([{"run_gear_id": archived}], ids)
        restore.assert_called_once_with({"run_gear_id": archived}, ids, 1, mock_db)
        assert service.counts["user_default_gear"] == 1

    def test_import_user_default_gear_does_not_count_a_skipped_record(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        with patch(
            "modules.users.users_profile.import_service.users_default_gear_integration.restore_profile_default_gear",
            return_value=False,
        ):
            service.import_user_default_gear([{"unknown_field": 1}], {})
        assert service.counts["user_default_gear"] == 0

    def test_collect_and_import_user_integrations_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.collect_and_import_user_integrations([])
        assert service.counts.get("user_integrations", 0) == 0

    def test_goals_the_user_already_has_or_that_are_invalid_are_skipped(self) -> None:
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
            service.collect_and_import_user_goals(goals)

        assert create.call_count == 2
        assert service.counts["user_goals"] == 1

    def test_invalid_singleton_settings_are_skipped_not_fatal(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        base = "modules.users.users_profile.import_service"
        with (
            patch(f"{base}.users_privacy_settings_integration.edit_privacy_settings") as privacy,
            patch(f"{base}.user_integrations_integration.edit_integrations") as integrations,
        ):
            service.collect_and_import_user_privacy_settings([{"default_activity_visibility": "bogus"}])
            service.collect_and_import_user_integrations([{"strava_sync_gear": "not-a-bool"}])

        privacy.assert_not_called()
        integrations.assert_not_called()
        assert service.counts["user_privacy_settings"] == 0

    def test_collect_and_import_user_goals_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.collect_and_import_user_goals([])
        assert service.counts.get("user_goals", 0) == 0

    def test_collect_and_import_user_privacy_settings_empty(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.collect_and_import_user_privacy_settings([])
        assert service.counts.get("user_privacy_settings", 0) == 0

    def test_collect_and_import_user_data(self) -> None:
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
            patch.object(service, "collect_and_import_user_goals"),
            patch.object(service, "collect_and_import_user_integrations"),
            patch.object(service, "collect_and_import_user_privacy_settings"),
        ):
            service.collect_and_import_user_data(
                [{"photo_path": "data/user_images/old_user.jpg"}],
                [],
                [],
                [],
            )

        assert service.counts["user"] == 1

    def _imported_profile(self, user_row: dict[str, Any]) -> Any:
        """Imports one archived user row and returns the profile update it staged."""
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        with (
            patch("modules.users.users_profile.import_service.users_integration.edit_profile") as mock_edit,
            patch.object(service, "collect_and_import_user_goals"),
            patch.object(service, "collect_and_import_user_integrations"),
            patch.object(service, "collect_and_import_user_privacy_settings"),
        ):
            service.collect_and_import_user_data([user_row], [], [], [])
        return mock_edit.call_args.args[1]

    def test_an_archive_never_renames_the_account(self) -> None:
        profile = self._imported_profile({"username": "someone_else", "city": "Porto"})

        assert profile.model_dump(exclude_unset=True) == {"city": "Porto"}

    def test_an_archive_carries_the_weight_units_override_over(self) -> None:
        profile = self._imported_profile({"units": "metric", "weight_units": "imperial"})

        assert profile.model_dump(exclude_unset=True) == {"units": "metric", "weight_units": "imperial"}

    def test_an_archive_without_weight_units_leaves_the_override_untouched(self) -> None:
        profile = self._imported_profile({"units": "imperial"})

        assert "weight_units" not in profile.model_fields_set

    def test_collect_and_import_user_data_empty_still_imports_sub_settings(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with (
            patch.object(service, "collect_and_import_user_goals") as mock_goals,
            patch.object(service, "collect_and_import_user_integrations") as mock_int,
            patch.object(service, "collect_and_import_user_privacy_settings") as mock_priv,
        ):
            service.collect_and_import_user_data([], [], [], [])

        assert service.counts.get("user", 0) == 0
        mock_goals.assert_called_once()
        mock_int.assert_called_once()
        mock_priv.assert_called_once()

    def test_collect_and_import_user_integrations(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch(
            "modules.users.users_profile.import_service.user_integrations_integration.edit_integrations",
        ):
            service.collect_and_import_user_integrations([{"strava_sync_gear": True}])

        assert service.counts["user_integrations"] == 1

    def test_user_integrations_import_drops_credentials_and_oauth_state(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        crafted = {
            "id": str(uuid.uuid4()),
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
            service.collect_and_import_user_integrations([crafted])

        applied = mock_edit.call_args.args[0]
        assert applied.model_dump(exclude_unset=True) == {"strava_sync_gear": True, "garminconnect_sync_gear": False}

    def test_user_integrations_import_with_only_credentials_imports_nothing(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))

        with patch(
            "modules.users.users_profile.import_service.user_integrations_integration.edit_integrations",
        ) as mock_edit:
            service.collect_and_import_user_integrations([{"strava_token": "stolen"}])

        mock_edit.assert_not_called()
        assert service.counts["user_integrations"] == 0

    def test_collect_and_import_user_goals(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch("modules.users.users_profile.import_service.users_goals_integration.create_goal"):
            service.collect_and_import_user_goals(
                [{"interval": "daily", "activity_type": "run", "goal_type": "distance", "goal_distance": 5000}]
            )

        assert service.counts["user_goals"] == 1

    def test_collect_and_import_user_privacy_settings(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )

        with patch(
            "modules.users.users_profile.import_service.users_privacy_settings_integration.edit_privacy_settings",
        ):
            service.collect_and_import_user_privacy_settings([{"hide_activity_map": True}])

        assert service.counts["user_privacy_settings"] == 1

    def test_crafted_zip_cannot_recreate_identity_links(self) -> None:
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
            }
        )

        assert not hasattr(service, "collect_and_import_user_identity_providers")
        with patch(
            "modules.users.users_profile.import_service.users_integration.edit_profile",
        ) as mock_edit_profile:
            result = service.import_from_zip_data(zip_data)

        assert result is service.counts
        mock_edit_profile.assert_called_once()
        assert service.counts["user"] == 1
        assert service.counts.get("user_identity_providers", 0) == 0


class TestImportServiceFromZip:
    def test_import_from_zip_success(self) -> None:
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
            }
        )

        def _increment_gears(*_args):
            service.counts["gears"] = 1
            return []

        with (
            patch(
                "modules.users.users_profile.import_service.users_integration.require_user",
                return_value=MagicMock(username="test", email="test@example.com"),
            ),
            patch.object(service, "restore_profile_sections", side_effect=_increment_gears),
            patch.object(service, "collect_and_import_user_data"),
            patch.object(service, "add_user_images_from_zip"),
        ):
            result = service.import_from_zip_data(zip_data)

        assert result is service.counts

    @staticmethod
    def _atomic_service():
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=mock_db)
        service.performance_config.enable_memory_monitoring = False
        service.performance_config.max_file_size_mb = 100
        return service, mock_db

    def test_the_database_part_commits_once_before_any_file_is_written(self) -> None:
        service, mock_db = self._atomic_service()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        zip_data = _make_zip_with_json({"data/gears.json": [{"id": 1, "nickname": "Bike"}]})
        section_files = MagicMock()

        with (
            patch.object(service, "restore_profile_sections", return_value=[section_files]) as gears,
            patch.object(service, "add_user_images_from_zip") as images,
        ):
            order.attach_mock(gears, "gears")
            order.attach_mock(section_files, "files")
            order.attach_mock(images, "images")
            service.counts["gears"] = 1
            service.import_from_zip_data(zip_data)

        names = [call[0] for call in order.mock_calls]
        assert names.count("commit") == 1
        assert names.index("commit") < names.index("files") < names.index("images")
        mock_db.rollback.assert_not_called()

    @pytest.mark.parametrize("failing", ["restore_profile_sections", "collect_and_import_user_data"])
    def test_a_failure_in_the_database_part_rolls_everything_back(self, failing) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": []})
        section_files = MagicMock()

        with (
            patch.object(service, "restore_profile_sections", return_value=[section_files]),
            patch.object(
                service,
                failing,
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            service.import_from_zip_data(zip_data)

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()
        section_files.assert_not_called()

    def test_a_failure_writing_files_keeps_the_committed_rows(self) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": []})

        with (
            patch.object(service, "restore_profile_sections", return_value=[MagicMock(side_effect=OSError("disk"))]),
            pytest.raises(FileSystemError),
        ):
            service.import_from_zip_data(zip_data)

        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_an_archive_with_nothing_to_import_is_rejected_before_the_commit(self) -> None:
        service, mock_db = self._atomic_service()
        zip_data = _make_zip_with_json({"data/gears.json": []})

        with (
            patch.object(service, "restore_profile_sections", return_value=[]),
            pytest.raises(FileFormatError, match="zero items"),
        ):
            service.import_from_zip_data(zip_data)

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()

    def test_the_commit_callback_fires_once_the_rows_are_committed(self) -> None:
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
            patch.object(service, "restore_profile_sections", return_value=[]),
            patch.object(service, "add_user_images_from_zip"),
        ):
            service.counts["user_images"] = 1
            service.import_from_zip_data(zip_data)

        assert calls == [1]

    def test_a_rejected_archive_rolls_back(self) -> None:
        service, mock_db = self._atomic_service()

        with pytest.raises(FileFormatError):
            service.import_from_zip_data(b"not a zip")

        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_called_once()

    def test_import_from_zip_os_error(self) -> None:
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
            patch.object(service, "restore_profile_sections", side_effect=OSError("disk full")),
            pytest.raises(FileSystemError),
        ):
            service.import_from_zip_data(zip_data)

    def test_import_from_zip_all_empty_raises_error(self) -> None:
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
            }
        )

        with (
            patch.object(service, "restore_profile_sections", return_value=[]),
            patch.object(service, "collect_and_import_user_data"),
            patch.object(service, "add_user_images_from_zip"),
            pytest.raises(FileFormatError, match="zero items"),
        ):
            service.import_from_zip_data(zip_data)


class TestImportServiceFiles:
    def test_add_user_images_from_zip(self) -> None:
        mock_db = MagicMock(spec=Session)
        service = profile_import_service.ImportService(
            user_id=1,
            storage=MagicMock(),
            db=mock_db,
        )
        service.performance_config.enable_memory_monitoring = False

        zip_data = _make_zip_with_json({})
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            service.add_user_images_from_zip(_reader(service, z))


class TestImportServiceAddUserImages:
    def test_add_user_images_from_zip_accepts_webp_like_the_upload_does(self) -> None:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("user_images/photo.WEBP", b"image-data")
        mock_validator = MagicMock()
        mock_validator.config.limits.max_image_size = 1000000

        with (
            patch("modules.users.users_profile.import_service.file_uploads.file_validator", mock_validator),
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes_sync"),
            patch("modules.users.users_profile.import_service.users_integration.store_user_photo") as mock_store,
            zipfile.ZipFile(BytesIO(buf.getvalue())) as z,
        ):
            service.add_user_images_from_zip(_reader(service, z))

        assert mock_store.call_args.args[:3] == (1, ".webp", b"image-data")

    def test_add_user_images_from_zip_valid(self) -> None:
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
            patch("modules.users.users_profile.import_service.file_uploads.validate_bytes_sync"),
            patch("modules.users.users_profile.import_service.users_integration.store_user_photo") as mock_store,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            service.add_user_images_from_zip(_reader(service, z))

        assert service.counts["user_images"] == 1
        # The archive's filename is discarded: the key is minted for the
        # importing user so a crafted ZIP cannot write over someone else's blob.
        mock_store.assert_called_once_with(1, ".jpg", b"image-data", service.storage, mock_db)

    def test_add_user_images_from_zip_domain_error(self) -> None:
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
                "modules.users.users_profile.import_service.file_uploads.validate_bytes_sync",
                side_effect=core_exceptions.InvalidInputError("invalid image"),
            ),
            _storage_of(service) as runtime,
            zipfile.ZipFile(BytesIO(zip_data)) as z,
        ):
            service.add_user_images_from_zip(_reader(service, z))

        assert service.counts.get("user_images", 0) == 0
        runtime.get_active_platform.return_value.storage.save.assert_not_called()


class TestImportServiceFromZipExtended:
    def test_import_from_zip_json_decode_error(self) -> None:
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
            service.import_from_zip_data(zip_data)


class TestImportServiceProfileSections:
    """The import runs the registered sections in order and keeps what they report."""

    @staticmethod
    def _service() -> profile_import_service.ImportService:
        service = profile_import_service.ImportService(user_id=1, storage=MagicMock(), db=MagicMock(spec=Session))
        service.performance_config.enable_memory_monitoring = False
        return service

    @staticmethod
    def _archive(files: dict[str, object], service) -> profile_utils.ZipArchiveReader:
        return _reader(service, zipfile.ZipFile(BytesIO(_make_zip_with_json(files))))

    def test_a_records_section_restores_its_entry_and_its_count_is_kept(self) -> None:
        users_contributor_registry.clear()
        restore = MagicMock(return_value=2)
        users_contributor_registry.register_profile_section(
            users_profile_contracts.ProfileRecordsSection(key="extra", export=lambda u, d: [], restore=restore)
        )
        service = self._service()
        ids: users_profile_contracts.ProfileIdMaps = {}

        files = service.restore_profile_sections(
            self._archive({"data/extra.json": [{"id": 1}, {"id": 2}]}, service), ids, lambda: None
        )

        restore.assert_called_once_with([{"id": 1}, {"id": 2}], 1, ids, service.db)
        assert service.counts["extra"] == 2
        assert files == []

    def test_a_section_without_an_entry_restores_nothing_and_reports_zero(self) -> None:
        users_contributor_registry.clear()
        restore = MagicMock(return_value=0)
        users_contributor_registry.register_profile_section(
            users_profile_contracts.ProfileRecordsSection(key="extra", export=lambda u, d: [], restore=restore)
        )
        service = self._service()

        service.restore_profile_sections(self._archive({}, service), {}, lambda: None)

        assert restore.call_args.args[0] == []
        assert service.counts["extra"] == 0

    def test_sections_run_in_order_and_a_later_one_reads_the_ids_of_an_earlier_one(self) -> None:
        users_contributor_registry.clear()
        seen: list[object] = []

        def first(records, user_id, ids, db) -> int:
            ids["first"] = {1: 10}
            return 1

        def second(records, user_id, ids, db) -> int:
            seen.append(dict(ids))
            return 0

        for key, restore in (("first", first), ("second", second)):
            users_contributor_registry.register_profile_section(
                users_profile_contracts.ProfileRecordsSection(key=key, export=lambda u, d: [], restore=restore)
            )
        service = self._service()
        timeouts: list[int] = []

        service.restore_profile_sections(self._archive({}, service), {}, lambda: timeouts.append(1))

        assert seen == [{"first": {1: 10}}]
        assert len(timeouts) == 2

    def test_an_archive_section_gets_the_context_and_its_files_are_returned(self) -> None:
        users_contributor_registry.clear()
        after_commit = MagicMock()
        contexts: list[users_profile_contracts.ProfileImportContext] = []

        def restore(context):
            contexts.append(context)
            return after_commit

        users_contributor_registry.register_profile_section(
            users_profile_contracts.ProfileArchiveSection(key="extra", export=lambda c: None, restore=restore)
        )
        service = self._service()
        service.performance_config.max_activities = 1
        ids: users_profile_contracts.ProfileIdMaps = {}

        files = service.restore_profile_sections(self._archive({}, service), ids, lambda: None)

        assert files == [after_commit]
        after_commit.assert_not_called()
        context = contexts[0]
        assert (context.user_id, context.db, context.counts, context.ids) == (1, service.db, service.counts, ids)
        assert context.batch_size == service.performance_config.batch_size
        context.check_activity_count(1)
        with pytest.raises(ActivityLimitError):
            context.check_activity_count(2)

    def test_the_files_of_a_section_are_written_after_the_commit(self) -> None:
        users_contributor_registry.clear()
        after_commit = MagicMock()
        users_contributor_registry.register_profile_section(
            users_profile_contracts.ProfileArchiveSection(
                key="extra", export=lambda c: None, restore=lambda c: after_commit
            )
        )
        service = self._service()
        service.performance_config.max_file_size_mb = 100
        order = MagicMock()
        order.attach_mock(service.db.commit, "commit")
        order.attach_mock(after_commit, "files")

        with (
            patch.object(service, "add_user_images_from_zip"),
        ):
            service.import_from_zip_data(_make_zip_with_json({"data/user.json": []}))

        assert [call[0] for call in order.mock_calls] == ["commit", "files"]
