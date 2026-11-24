"""The profile import on the real database: what an archive may write, what it is refused for, and what a failure
leaves behind."""

import io

import pytest
from PIL import Image
from sqlalchemy import select

import modules.auth.identity_provider_links.models as identity_link_models
import modules.users.users.integration_service as users_integration
import modules.users.users_default_gear.integration_service as default_gear_integration
import modules.users.users_goals.crud as goals_crud
import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.import_service as import_service
from tests._factories.gears import make_gear
from tests._factories.goals import make_goal
from tests._factories.profile import archive_of, png, profile_archive
from tests._factories.users import make_user

#: The pytest process holds what earlier tests allocated, which the memory limit is not about.
_ROOMY = {"max_memory_mb": 1_000_000}


@pytest.fixture
def owner(committed_sessions):
    """A committed user the archives are imported into."""
    with committed_sessions() as db:
        created = make_user(db, name="Before", city="Porto", height=170)
        db.commit()
    return created


def _import(committed_sessions, storage, user_id, archive, **config):
    """Run the import on a session of its own, as the import job does, and return its counts."""
    settings = {**_ROOMY, **config}
    with committed_sessions() as db:
        importer = import_service.ImportService(
            user_id, storage, db, import_service.ImportPerformanceConfig(**settings)
        )
        return importer.import_from_zip_data(archive)


@pytest.fixture
def storage(_publish_local_platform):
    return _publish_local_platform.storage


