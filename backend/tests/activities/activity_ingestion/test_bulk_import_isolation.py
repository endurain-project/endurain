"""Tests for per-user bulk-import directory isolation."""

import os
from unittest.mock import MagicMock, patch

import core.config as core_config
import modules.activities.activity_ingestion.router as router
import modules.activities.activity_ingestion.sources as sources


class TestBulkImportDirResolution:
    def test_each_user_gets_their_own_directory(self):
        assert core_config.bulk_import_dir_for(7) != core_config.bulk_import_dir_for(8)
        assert core_config.bulk_import_dir_for(7).endswith("/7")

    def test_the_user_id_is_always_a_single_path_segment(self):
        """Coerced to int, so nothing user-controlled can widen the path."""
        assert core_config.bulk_import_dir_for("7") == core_config.bulk_import_dir_for(7)  # type: ignore[arg-type]
        assert "/" not in core_config.bulk_import_dir_for(7).rsplit("/", 1)[1]

    def test_the_error_directory_lives_under_the_user_directory(self):
        assert core_config.bulk_import_error_dir_for(7).startswith(core_config.bulk_import_dir_for(7))


class TestBulkImportSourceErrorDirectory:
    def test_a_generic_import_uses_the_owners_error_directory(self):
        source = sources.BulkImportSource(import_initiated_time="2026", user_id=7)
        assert source.error_directory == core_config.bulk_import_error_dir_for(7)

    def test_a_strava_export_keeps_its_own_directory(self):
        source = sources.BulkImportSource(import_initiated_time="2026", user_id=7, strava_activities={"a.fit": {}})
        assert source.error_directory == core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR

    def test_falls_back_to_the_shared_directory_without_an_owner(self):
        """Nothing should construct it this way, but it must not build a '/None' path."""
        source = sources.BulkImportSource(import_initiated_time="2026")
        assert source.error_directory == core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR


class TestStrandedRootFiles:
    def test_warns_instead_of_importing_files_left_in_the_shared_root(self, tmp_path):
        """Importing them would attribute one user's files to whoever ran the import."""
        root = tmp_path / "bulk_import"
        root.mkdir()
        (root / "someone_elses.fit").write_bytes(b"x")

        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(root)),
            patch.object(router, "logger") as log,
        ):
            router._warn_about_unowned_bulk_import_files(7)

        assert log.warning.called
        assert "someone_elses.fit" not in str(log.warning.call_args)
        # The operator is told where to move them.
        assert str(7) in str(log.warning.call_args)

    def test_stays_quiet_when_the_root_is_clean(self, tmp_path):
        root = tmp_path / "bulk_import"
        root.mkdir()
        (root / "7").mkdir()

        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(root)),
            patch.object(router, "logger") as log,
        ):
            router._warn_about_unowned_bulk_import_files(7)

        log.warning.assert_not_called()

    def test_ignores_unsupported_files_in_the_root(self, tmp_path):
        root = tmp_path / "bulk_import"
        root.mkdir()
        (root / "readme.txt").write_bytes(b"x")

        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(root)),
            patch.object(router, "logger") as log,
        ):
            router._warn_about_unowned_bulk_import_files(7)

        log.warning.assert_not_called()

    def test_a_missing_root_is_not_an_error(self, tmp_path):
        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(tmp_path / "nope")),
            patch.object(router, "logger") as log,
        ):
            router._warn_about_unowned_bulk_import_files(7)

        log.warning.assert_not_called()


class TestBulkImportRouteScoping:
    def test_the_route_scans_only_the_callers_directory(self, tmp_path):
        db = MagicMock()
        user_dir = tmp_path / "bulk_import" / "3"
        user_dir.mkdir(parents=True)

        with (
            patch.object(router.core_config, "bulk_import_dir_for", return_value=str(user_dir)) as resolve,
            patch.object(router, "_warn_about_unowned_bulk_import_files"),
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_files"),
            patch.object(router.os, "listdir", return_value=[]),
        ):
            router.create_activity_with_bulk_import(request=MagicMock(), token_user_id=3, _check_scopes=None, db=db)

        # Resolved from the token's user, never from client input.
        resolve.assert_called_once_with(3)

    def test_files_are_queued_from_the_user_directory(self, tmp_path):
        db = MagicMock()
        user_dir = tmp_path / "bulk_import" / "3"
        user_dir.mkdir(parents=True)
        (user_dir / "ride.gpx").write_bytes(b"<gpx/>")

        with (
            patch.object(router.core_config, "bulk_import_dir_for", return_value=str(user_dir)),
            patch.object(router, "_warn_about_unowned_bulk_import_files"),
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
        ):
            router.create_activity_with_bulk_import(request=MagicMock(), token_user_id=3, _check_scopes=None, db=db)

        queued = publish.call_args.args[0]
        assert queued == [os.path.join(str(user_dir), "ride.gpx")]
