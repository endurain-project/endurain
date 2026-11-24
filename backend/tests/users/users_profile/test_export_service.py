"""The profile export on the real database: what the archive carries, and how a build fails."""

import io
import json
import os
import zipfile

import pytest
from sqlalchemy import column, delete, text
from sqlalchemy import table as sa_table

import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_service as export_service
from tests._factories.gears import make_gear
from tests._factories.goals import make_goal
from tests._factories.profile import FaultyStorage, png
from tests._factories.users import make_user

#: The pytest process holds what earlier tests allocated, which the memory limit is not about.
_ROOMY = {"max_memory_mb": 1_000_000}


@pytest.fixture
def storage(_publish_local_platform):
    return _publish_local_platform.storage


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, city="Porto")
        make_goal(db, created.id)
        make_gear(db, created.id)
        db.commit()
    return created


def _build(committed_sessions, storage, user_id, **config):
    """Build the archive the way the export does and return its entries."""
    settings = {**_ROOMY, **config}
    with committed_sessions() as db:
        exporter = export_service.ExportService(
            user_id, storage, db, export_service.ExportPerformanceConfig(**settings)
        )
        archive = exporter.build_export_archive({"id": str(user_id), "city": "Porto"})
        with archive:
            data = archive.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zipf:
        return {name: zipf.read(name) for name in zipf.namelist()}


def _rows(entries, name):
    return json.loads(entries[name])