class TestWhatTheArchiveWrites:
    def test_the_profile_fields_are_applied_and_the_account_keeps_its_name(self, committed_sessions, storage, owner):
        row = {
            "username": owner.username,
            "email": owner.email,
            "city": "Lisbon",
            "height": 181,
            "max_heart_rate": 190,
            "weight_units": "imperial",
        }

        counts = _import(committed_sessions, storage, owner.id, archive_of({"data/user.json": [row]}))

        with committed_sessions() as db:
            stored = users_integration.require_user(owner.id, db)
        assert counts["user"] == 1
        assert (stored.city, stored.height, stored.max_heart_rate) == ("Lisbon", 181, 190)
        assert stored.weight_units == "imperial"
        assert (stored.username, stored.email) == (owner.username, owner.email)

    def test_privileged_fields_in_a_crafted_archive_are_dropped(self, committed_sessions, storage, owner):
        row = {
            "username": owner.username,
            "city": "Faro",
            "access_type": "admin",
            "active": False,
            "email_verified": False,
            "pending_admin_approval": True,
            "id": "00000000-0000-4000-8000-000000000001",
        }

        _import(committed_sessions, storage, owner.id, archive_of({"data/user.json": [row]}))

        with committed_sessions() as db:
            stored = users_integration.require_user(owner.id, db)
        assert stored.city == "Faro"
        assert (stored.access_type, stored.active, stored.email_verified) == ("regular", True, True)
        assert stored.pending_admin_approval is False

    def test_the_settings_import_even_without_a_profile_row(self, committed_sessions, storage, owner):
        archive = archive_of(
            {
                "data/user_privacy_settings.json": [{"hide_activity_map": True}],
                "data/user_integrations.json": [{"strava_sync_gear": True}],
            }
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert (counts["user"], counts["user_privacy_settings"], counts["user_integrations"]) == (0, 1, 1)

    def test_goals_keep_their_archive_order_and_skip_invalid_and_existing_ones(
        self, committed_sessions, storage, owner
    ):
        with committed_sessions() as db:
            make_goal(db, owner.id, interval="daily", goal_distance=1000)
            db.commit()
        goals = [
            {
                "id": "x",
                "version": 9,
                "interval": "weekly",
                "activity_type": "run",
                "goal_type": "distance",
                "goal_distance": 5000,
            },
            {"interval": "daily", "activity_type": "run", "goal_type": "distance", "goal_distance": 7777},
            {"interval": "hourly", "activity_type": "run", "goal_type": "distance", "goal_distance": 1},
            {"interval": "monthly", "activity_type": "bike", "goal_type": "calories", "goal_calories": 900},
        ]

        counts = _import(committed_sessions, storage, owner.id, profile_archive(owner, user_goals=goals))

        with committed_sessions() as db:
            stored = goals_crud.get_user_goals_page(owner.id, db, limit=10, offset=0)
        assert counts["user_goals"] == 2
        assert [(g.interval, g.activity_type) for g in stored] == [
            ("daily", "run"),
            ("weekly", "run"),
            ("monthly", "bike"),
        ]
        assert stored[0].goal_distance == 1000

    def test_privacy_settings_import_without_their_version_and_an_old_archive_leaves_discovery_alone(
        self, committed_sessions, storage, owner
    ):
        with committed_sessions() as db:
            privacy_integration.edit_privacy_settings(
                owner.id,
                privacy_integration.users_privacy_settings_schema.UserPrivacySettingsUpdate(discoverable=False),
                db,
                if_match="*",
            )
            db.commit()
        settings = [{"id": "x", "version": 5, "hide_activity_hr": True, "default_activity_visibility": "followers"}]

        counts = _import(committed_sessions, storage, owner.id, profile_archive(owner, user_privacy_settings=settings))

        with committed_sessions() as db:
            stored = privacy_integration.get_privacy_settings(owner.id, db)
        assert counts["user_privacy_settings"] == 1
        assert stored is not None
        assert (stored.hide_activity_hr, stored.default_activity_visibility, stored.discoverable) == (
            True,
            "followers",
            False,
        )

    def test_the_discoverable_choice_is_imported(self, committed_sessions, storage, owner):
        _import(
            committed_sessions,
            storage,
            owner.id,
            profile_archive(owner, user_privacy_settings=[{"discoverable": False}]),
        )

        with committed_sessions() as db:
            stored = privacy_integration.get_privacy_settings(owner.id, db)
        assert stored is not None
        assert stored.discoverable is False

    def test_invalid_singleton_settings_are_skipped_not_fatal(self, committed_sessions, storage, owner):
        archive = profile_archive(
            owner,
            user_privacy_settings=[{"hide_activity_map": "not a boolean"}],
            user_integrations=[{"strava_sync_gear": "not a boolean"}],
            user_goals=[{"interval": "weekly", "activity_type": "run", "goal_type": "distance", "goal_distance": 100}],
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert (counts["user_privacy_settings"], counts["user_integrations"], counts["user_goals"]) == (0, 0, 1)

    def test_only_the_sync_preferences_of_the_integrations_are_imported(self, committed_sessions, storage, owner):
        integrations = [
            {
                "strava_sync_gear": True,
                "garminconnect_sync_gear": True,
                "strava_token": "planted",
                "strava_refresh_token": "planted",
                "strava_client_id": "planted",
                "garminconnect_token": {"di_token": "planted"},
            }
        ]

        counts = _import(committed_sessions, storage, owner.id, profile_archive(owner, user_integrations=integrations))

        with committed_sessions() as db:
            stored = integrations_integration.require_user_integrations(owner.id, db)
        assert counts["user_integrations"] == 1
        assert (stored.strava_sync_gear, stored.garminconnect_sync_gear) == (True, True)
        assert (stored.strava_token, stored.strava_refresh_token, stored.strava_client_id) == (None, None, None)
        assert stored.garminconnect_token is None

    def test_credentials_alone_import_nothing(self, committed_sessions, storage, owner):
        archive = profile_archive(
            owner,
            user_integrations=[{"strava_token": "planted"}],
            user_goals=[
                {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}
            ],
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert counts["user_integrations"] == 0

    def test_a_crafted_archive_cannot_recreate_identity_provider_links(self, committed_sessions, storage, owner):
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username}],
                "data/user_identity_providers.json": [{"idp_id": "x", "idp_subject": "attacker"}],
                "data/identity_provider_links.json": [{"idp_id": "x", "idp_subject": "attacker"}],
                "data/user_goals.json": [
                    {
                        "interval": "daily",
                        "activity_type": "run",
                        "goal_type": "activities",
                        "goal_activities_number": 1,
                    }
                ],
            }
        )

        _import(committed_sessions, storage, owner.id, archive)

        with committed_sessions() as db:
            assert db.scalars(select(identity_link_models.IdentityLink)).all() == []

    def test_the_default_gear_is_moved_onto_the_restored_gears(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            gear = make_gear(db, owner.id)
            db.commit()
        archive = profile_archive(
            owner,
            user_default_gear=[{"id": "x", "run_gear_id": str(gear.id), "ride_gear_id": "not-a-gear"}],
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        with committed_sessions() as db:
            stored = default_gear_integration.get_default_gear(owner.id, db)
        assert counts["user_default_gear"] == 1
        assert stored is not None
        # No gear section restored any gear, so an archived gear id names nothing.
        assert (stored.run_gear_id, stored.ride_gear_id) == (None, None)

    def test_invalid_default_gear_is_not_counted(self, committed_sessions, storage, owner):
        archive = profile_archive(
            owner,
            user_default_gear=[{"unknown": 1}],
            user_goals=[
                {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}
            ],
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert counts["user_default_gear"] == 0


class TestRefusals:
    def test_an_archive_from_another_account_imports_nothing(self, committed_sessions, storage, owner):
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()
        archive = profile_archive(
            stranger,
            user_goals=[
                {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}
            ],
        )

        with pytest.raises(profile_exceptions.ImportAccountMismatchError):
            _import(committed_sessions, storage, owner.id, archive)

        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 0

    def test_a_renamed_account_still_matches_by_email_and_the_check_ignores_case(
        self, committed_sessions, storage, owner
    ):
        goals = [{"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}]
        by_email = archive_of(
            {"data/user.json": [{"username": "old-name", "email": owner.email.upper()}], "data/user_goals.json": goals}
        )
        by_username = archive_of(
            {"data/user.json": [{"username": owner.username.upper(), "email": "gone@example.com"}]}
            | {"data/user_goals.json": [{**goals[0], "interval": "weekly"}]}
        )

        assert _import(committed_sessions, storage, owner.id, by_email)["user_goals"] == 1
        assert _import(committed_sessions, storage, owner.id, by_username)["user_goals"] == 1

    def test_an_archive_without_a_username_or_email_is_accepted(self, committed_sessions, storage, owner):
        archive = archive_of(
            {
                "data/user.json": [{"city": "Faro"}],
            }
        )

        assert _import(committed_sessions, storage, owner.id, archive)["user"] == 1

    @pytest.mark.parametrize("archived_id", [7, 0])
    def test_an_integer_account_id_marks_an_older_archive_whatever_else_it_says(
        self, committed_sessions, storage, owner, archived_id
    ):
        archive = archive_of({"data/user.json": [{"id": archived_id, "username": owner.username}]})

        with pytest.raises(profile_exceptions.ImportArchiveFromOlderVersionError):
            _import(committed_sessions, storage, owner.id, archive)

    def test_a_true_id_is_not_an_integer_id(self, committed_sessions, storage, owner):
        archive = archive_of({"data/user.json": [{"id": True, "username": owner.username, "city": "Faro"}]})

        assert _import(committed_sessions, storage, owner.id, archive)["user"] == 1

    def test_an_archive_with_nothing_to_import_is_refused(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.FileFormatError):
            _import(committed_sessions, storage, owner.id, archive_of({"data/readme.json": []}))

    def test_a_file_that_is_not_a_zip_is_refused(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.FileFormatError):
            _import(committed_sessions, storage, owner.id, b"this is not an archive")

    def test_an_archive_over_the_size_limit_is_refused(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.FileSizeError):
            _import(committed_sessions, storage, owner.id, profile_archive(owner), max_file_size_mb=0)

    def test_an_archive_with_too_many_entries_is_refused_before_anything_is_read(
        self, committed_sessions, storage, owner
    ):
        archive = archive_of({f"data/extra_{n}.json": [] for n in range(3)})

        with pytest.raises(profile_exceptions.FileSizeError):
            _import(committed_sessions, storage, owner.id, archive, max_entries=2)

    def test_a_data_file_over_its_size_cap_is_refused(self, committed_sessions, storage, owner):
        archive = archive_of({"data/user.json": [{"username": owner.username, "about": "x" * 3_000_000}]})

        with pytest.raises(profile_exceptions.FileSizeError):
            _import(committed_sessions, storage, owner.id, archive, max_json_mb=1)

    def test_an_archive_that_decompresses_past_the_archive_cap_is_refused(self, committed_sessions, storage, owner):
        archive = archive_of({"data/user.json": [{"username": owner.username, "about": "x" * 3_000_000}]})

        with pytest.raises(profile_exceptions.FileSizeError):
            _import(committed_sessions, storage, owner.id, archive, max_uncompressed_mb=1)

    def test_a_data_file_that_is_not_json_is_refused(self, committed_sessions, storage, owner):
        archive = archive_of({"data/user.json": b"{ not json"})

        with pytest.raises(profile_exceptions.JSONParseError):
            _import(committed_sessions, storage, owner.id, archive)

    def test_a_data_file_that_is_not_a_list_or_holds_other_things_is_read_as_what_it_lists(
        self, committed_sessions, storage, owner
    ):
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username}],
                "data/user_goals.json": {"not": "a list"},
                "data/user_privacy_settings.json": ["text", {"hide_activity_map": True}],
            }
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert (counts["user_goals"], counts["user_privacy_settings"]) == (0, 1)

    def test_the_memory_limit_is_checked_before_anything_is_loaded(self, committed_sessions, storage, owner):
        with pytest.raises(profile_exceptions.MemoryAllocationError):
            _import(committed_sessions, storage, owner.id, profile_archive(owner), max_memory_mb=0)

    def test_an_import_out_of_time_stops_and_leaves_nothing(self, committed_sessions, storage, owner):
        archive = profile_archive(
            owner,
            user_goals=[
                {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}
            ],
        )

        with pytest.raises(profile_exceptions.ImportTimeoutError):
            _import(committed_sessions, storage, owner.id, archive, timeout_seconds=-1)

        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 0

    def test_a_refused_archive_leaves_no_rows_even_when_part_of_it_was_staged(self, committed_sessions, storage, owner):
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username, "city": "Faro"}],
                "data/user_goals.json": [
                    {
                        "interval": "daily",
                        "activity_type": "run",
                        "goal_type": "activities",
                        "goal_activities_number": 1,
                    }
                ],
                "data/activities.json": [{"id": "not-an-activity"}] * 3,
            }
        )

        try:
            _import(committed_sessions, storage, owner.id, archive, max_activities=2)
        except profile_exceptions.ActivityLimitError:
            pass
        else:
            pytest.fail("the activity limit did not apply")

        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).city == "Porto"
            assert goals_crud.count_user_goals(owner.id, db) == 0


