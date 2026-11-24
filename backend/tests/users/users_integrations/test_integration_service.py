"""The integrations surface other modules call, on the real database."""

import uuid
from datetime import UTC, datetime

import pytest

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.users.users_integrations.integration_service as integration
import modules.users.users_integrations.schema as schema

_TOKENS = {"access_token": "access", "refresh_token": "refresh", "expires_at": 1_900_000_000}
_GARMIN = {"di_token": "x", "di_refresh_token": "y"}


def _garmin_token(label: str) -> dict[str, str]:
    return {
        "di_token": core_cryptography.encrypt_token_fernet(f"access-{label}"),
        "di_refresh_token": core_cryptography.encrypt_token_fernet(f"refresh-{label}"),
    }


class TestRequireUserIntegrations:
    def test_the_users_integrations_are_returned(self, db, user):
        assert integration.require_user_integrations(user.id, db) == integration.get_user_integrations(user.id, db)

    def test_a_user_without_integrations_is_refused(self, db):
        assert integration.get_user_integrations(uuid.uuid4(), db) is None
        with pytest.raises(core_exceptions.NotFoundError):
            integration.require_user_integrations(uuid.uuid4(), db)


class TestStrava:
    def test_linking_stores_the_tokens_and_unlinking_clears_them(self, db, user):
        integration.link_strava_account(user.id, _TOKENS, db)
        integration.set_strava_client(user.id, "client", "secret", db, if_match="*")
        integration.set_strava_sync_gear(user.id, True, db)

        linked = integration.require_user_integrations(user.id, db)
        assert core_cryptography.decrypt_token_fernet(linked.strava_token) == "access"
        assert core_cryptography.decrypt_token_fernet(linked.strava_client_id) == "client"
        assert linked.strava_sync_gear is True
        assert integration.list_user_ids_with_strava_linked(None, 1000, db).count(user.id) == 1

        integration.unlink_strava_account(user.id, db)

        unlinked = integration.require_user_integrations(user.id, db)
        assert (unlinked.strava_token, unlinked.strava_client_id, unlinked.strava_sync_gear) == (None, None, False)
        assert user.id not in integration.list_user_ids_with_strava_linked(None, 1000, db)

    def test_a_rejected_refresh_token_marks_the_revocation_until_the_data_is_cleared(self, db, user):
        integration.link_strava_account(user.id, _TOKENS, db)
        refresh = integration.require_user_integrations(user.id, db).strava_refresh_token
        revoked_at = datetime(2025, 1, 1, tzinfo=UTC)

        assert integration.unlink_strava_tokens_if_refresh_token(user.id, refresh, db, revoked_at=revoked_at) is True

        later = datetime(2025, 2, 1, tzinfo=UTC)
        db.flush()
        assert user.id in integration.list_user_ids_with_strava_revoked_before(later, None, 1000, db)
        integration.clear_strava_revoked_at(user.id, db)
        assert user.id not in integration.list_user_ids_with_strava_revoked_before(later, None, 1000, db)

    def test_a_refresh_replaces_the_tokens_it_came_from(self, db, user):
        integration.link_strava_account(user.id, _TOKENS, db)
        refresh = integration.require_user_integrations(user.id, db).strava_refresh_token
        refreshed = {**_TOKENS, "access_token": "access-2", "refresh_token": "refresh-2"}

        assert integration.replace_strava_tokens_if_refresh_token(user.id, refresh, refreshed, db) is True

        stored = integration.require_user_integrations(user.id, db)
        assert core_cryptography.decrypt_token_fernet(stored.strava_refresh_token) == "refresh-2"


class TestGarmin:
    def test_linking_stores_the_token_and_unlinking_clears_it(self, db, user):
        integration.link_garminconnect_account(user.id, _GARMIN, db)
        integration.set_garminconnect_sync_gear(user.id, True, db)
        db.flush()
        db.expire_all()

        assert integration.require_user_integrations(user.id, db).garminconnect_token == _GARMIN
        assert integration.list_user_ids_with_garminconnect_linked(None, 1000, db).count(user.id) == 1

        integration.unlink_garminconnect_account(user.id, db)
        db.flush()
        db.expire_all()

        unlinked = integration.require_user_integrations(user.id, db)
        assert (unlinked.garminconnect_token, unlinked.garminconnect_sync_gear) == (None, False)

    def test_a_refresh_replaces_and_a_rejection_unlinks_only_the_token_it_read(self, db, user):
        old, fresh = _garmin_token("old"), _garmin_token("fresh")
        integration.link_garminconnect_account(user.id, old, db)

        replaced = integration.replace_garminconnect_token_if_token(user.id, old, fresh, db)
        stale_unlink = integration.unlink_garminconnect_account_if_token(user.id, old, db)

        assert (replaced, stale_unlink) == (True, False)
        assert integration.unlink_garminconnect_account_if_token(user.id, fresh, db) is True


class TestEditAndCreate:
    def test_the_given_fields_are_staged(self, db, user):
        edited = integration.edit_integrations(schema.UserIntegrationsUpdate(garminconnect_sync_gear=True), user.id, db)

        assert integration.require_user_integrations(user.id, db) == edited
        assert edited.garminconnect_sync_gear is True

    def test_a_second_set_of_integrations_is_a_conflict(self, db, user):
        with pytest.raises(core_exceptions.ConflictError):
            integration.create_integrations(user.id, db)
