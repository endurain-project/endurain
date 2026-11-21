"""Integration settings and provider tokens against the real database."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.users.users.models as users_models
import modules.users.users_integrations.crud as crud
import modules.users.users_integrations.schema as schema
from tests._factories.users import make_user

_EXPIRES_AT = 1_900_000_000


def _tokens(label: str = "a") -> dict[str, Any]:
    return {"access_token": f"access-{label}", "refresh_token": f"refresh-{label}", "expires_at": _EXPIRES_AT}


def _garmin(label: str = "a") -> dict[str, Any]:
    return {
        "di_token": core_cryptography.encrypt_token_fernet(f"access-{label}"),
        "di_refresh_token": core_cryptography.encrypt_token_fernet(f"refresh-{label}"),
        "client_id": "garmin",
    }


def _read(db, user_id):
    stored = crud.get_user_integrations_by_user_id(user_id, db)
    assert stored is not None
    return stored


class TestCreateAndRead:
    def test_a_new_account_has_unlinked_integrations(self, db, user):
        stored = _read(db, user.id)

        assert stored.user_id == user.id
        assert stored.version == 1
        assert (stored.strava_token, stored.strava_refresh_token, stored.strava_client_id) == (None, None, None)
        assert (stored.strava_sync_gear, stored.garminconnect_sync_gear) == (False, False)
        assert (stored.garminconnect_token, stored.strava_revoked_at) == (None, None)

    def test_a_user_without_integrations_reads_none(self, db):
        assert crud.get_user_integrations_by_user_id(uuid.uuid4(), db) is None

    def test_a_second_row_for_a_user_is_a_conflict(self, db, user):
        with pytest.raises(core_exceptions.ConflictError):
            crud.create_user_integrations(user.id, db)

    def test_deleting_the_user_deletes_the_integrations(self, db, user):
        db.execute(delete(users_models.Users).where(users_models.Users.id == user.id))

        assert crud.get_user_integrations_by_user_id(user.id, db) is None


class TestEdit:
    def test_only_the_set_fields_change(self, db, user):
        updated = crud.edit_user_integrations(schema.UserIntegrationsUpdate(strava_sync_gear=True), user.id, db)

        assert (updated.strava_sync_gear, updated.garminconnect_sync_gear) == (True, False)
        assert _read(db, user.id).strava_sync_gear is True

    def test_missing_integrations_are_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_user_integrations(schema.UserIntegrationsUpdate(strava_sync_gear=True), uuid.uuid4(), db)


class TestStravaLink:
    def test_the_tokens_are_stored_encrypted_with_their_expiry(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)

        stored = _read(db, user.id)
        assert stored.strava_token != "access-a"
        assert core_cryptography.decrypt_token_fernet(stored.strava_token) == "access-a"
        assert core_cryptography.decrypt_token_fernet(stored.strava_refresh_token) == "refresh-a"
        assert stored.strava_token_expires_at == datetime.fromtimestamp(_EXPIRES_AT, tz=UTC)

    def test_relinking_clears_the_revocation_mark(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        crud.unlink_strava_tokens_if_refresh_token(
            user.id, _read(db, user.id).strava_refresh_token, db, revoked_at=datetime.now(UTC)
        )
        assert _read(db, user.id).strava_revoked_at is not None

        crud.link_strava_account(user.id, _tokens("b"), db)

        assert _read(db, user.id).strava_revoked_at is None

    def test_linking_without_integrations_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.link_strava_account(uuid.uuid4(), _tokens(), db)

    def test_the_client_credentials_are_stored_encrypted_under_the_version_the_client_read(self, db, user):
        crud.set_user_strava_client(user.id, "client", "secret", db, if_match='"1"')

        stored = _read(db, user.id)
        assert core_cryptography.decrypt_token_fernet(stored.strava_client_id) == "client"
        assert core_cryptography.decrypt_token_fernet(stored.strava_client_secret) == "secret"
        assert stored.version == 2

    def test_a_stale_version_leaves_the_client_credentials_alone(self, db, user):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.set_user_strava_client(user.id, "client", "secret", db, if_match='"4"')

        assert _read(db, user.id).strava_client_id is None

    def test_setting_the_client_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.set_user_strava_client(uuid.uuid4(), "c", "s", db, if_match="*")

    @pytest.mark.parametrize("sync_gear", [True, False])
    def test_the_gear_sync_preference_is_stored(self, db, user, sync_gear):
        crud.set_user_strava_sync_gear(user.id, sync_gear, db)

        assert _read(db, user.id).strava_sync_gear is sync_gear

    def test_the_gear_sync_preference_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.set_user_strava_sync_gear(uuid.uuid4(), True, db)


class TestStravaUnlink:
    def test_an_unlink_clears_everything_including_the_client(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        crud.set_user_strava_client(user.id, "client", "secret", db, if_match="*")
        crud.set_user_strava_sync_gear(user.id, True, db)

        crud.unlink_strava_account(user.id, db)

        stored = _read(db, user.id)
        assert (stored.strava_token, stored.strava_refresh_token, stored.strava_token_expires_at) == (None, None, None)
        assert (stored.strava_client_id, stored.strava_client_secret, stored.strava_sync_gear) == (None, None, False)

    def test_unlinking_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.unlink_strava_account(uuid.uuid4(), db)

    def test_a_rejected_refresh_token_clears_the_tokens_and_keeps_the_client(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        crud.set_user_strava_client(user.id, "client", "secret", db, if_match="*")
        crud.set_user_strava_sync_gear(user.id, True, db)
        refresh = _read(db, user.id).strava_refresh_token

        cleared = crud.unlink_strava_tokens_if_refresh_token(user.id, refresh, db)

        stored = _read(db, user.id)
        assert cleared is True
        assert (stored.strava_token, stored.strava_refresh_token, stored.strava_sync_gear) == (None, None, False)
        assert stored.strava_client_id is not None
        assert stored.strava_revoked_at is None

    def test_a_revocation_stores_its_time_with_the_cleared_tokens(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        moment = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)

        crud.unlink_strava_tokens_if_refresh_token(
            user.id, _read(db, user.id).strava_refresh_token, db, revoked_at=moment
        )

        assert _read(db, user.id).strava_revoked_at == moment

    def test_a_token_linked_since_is_kept(self, db, user):
        crud.link_strava_account(user.id, _tokens("old"), db)
        old = _read(db, user.id).strava_refresh_token
        crud.link_strava_account(user.id, _tokens("new"), db)

        assert crud.unlink_strava_tokens_if_refresh_token(user.id, old, db) is False
        assert _read(db, user.id).strava_token is not None

    def test_a_missing_user_is_not_unlinked(self, db):
        assert crud.unlink_strava_tokens_if_refresh_token(uuid.uuid4(), "x", db) is False

    def test_the_refresh_replaces_the_tokens_while_the_refresh_token_is_the_one_it_came_from(self, db, user):
        crud.link_strava_account(user.id, _tokens("old"), db)
        old = _read(db, user.id).strava_refresh_token

        replaced = crud.replace_strava_tokens_if_refresh_token(user.id, old, _tokens("new"), db)

        stored = _read(db, user.id)
        assert replaced is True
        assert core_cryptography.decrypt_token_fernet(stored.strava_refresh_token) == "refresh-new"

    def test_a_refresh_from_a_replaced_token_is_dropped(self, db, user):
        crud.link_strava_account(user.id, _tokens("old"), db)
        old = _read(db, user.id).strava_refresh_token
        crud.link_strava_account(user.id, _tokens("new"), db)

        assert crud.replace_strava_tokens_if_refresh_token(user.id, old, _tokens("late"), db) is False
        assert core_cryptography.decrypt_token_fernet(_read(db, user.id).strava_refresh_token) == "refresh-new"

    def test_a_refresh_of_a_missing_user_is_dropped(self, db):
        assert crud.replace_strava_tokens_if_refresh_token(uuid.uuid4(), "x", _tokens(), db) is False


class TestStravaRevocation:
    def test_the_due_users_are_the_unlinked_ones_revoked_before_the_cutoff_in_id_order(self, db):
        now = datetime(2025, 3, 10, tzinfo=UTC)
        due = [make_user(db).id for _ in range(3)]
        recent, relinked, never = make_user(db).id, make_user(db).id, make_user(db).id
        for user_id, age in [(due[0], 40), (due[1], 35), (due[2], 31), (recent, 5)]:
            crud.link_strava_account(user_id, _tokens(), db)
            crud.unlink_strava_tokens_if_refresh_token(
                user_id, _read(db, user_id).strava_refresh_token, db, revoked_at=now - timedelta(days=age)
            )
        crud.link_strava_account(relinked, _tokens(), db)
        cutoff = now - timedelta(days=30)

        listed = crud.list_user_ids_with_strava_revoked_before(cutoff, None, 100, db)
        first = crud.list_user_ids_with_strava_revoked_before(cutoff, None, 2, db)
        rest = crud.list_user_ids_with_strava_revoked_before(cutoff, first[-1], 2, db)

        assert listed == sorted(due)
        assert first + rest == sorted(due)
        assert recent not in listed and relinked not in listed and never not in listed

    def test_clearing_the_mark_after_the_data_was_deleted(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        crud.unlink_strava_tokens_if_refresh_token(
            user.id, _read(db, user.id).strava_refresh_token, db, revoked_at=datetime.now(UTC)
        )

        crud.clear_strava_revoked_at(user.id, db)

        assert _read(db, user.id).strava_revoked_at is None

    def test_clearing_the_mark_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.clear_strava_revoked_at(uuid.uuid4(), db)

    def test_an_in_app_unlink_clears_the_mark(self, db, user):
        crud.link_strava_account(user.id, _tokens(), db)
        crud.unlink_strava_tokens_if_refresh_token(
            user.id, _read(db, user.id).strava_refresh_token, db, revoked_at=datetime.now(UTC)
        )

        crud.unlink_strava_account(user.id, db)

        assert _read(db, user.id).strava_revoked_at is None


class TestStravaLinkedListing:
    def test_only_users_with_a_token_are_listed_in_id_order_and_paged_by_cursor(self, db):
        linked = [make_user(db).id for _ in range(3)]
        make_user(db)
        for user_id in linked:
            crud.link_strava_account(user_id, _tokens(), db)

        everyone = crud.list_user_ids_with_strava_linked(None, 100, db)
        first = crud.list_user_ids_with_strava_linked(None, 2, db)
        rest = crud.list_user_ids_with_strava_linked(first[-1], 2, db)

        assert everyone == sorted(linked)
        assert first + rest == sorted(linked)


class TestGarmin:
    def test_the_token_is_stored_as_given(self, db, user):
        token = _garmin()

        crud.link_garminconnect_account(user.id, token, db)
        db.flush()
        db.expire_all()

        assert _read(db, user.id).garminconnect_token == token

    def test_linking_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.link_garminconnect_account(uuid.uuid4(), _garmin(), db)

    @pytest.mark.parametrize("sync_gear", [True, False])
    def test_the_gear_sync_preference_is_stored(self, db, user, sync_gear):
        crud.set_user_garminconnect_sync_gear(user.id, sync_gear, db)

        assert _read(db, user.id).garminconnect_sync_gear is sync_gear

    def test_the_gear_sync_preference_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.set_user_garminconnect_sync_gear(uuid.uuid4(), True, db)

    def test_an_unlink_clears_the_token_and_the_gear_sync(self, db, user):
        crud.link_garminconnect_account(user.id, _garmin(), db)
        crud.set_user_garminconnect_sync_gear(user.id, True, db)

        crud.unlink_garminconnect_account(user.id, db)
        db.flush()
        db.expire_all()

        stored = _read(db, user.id)
        assert (stored.garminconnect_token, stored.garminconnect_sync_gear) == (None, False)

    def test_unlinking_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.unlink_garminconnect_account(uuid.uuid4(), db)

    def test_a_rejected_token_unlinks_while_it_is_the_stored_one(self, db, user):
        token = _garmin()
        crud.link_garminconnect_account(user.id, token, db)
        crud.set_user_garminconnect_sync_gear(user.id, True, db)

        assert crud.unlink_garminconnect_account_if_token(user.id, token, db) is True
        db.flush()
        db.expire_all()

        stored = _read(db, user.id)
        assert (stored.garminconnect_token, stored.garminconnect_sync_gear) == (None, False)

    def test_a_token_linked_since_is_kept_and_so_is_a_missing_one(self, db, user):
        crud.link_garminconnect_account(user.id, _garmin("new"), db)

        assert crud.unlink_garminconnect_account_if_token(user.id, _garmin("old"), db) is False
        assert crud.unlink_garminconnect_account_if_token(uuid.uuid4(), _garmin("old"), db) is False
        assert _read(db, user.id).garminconnect_token is not None

    def test_a_token_that_is_not_linked_is_not_unlinked(self, db, user):
        assert crud.unlink_garminconnect_account_if_token(user.id, _garmin(), db) is False

    def test_the_refresh_replaces_the_token_it_came_from(self, db, user):
        old, new = _garmin("old"), _garmin("new")
        crud.link_garminconnect_account(user.id, old, db)

        assert crud.replace_garminconnect_token_if_token(user.id, old, new, db) is True
        db.flush()
        db.expire_all()

        assert _read(db, user.id).garminconnect_token == new

    def test_a_secret_re_encrypted_under_a_new_key_still_matches_what_the_caller_read(self, db, user):
        old = _garmin("old")
        crud.link_garminconnect_account(user.id, old, db)
        reencrypted = {**old, "di_token": core_cryptography.encrypt_token_fernet("access-old")}
        assert reencrypted["di_token"] != old["di_token"]
        crud.link_garminconnect_account(user.id, reencrypted, db)

        assert crud.replace_garminconnect_token_if_token(user.id, old, _garmin("new"), db) is True

    def test_a_refresh_from_a_replaced_token_is_dropped(self, db, user):
        current = _garmin("current")
        crud.link_garminconnect_account(user.id, current, db)

        assert crud.replace_garminconnect_token_if_token(user.id, _garmin("old"), _garmin("late"), db) is False
        assert crud.replace_garminconnect_token_if_token(uuid.uuid4(), _garmin("old"), _garmin("late"), db) is False
        db.flush()
        db.expire_all()
        assert _read(db, user.id).garminconnect_token == current

    def test_a_token_with_other_keys_is_not_the_one_read(self, db, user):
        old = _garmin("old")
        crud.link_garminconnect_account(user.id, old, db)

        assert crud.unlink_garminconnect_account_if_token(user.id, {"di_token": old["di_token"]}, db) is False
        assert crud.unlink_garminconnect_account_if_token(user.id, {**old, "client_id": "other"}, db) is False

    def test_the_linked_listing_skips_unlinked_tokens_and_pages_past_them(self, db):
        linked = sorted(make_user(db).id for _ in range(3))
        for user_id in linked:
            crud.link_garminconnect_account(user_id, _garmin(), db)
        for _ in range(4):
            gone = make_user(db).id
            crud.link_garminconnect_account(gone, _garmin(), db)
            crud.unlink_garminconnect_account(gone, db)
        db.flush()

        everyone = crud.list_user_ids_with_garminconnect_linked(None, 100, db)
        first = crud.list_user_ids_with_garminconnect_linked(None, 2, db)
        rest = crud.list_user_ids_with_garminconnect_linked(first[-1], 2, db)

        assert everyone == linked
        assert first + rest == linked
        assert len(first) == 2
