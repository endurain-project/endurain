"""The surface other modules call, run against the real database; each call answers what the users module stores."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.auth.credentials.integration_service as credentials_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.deletion_state_store as users_deletion_state_store
import modules.users.users.integration_service as users_integration
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import PASSWORD, make_admin, make_sign_up, make_user
from tests._helpers import images


@pytest.fixture
def user(db):
    return make_user(db, username="reader", email="reader@example.com")


def _stored(db, user_id):
    row = db.get(users_models.Users, user_id)
    db.refresh(row)
    return row


class TestReads:
    def test_a_user_is_read_by_id_email_and_username(self, db, user):
        assert users_integration.get_user(user.id, db).id == user.id
        assert users_integration.get_user(uuid.uuid4(), db) is None
        assert users_integration.require_user(user.id, db).id == user.id
        assert users_integration.get_user_by_email("READER@example.com", db).id == user.id
        assert users_integration.get_user_by_username("Reader", db).id == user.id

    def test_a_missing_user_is_required_to_exist(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_integration.require_user(uuid.uuid4(), db)

    def test_public_projections_follow_the_visibility_rules(self, db, user):
        hidden = make_user(db, active=False)
        edit_server_settings(db, public_shareable_links=True, public_shareable_links_user_info=True)

        assert users_integration.get_public_profile(user.id, db).id == user.id
        assert users_integration.get_public_user(user.id, db).id == user.id
        assert list(users_integration.list_public_profiles([user.id, hidden.id], db)) == [user.id]

    def test_an_inactive_user_is_refused_and_the_administrators_are_listed(self, db, user):
        admin = make_admin(db)

        users_integration.require_active_user(user)
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_integration.require_active_user(make_user(db, active=False))
        assert [a.id for a in users_integration.require_admin_users(db)] == [admin.id]

    def test_whether_a_user_exists_and_was_created_after_a_moment_and_is_deactivated(self, db, user):
        assert users_integration.any_user_exists(db) is True
        assert users_integration.was_created_after(user.id, datetime.now(UTC) - timedelta(days=1), db) is True
        assert users_integration.was_created_after(user.id, datetime.now(UTC) + timedelta(days=1), db) is False
        assert users_integration.is_deactivated(user.id, db) is False
        assert users_integration.is_deactivated(make_user(db, active=False).id, db) is True

    def test_the_users_timezone_and_today_are_resolved_with_the_server_default_as_fallback(self, db):
        zoned = make_user(db, timezone="Asia/Tokyo")
        unset = make_user(db)

        assert users_integration.resolve_timezone(zoned.id, db) == "Asia/Tokyo"
        assert users_integration.resolve_timezone(unset.id, db) == users_integration.timezone_or_default(None)
        assert users_integration.local_today(zoned.id, db) is not None
        assert users_integration.timezone_or_default("Europe/Lisbon") == "Europe/Lisbon"


class TestWrites:
    def test_the_first_administrator_is_staged_only_while_no_user_exists(self, db):
        admin = users_schema.FirstAdminCreate(
            name="Owner", username="owner", email="owner@example.com", password=PASSWORD
        )

        created = users_integration.stage_first_admin(admin, db)

        assert _stored(db, created.id).access_type == "admin"
        with pytest.raises(core_exceptions.ConflictError):
            users_integration.stage_first_admin(admin, db)

    def test_a_sign_up_and_an_sso_account_are_staged_with_the_server_settings(self, db):
        settings = server_settings_integration.get_server_settings(db)

        signed_up = users_integration.stage_signup_user(
            users_schema.UserSignup(name="Sam", username="sam", email="sam@example.com", password=PASSWORD),
            settings,
            db,
        )
        sso = users_integration.create_sso_user(
            users_schema.UserBase(name="Sue", username="sue", email="sue@example.com"),
            settings,
            db,
            email_verified=True,
        )

        assert (_stored(db, signed_up.id).email_verified, _stored(db, sso.id).email_verified) == (False, True)
        assert credentials_integration.get_password_hash(sso.id, db) is None

    def test_verification_activates_a_sign_up(self, db):
        waiting = make_sign_up(db)

        users_integration.stage_email_verification(
            waiting.id, edit_server_settings(db, signup_require_admin_approval=False), db
        )

        assert _stored(db, waiting.id).active is True

    def test_a_system_edit_overwrites_with_a_wildcard_and_a_profile_edit_keeps_the_allow_list(self, db, user):
        users_integration.edit_user(user.id, users_schema.UserEdit(access_type="admin"), db, if_match="*")
        users_integration.edit_profile(user.id, users_schema.ProfileUpdate(city="Faro"), db, if_match="*")

        row = _stored(db, user.id)
        assert (row.access_type, row.city) == ("admin", "Faro")

    def test_the_changed_fields_are_named_in_submission_order(self, db, user):
        after = users_integration.edit_profile(
            user.id, users_schema.ProfileUpdate(city="Faro", height=180), db, if_match="*"
        )

        assert users_integration.changed_field_names(user, after, ["height", "name", "city"]) == ["height", "city"]

    def test_username_and_email_changes_are_staged_and_report_whether_they_changed(self, db, user):
        assert users_integration.stage_username_change(user.id, "Renamed", db) is True
        assert users_integration.stage_username_change(user.id, "renamed", db) is False
        assert users_integration.stage_email_change(user.id, "New@Example.com", db) is True
        assert users_integration.stage_email_change(user.id, "new@example.com", db) is False
        assert _stored(db, user.id).email_verified is False

    def test_confirmed_and_synced_email_changes_are_verified(self, db, user):
        users_integration.stage_confirmed_email_change(user.id, "one@example.com", db)
        assert _stored(db, user.id).email_verified is True

        users_integration.stage_synced_email_change(user.id, "two@example.com", db)

        assert _stored(db, user.id).email == "two@example.com"

    def test_an_address_is_available_unless_another_account_holds_it(self, db, user):
        other = make_user(db)

        assert users_integration.is_email_available(user.id, user.email, db) is True
        assert users_integration.is_email_available(user.id, other.email, db) is False


class TestPhotos:
    def test_a_photo_is_uploaded_stored_and_deleted(self, db, user, _publish_local_platform):
        storage = _publish_local_platform.storage
        png = images.png_with_text()

        assert users_integration.upload_user_photo(user.id, "me.png", lambda: png, storage, db) is False
        assert users_integration.upload_user_photo(user.id, "me.png", lambda: png, storage, db) is True
        assert users_integration.store_user_photo(user.id, ".png", png, storage, db) == f"{user.id}.png"
        users_integration.delete_user_photo(user.id, storage, db)

        assert _stored(db, user.id).photo_path is None
        assert list(storage.list_keys(users_constants.USER_IMAGE_STORAGE_AREA)) == []


class TestDeletionJobs:
    def test_a_users_own_deletion_is_queued_whatever_version_they_last_read(
        self, committed_sessions, monkeypatch, _publish_local_platform
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        platform = _publish_local_platform
        with committed_sessions() as db:
            leaving = make_user(db, photo_path="old.png")
            users_crud.replace_photo_key(leaving.id, "new.png", db)
            db.commit()

        with committed_sessions() as db:
            queued = users_integration.request_user_deletion(
                leaving.id, platform.state, platform.storage, platform.mail, db
            )

        assert queued.status == users_constants.DeletionStatus.QUEUED
        with committed_sessions() as db:
            row = db.get(users_models.Users, leaving.id)
            assert (row.active, row.deletion_requested_at is not None) == (False, True)

    def test_the_current_deletion_is_read_with_its_id_and_kind(self, _publish_local_platform):
        state = _publish_local_platform.state
        owner = uuid.uuid4()
        job = users_deletion_state_store.UserDeletionStateStore(state).begin(
            uuid.uuid4(), users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=owner
        )

        status = users_integration.read_deletion_job(job, state)

        assert (status.id, status.kind, status.status) == (job.id, "user_deletion", "queued")

    def test_an_earlier_job_and_an_expired_one_read_as_none(self, _publish_local_platform):
        state = _publish_local_platform.state
        store = users_deletion_state_store.UserDeletionStateStore(state)
        user_id, owner = uuid.uuid4(), uuid.uuid4()
        first = store.begin(user_id, users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=owner)
        store.set_status(
            user_id, users_constants.DeletionKind.ACCOUNT, users_constants.DeletionStatus.FAILED, job_id=first.id
        )
        store.begin(user_id, users_constants.DeletionKind.ACCOUNT, conflict="held", owner_id=owner)

        assert users_integration.read_deletion_job(first, state) is None

    def test_the_pool_can_be_shut_down_and_takes_work_again(self, monkeypatch):
        pool = core_local_pool.BoundedPool("t", workers=1, max_pending=1)
        monkeypatch.setattr(users_deletion_job_service, "_deletion_pool", pool)
        assert pool.submit(lambda: 1).result() == 1

        users_integration.shutdown_deletion_pool()

        assert pool.submit(lambda: 2).result() == 2
        pool.shutdown(wait=True)

    def test_a_purge_of_old_unverified_sign_ups_reports_how_many_it_staged(self, db):
        make_sign_up(db, created_at=datetime.now(UTC) - timedelta(days=3))
        make_user(db)

        assert users_integration.stage_unverified_sign_up_purge(datetime.now(UTC) - timedelta(days=1), [], 10, db) == 1