class TestFilesAndCommit:
    def test_the_photo_is_stored_after_the_rows_commit(self, committed_sessions, storage, owner):
        calls = []
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username, "city": "Faro"}],
                f"user_images/{owner.id}.png": png(90, 8),
            }
        )

        with committed_sessions() as db:
            importer = import_service.ImportService(
                owner.id,
                storage,
                db,
                import_service.ImportPerformanceConfig(**_ROOMY),
                on_database_committed=lambda: calls.append(users_integration.get_user(owner.id, db)),
            )
            counts = importer.import_from_zip_data(archive)

        assert counts["user_images"] == 1
        # The callback ran once the rows were in, and before the photo was written.
        assert [user.city for user in calls if user is not None] == ["Faro"]
        with committed_sessions() as db:
            stored = users_integration.require_user(owner.id, db)
        assert stored.photo_path is not None

    def test_an_invalid_image_is_dropped_and_other_files_are_ignored(self, committed_sessions, storage, owner):
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username, "city": "Faro"}],
                "user_images/bad.png": b"not an image",
                "user_images/notes.txt": b"ignored",
            }
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert counts["user_images"] == 0
        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).photo_path is None

    def test_a_webp_photo_is_accepted_like_the_upload_accepts_it(self, committed_sessions, storage, owner):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="WEBP")
        archive = archive_of(
            {"data/user.json": [{"username": owner.username}], f"user_images/{owner.id}.webp": buffer.getvalue()}
        )

        counts = _import(committed_sessions, storage, owner.id, archive)

        assert counts["user_images"] == 1

    def test_a_failure_writing_files_keeps_the_committed_rows(self, committed_sessions, storage, owner):
        class FailingStorage:
            def __getattr__(self, name):
                return getattr(storage, name)

            def save(self, *args, **kwargs):
                raise OSError("disk full")

            def save_stream(self, *args, **kwargs):
                raise OSError("disk full")

        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username, "city": "Faro"}],
                f"user_images/{owner.id}.png": png(90, 8),
            }
        )

        with pytest.raises(profile_exceptions.FileSystemError):
            _import(committed_sessions, FailingStorage(), owner.id, archive)

        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).city == "Faro"


def test_a_truncated_zip_is_refused_as_a_bad_archive(committed_sessions, storage, owner):
    archive = profile_archive(owner, user_privacy_settings=[{"hide_activity_map": True}])

    with pytest.raises(profile_exceptions.FileFormatError):
        _import(committed_sessions, storage, owner.id, archive[:-10])


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

        assert import_service.ImportPerformanceConfig.get_auto_config().batch_size == batch_size
