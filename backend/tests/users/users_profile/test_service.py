"""The profile service on the real database: the assembled profile, the user's own edits, export and deletion."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

import core.exceptions as core_exceptions
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.schema as auth_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_integrations.constants as integrations_constants
import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_service as export_service
import modules.users.users_profile.service as profile_service
from tests._factories.profile import FaultyStorage
from tests._factories.users import PASSWORD, make_admin, make_user

_SESSION = uuid.UUID(int=601)
_TOKENS = {"access_token": "access", "refresh_token": "refresh", "expires_at": 1_900_000_000}


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def step_up_store(platform):
    return account_security_integration.get_step_up_attempts(platform.state)


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, name="Before", city="Porto")
        db.commit()
    return created


def _version(committed_sessions, user_id):
    with committed_sessions() as db:
        return users_integration.require_user(user_id, db).version


class TestGetProfile:
    def test_the_profile_assembles_the_account_its_links_and_its_privacy_settings(self, db):
        user = make_user(db, name="Ada")
        integrations_integration.link_strava_account(user.id, _TOKENS, db)
        integrations_integration.link_garminconnect_account(user.id, {"di_token": "x"}, db)
        privacy_integration.edit_privacy_settings(
            user.id,
            privacy_schema.UserPrivacySettingsUpdate(hide_activity_map=True, discoverable=False),
            db,
            if_match="*",
        )

        profile = profile_service.get_profile(user.id, db)

        assert (profile.id, profile.name) == (user.id, "Ada")
        assert (profile.is_strava_linked, profile.is_garminconnect_linked) == (True, True)
        assert profile.strava_revoked_at is None and profile.strava_data_deletion_at is None
        assert (profile.hide_activity_map, profile.discoverable) == (True, False)
        assert profile.default_activity_visibility == "private"
        assert (profile.has_local_password, profile.mfa_enabled) == (True, False)
        assert profile.pending_email is None
        assert profile.integrations_version >= 1 and profile.privacy_settings_version >= 1

    def test_a_revoked_strava_link_names_when_its_data_will_be_deleted(self, db):
        user = make_user(db)
        integrations_integration.link_strava_account(user.id, _TOKENS, db)
        refresh = integrations_integration.require_user_integrations(user.id, db).strava_refresh_token
        revoked_at = datetime(2025, 3, 1, tzinfo=UTC)
        integrations_integration.unlink_strava_tokens_if_refresh_token(user.id, refresh, db, revoked_at=revoked_at)
        db.flush()

        profile = profile_service.get_profile(user.id, db)

        assert profile.is_strava_linked is False
        assert profile.strava_revoked_at == revoked_at
        grace = timedelta(days=integrations_constants.STRAVA_REVOKED_DATA_GRACE_DAYS)
        assert profile.strava_data_deletion_at == revoked_at + grace

    def test_an_account_without_a_password_says_so(self, db):
        user = make_user(db, with_password=False)

        assert profile_service.get_profile(user.id, db).has_local_password is False

    @pytest.mark.parametrize("table", ["users_integrations", "users_privacy_settings"])
    def test_a_missing_part_is_not_found(self, db, table):
        from sqlalchemy import column, delete
        from sqlalchemy import table as sa_table

        user = make_user(db)
        db.execute(delete(sa_table(table, column("user_id"))).where(column("user_id") == user.id))

        with pytest.raises(core_exceptions.NotFoundError):
            profile_service.get_profile(user.id, db)

    def test_an_unknown_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            profile_service.get_profile(uuid.uuid4(), db)


class TestEditProfile:
    def test_the_edit_commits_and_the_profile_comes_back_with_the_new_version(self, committed_sessions, owner):
        with committed_sessions() as db:
            edited = profile_service.edit_profile(
                owner.id,
                users_schema.ProfileUpdate(city="Lisbon", height=181),
                db,
                if_match=f'"{owner.version}"',
            )

        assert (edited.city, edited.height, edited.name) == ("Lisbon", 181, "Before")
        assert edited.version == owner.version + 1
        assert _version(committed_sessions, owner.id) == edited.version

    def test_a_stale_version_is_refused_and_nothing_changes(self, committed_sessions, owner):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            profile_service.edit_profile(
                owner.id, users_schema.ProfileUpdate(city="Lisbon"), db, if_match=f'"{owner.version + 5}"'
            )

        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).city == "Porto"

    def test_an_unknown_user_is_not_found(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            profile_service.edit_profile(uuid.uuid4(), users_schema.ProfileUpdate(city="x"), db, if_match="*")


class TestPrivacySettings:
    def test_the_settings_are_read_with_their_version(self, db):
        user = make_user(db)

        settings = profile_service.get_privacy_settings(user.id, db)

        assert (settings.user_id, settings.version) == (user.id, 1)

    def test_a_user_without_settings_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            profile_service.get_privacy_settings(uuid.uuid4(), db)

    def test_the_edit_commits_and_returns_the_new_version(self, committed_sessions, owner):
        with committed_sessions() as db:
            edited = profile_service.edit_privacy_settings(
                owner.id, privacy_schema.UserPrivacySettingsUpdate(hide_activity_hr=True), db, if_match='"1"'
            )

        assert (edited.hide_activity_hr, edited.version) == (True, 2)
        with committed_sessions() as db:
            assert profile_service.get_privacy_settings(owner.id, db) == edited

    def test_a_stale_version_is_refused(self, committed_sessions, owner):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            profile_service.edit_privacy_settings(
                owner.id, privacy_schema.UserPrivacySettingsUpdate(hide_activity_hr=True), db, if_match='"9"'
            )

    def test_missing_settings_are_not_found(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            profile_service.edit_privacy_settings(
                uuid.uuid4(), privacy_schema.UserPrivacySettingsUpdate(hide_activity_hr=True), db, if_match="*"
            )


class TestChangePassword:
    def _change(self, committed_sessions, owner, step_up_store, new="A completely new passphrase 2026!", **fields):
        change = users_schema.UserEditPassword(password=new, step_up={"current_password": PASSWORD}, **fields)
        with committed_sessions() as db:
            profile_service.change_password(owner.id, change, _SESSION, step_up_store, db)

    def test_the_new_password_replaces_the_old_one(self, committed_sessions, owner, step_up_store):
        self._change(committed_sessions, owner, step_up_store)

        with committed_sessions() as db:
            stored = credentials_integration.get_password_hash(owner.id, db)
        hasher = credentials_integration.get_password_hasher()
        assert stored is not None
        assert hasher.verify_password("A completely new passphrase 2026!", stored)
        assert not hasher.verify_password(PASSWORD, stored)

    def test_a_wrong_current_password_changes_nothing(self, committed_sessions, owner, step_up_store):
        change = users_schema.UserEditPassword(
            password="A completely new passphrase 2026!", step_up={"current_password": "wrong"}
        )

        with committed_sessions() as db, pytest.raises(core_exceptions.StepUpFailedError):
            profile_service.change_password(owner.id, change, _SESSION, step_up_store, db)

    def test_the_other_sessions_end_unless_the_client_opts_out(self, committed_sessions, owner, step_up_store, sign_in):
        import sqlalchemy as sa

        import modules.auth.sessions.models as session_models

        mine, other = sign_in(owner), sign_in(owner)
        change = users_schema.UserEditPassword(
            password="A completely new passphrase 2026!", step_up={"current_password": PASSWORD}
        )

        with committed_sessions() as db:
            profile_service.change_password(owner.id, change, mine.session_id, step_up_store, db)

        with committed_sessions() as db:
            left = set(db.scalars(sa.select(session_models.UsersSessions.id).filter_by(user_id=owner.id)))
        assert left == {mine.session_id}
        assert other.session_id not in left


class TestStageExport:
    def test_the_archive_is_staged_and_server_managed_fields_never_reach_it(self, committed_sessions, platform, owner):
        with committed_sessions() as db:
            size = profile_service.stage_export(owner.id, platform.storage, db)

        data = platform.storage.get(
            profile_constants.EXPORT_STAGING_AREA, profile_constants.export_staged_key(owner.id)
        )
        assert data is not None and size == len(data)
        with zipfile.ZipFile(io.BytesIO(data)) as zipf:
            (user_row,) = json.loads(zipf.read("data/user.json"))
        assert user_row["city"] == "Porto"
        for field in profile_service._NON_EXPORTED_USER_FIELDS:
            assert field not in user_row

    def test_a_build_that_fails_is_a_domain_error_and_stages_nothing(
        self, committed_sessions, platform, owner, monkeypatch
    ):
        config = export_service.ExportPerformanceConfig(timeout_seconds=-1, max_memory_mb=1_000_000)
        monkeypatch.setattr(export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: config))

        with committed_sessions() as db, pytest.raises(core_exceptions.DomainError):
            profile_service.stage_export(owner.id, platform.storage, db)

        assert platform.storage.list_keys(profile_constants.EXPORT_STAGING_AREA, "") == []

    def test_a_storage_failure_while_staging_propagates(self, committed_sessions, platform, owner):
        broken = FaultyStorage(platform.storage, faults={"save_stream": OSError("disk full")})

        with committed_sessions() as db, pytest.raises(OSError, match="disk full"):
            profile_service.stage_export(owner.id, broken, db)

    def test_an_unknown_user_is_not_found(self, committed_sessions, platform):
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            profile_service.stage_export(uuid.uuid4(), platform.storage, db)


class TestDeleteAccount:
    def _delete(self, committed_sessions, platform, user, step_up_store, password=PASSWORD):
        with committed_sessions() as db:
            return profile_service.delete_account(
                user.id,
                _SESSION,
                auth_schema.StepUpVerification(current_password=password),
                step_up_store,
                platform.state,
                platform.storage,
                platform.mail,
                db,
            )

    def test_the_deletion_is_queued_and_the_account_is_deactivated_and_signed_out(
        self, committed_sessions, platform, owner, step_up_store, sign_in
    ):
        import sqlalchemy as sa

        import modules.auth.sessions.models as session_models

        sign_in(owner)

        status = self._delete(committed_sessions, platform, owner, step_up_store)

        assert status.kind == "user_deletion"
        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).active is False
            assert db.scalars(sa.select(session_models.UsersSessions.id).filter_by(user_id=owner.id)).all() == []

    def test_a_wrong_password_deletes_nothing(self, committed_sessions, platform, owner, step_up_store):
        with pytest.raises(core_exceptions.StepUpFailedError):
            self._delete(committed_sessions, platform, owner, step_up_store, password="wrong")

        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).active is True

    def test_the_only_administrator_cannot_delete_their_account(self, committed_sessions, platform, step_up_store):
        with committed_sessions() as db:
            admin = make_admin(db)
            db.commit()

        with pytest.raises(core_exceptions.LastAdministratorError):
            self._delete(committed_sessions, platform, admin, step_up_store)

        with committed_sessions() as db:
            assert users_integration.require_user(admin.id, db).active is True