class TestArchiveContents:
    def test_every_section_the_account_has_is_in_the_archive_with_its_count(self, committed_sessions, storage, owner):
        entries = _build(committed_sessions, storage, owner.id)

        counts = _rows(entries, "counts.json")[0]
        assert _rows(entries, "data/user.json") == [{"id": str(owner.id), "city": "Porto"}]
        assert len(_rows(entries, "data/gears.json")) == counts["gears"] == 1
        assert len(_rows(entries, "data/user_goals.json")) == counts["user_goals"] == 1
        assert _rows(entries, "data/user_privacy_settings.json")[0]["default_activity_visibility"] == "private"
        assert _rows(entries, "data/user_default_gear.json")[0]["user_id"] == str(owner.id)

    def test_only_the_sync_preferences_of_the_integrations_are_exported(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            integrations_integration.link_strava_account(
                owner.id, {"access_token": "a", "refresh_token": "r", "expires_at": 1_900_000_000}, db
            )
            integrations_integration.link_garminconnect_account(owner.id, {"di_token": "secret"}, db)
            integrations_integration.set_strava_sync_gear(owner.id, True, db)
            db.commit()

        entries = _build(committed_sessions, storage, owner.id)

        assert _rows(entries, "data/user_integrations.json") == [
            {"strava_sync_gear": True, "garminconnect_sync_gear": False}
        ]
        assert "secret" not in b"".join(entries.values()).decode(errors="ignore")

    def test_identity_providers_are_not_in_the_archive(self, committed_sessions, storage, owner):
        entries = _build(committed_sessions, storage, owner.id)

        assert not [name for name in entries if "identity" in name]

    def test_settings_the_account_does_not_have_are_written_as_empty_lists(self, committed_sessions, storage):
        with committed_sessions() as db:
            bare = make_user(db)
            for table in ("users_default_gear", "users_privacy_settings", "users_integrations", "users_goals"):
                db.execute(delete(sa_table(table, column("user_id"))).where(column("user_id") == bare.id))
            db.commit()

        entries = _build(committed_sessions, storage, bare.id)

        for name in ("user_default_gear", "user_privacy_settings", "user_integrations", "user_goals"):
            assert _rows(entries, f"data/{name}.json") == []

    def test_the_photo_is_in_the_archive(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            users_integration.store_user_photo(owner.id, ".png", png(90, 8), storage, db)

        entries = _build(committed_sessions, storage, owner.id)

        stored = storage.get(users_constants.USER_IMAGE_STORAGE_AREA, f"{owner.id}.png")
        assert stored is not None
        assert entries[f"user_images/{owner.id}.png"] == stored
        assert _rows(entries, "counts.json")[0]["user_images"] == 1

    def test_the_database_part_ends_before_the_storage_part_begins(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            users_integration.store_user_photo(owner.id, ".png", png(90, 8), storage, db)
        seen = []

        with committed_sessions() as db:

            class Watching(FaultyStorage):
                def __getattr__(self, name):
                    if name == "get":

                        def get(area, key):
                            seen.append(db.in_transaction())
                            return storage.get(area, key)

                        return get
                    return super().__getattr__(name)

            exporter = export_service.ExportService(
                owner.id, Watching(storage), db, export_service.ExportPerformanceConfig(**_ROOMY)
            )
            exporter.build_export_archive({"id": str(owner.id)}).close()

        assert seen == [False]


class TestFailures:
    def test_an_export_out_of_time_stops(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.ExportTimeoutError):
            _build(committed_sessions, storage, owner.id, timeout_seconds=-1)

    def test_a_memory_limit_that_is_exceeded_stops_the_export(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.MemoryAllocationError):
            _build(committed_sessions, storage, owner.id, max_memory_mb=0)

    def test_a_section_the_database_cannot_read_is_a_database_error(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            db.execute(text("DROP TABLE health_weight CASCADE"))
            db.commit()

        with pytest.raises(profile_exceptions.DatabaseConnectionError):
            _build(committed_sessions, storage, owner.id)

    def test_a_row_a_section_cannot_read_back_is_a_collection_error_naming_the_section(
        self, committed_sessions, storage, owner
    ):
        with committed_sessions() as db:
            db.execute(text("UPDATE gear SET gear_type = 99 WHERE user_id = :u"), {"u": owner.id})
            db.commit()

        with pytest.raises(profile_exceptions.DataCollectionError, match="gears"):
            _build(committed_sessions, storage, owner.id)

    @pytest.mark.parametrize(
        "drop",
        [
            "DROP TABLE users_goals CASCADE",
            "DROP TABLE users_privacy_settings CASCADE",
            "DROP TABLE users_integrations CASCADE",
            "DROP TABLE users_default_gear CASCADE",
        ],
    )
    def test_a_setting_that_cannot_be_read_is_a_collection_error(self, committed_sessions, storage, owner, drop):
        with committed_sessions() as db:
            db.execute(text(drop))
            db.commit()

        with pytest.raises(profile_exceptions.DataCollectionError):
            _build(committed_sessions, storage, owner.id)

    def test_a_storage_failure_is_a_file_system_error(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            users_integration.store_user_photo(owner.id, ".png", png(90, 8), storage, db)
        broken = FaultyStorage(storage, faults={"get": OSError("disk gone")})

        with pytest.raises(profile_exceptions.FileSystemError):
            _build(committed_sessions, broken, owner.id)

    def test_an_archive_that_cannot_be_written_is_a_zip_error(self, committed_sessions, storage, owner, monkeypatch):
        def refuse(self, *args, **kwargs):
            raise zipfile.LargeZipFile("too big")

        monkeypatch.setattr(zipfile.ZipFile, "writestr", refuse)

        with pytest.raises(profile_exceptions.ZipCreationError, match="too large"):
            _build(committed_sessions, storage, owner.id)

    def test_a_bad_zip_is_a_zip_error(self, committed_sessions, storage, owner, monkeypatch):
        def refuse(self, *args, **kwargs):
            raise zipfile.BadZipFile("broken")

        monkeypatch.setattr(zipfile.ZipFile, "writestr", refuse)

        with pytest.raises(profile_exceptions.ZipCreationError, match="Failed to create"):
            _build(committed_sessions, storage, owner.id)

    def test_running_out_of_memory_while_writing_is_a_memory_error(
        self, committed_sessions, storage, owner, monkeypatch
    ):
        def refuse(self, *args, **kwargs):
            raise MemoryError("oom")

        monkeypatch.setattr(zipfile.ZipFile, "writestr", refuse)

        with pytest.raises(profile_exceptions.MemoryAllocationError):
            _build(committed_sessions, storage, owner.id)

    def test_a_failed_build_leaves_no_temporary_file_open(self, committed_sessions, storage, owner):
        before = len(os.listdir("/dev/fd"))

        with pytest.raises(profile_exceptions.ExportTimeoutError):
            _build(committed_sessions, storage, owner.id, timeout_seconds=-1)

        assert len(os.listdir("/dev/fd")) <= before


class TestPerformanceConfig:
    @pytest.mark.parametrize(
        ("available_mb", "batch_size"),
        [(4096, 250), (1500, 125), (512, 50)],
        ids=["high", "medium", "low"],
    )
    def test_the_tier_follows_the_memory_available(self, monkeypatch, available_mb, batch_size):
        class Memory:
            available = available_mb * 1024 * 1024

        monkeypatch.setattr("psutil.virtual_memory", lambda: Memory())

        assert export_service.ExportPerformanceConfig.get_auto_config().batch_size == batch_size

    def test_a_failure_to_read_the_memory_available_uses_the_medium_tier(self, monkeypatch):
        def unreadable():
            raise OSError("no /proc")

        monkeypatch.setattr("psutil.virtual_memory", unreadable)

        assert export_service.ExportPerformanceConfig.get_auto_config().batch_size == 125
