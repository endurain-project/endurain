"""Tests for core.key_rotation and the per-module re-encryption of stored secrets."""

import uuid
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import insert, select, update

import core.cryptography as core_cryptography
import core.key_rotation as core_key_rotation
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.identity_provider_links.service as identity_links_service
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.models as identity_provider_models
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.models as mfa_models
import modules.auth.mfa.service as mfa_service
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.service as rotated_token_service
import modules.server_settings.models as server_settings_models
import modules.server_settings.service as server_settings_service
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.models as user_integrations_models
import modules.users.users_integrations.service as user_integrations_service
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import create_sqlite_session

NEW_KEY = Fernet.generate_key().decode()
OLD_KEY = Fernet.generate_key().decode()
STRANGER_KEY = Fernet.generate_key().decode()


def _token(key: str, plaintext: str) -> str:
    """Encrypt ``plaintext`` under ``key`` alone."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def _plain(token: str) -> str:
    """Decrypt ``token`` with the configured key list."""
    return core_cryptography.decrypt_token_fernet(token)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def rotating_keys(monkeypatch):
    """Configure the new key first and the old key second."""
    monkeypatch.setenv("FERNET_KEY", f"{NEW_KEY},{OLD_KEY}")


def _add_mfa(db, secret):
    db.execute(insert(mfa_models.MFAFactor).values(user_id=MOCK_USER_ID, type="totp", credential=secret))
    db.commit()


def _mfa_secret(db):
    return db.execute(select(mfa_models.MFAFactor.credential)).scalar_one()


class TestWalker:
    """The shared walker, exercised through the MFA module."""

    def test_old_key_value_is_rewritten_and_still_decrypts(self, db, rotating_keys):
        _add_mfa(db, _token(OLD_KEY, "totp-secret"))

        mfa_service.reencrypt_stored_secrets(db)

        stored = _mfa_secret(db)
        assert Fernet(NEW_KEY.encode()).decrypt(stored.encode()) == b"totp-secret"
        assert _plain(stored) == "totp-secret"

    def test_first_key_value_is_untouched(self, db, rotating_keys):
        token = _token(NEW_KEY, "totp-secret")
        _add_mfa(db, token)

        mfa_service.reencrypt_stored_secrets(db)

        assert _mfa_secret(db) == token

    def test_undecryptable_value_is_untouched_and_counted(self, db, rotating_keys):
        token = _token(STRANGER_KEY, "totp-secret")
        _add_mfa(db, token)

        counts = core_key_rotation.reencrypt_in_batches(
            "mfa", lambda after_id, limit: mfa_crud.stage_reencrypt_batch_mfa(after_id, limit, db), db
        )

        assert _mfa_secret(db) == token
        assert counts == core_key_rotation.RotationCounts(rotated=0, undecryptable=1)

    def test_nothing_happens_with_one_key(self, db, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", NEW_KEY)
        token = _token(OLD_KEY, "totp-secret")
        _add_mfa(db, token)

        mfa_service.reencrypt_stored_secrets(db)

        assert _mfa_secret(db) == token

    def test_every_batch_is_walked(self, db, rotating_keys, monkeypatch):
        monkeypatch.setattr(core_key_rotation, "BATCH_SIZE", 2)
        for n in range(1, 6):
            db.execute(
                insert(mfa_models.MFAFactor).values(
                    user_id=uuid.UUID(int=n), type="totp", credential=_token(OLD_KEY, f"secret-{n}")
                )
            )
        db.commit()

        mfa_service.reencrypt_stored_secrets(db)

        stored = db.execute(select(mfa_models.MFAFactor.credential).order_by(mfa_models.MFAFactor.user_id)).scalars()
        assert [_plain(value) for value in stored] == [f"secret-{n}" for n in range(1, 6)]
        for value in db.execute(select(mfa_models.MFAFactor.credential)).scalars():
            Fernet(NEW_KEY.encode()).decrypt(value.encode())

    def test_the_first_batch_reads_from_the_first_row(self, db, rotating_keys):
        factor_id = uuid.uuid4()
        db.execute(
            insert(mfa_models.MFAFactor).values(
                id=factor_id, user_id=MOCK_USER_ID, type="totp", credential=_token(OLD_KEY, "first")
            )
        )
        db.commit()

        batch = mfa_crud.stage_reencrypt_batch_mfa(None, 100, db)

        assert batch.last_id == factor_id
        assert batch.counts.rotated == 1
        assert mfa_crud.stage_reencrypt_batch_mfa(factor_id, 100, db).last_id is None

    def test_concurrent_change_is_not_overwritten(self, db, rotating_keys, monkeypatch):
        _add_mfa(db, _token(OLD_KEY, "stale"))
        concurrent = _token(NEW_KEY, "written-meanwhile")
        original = core_cryptography.reencrypt_to_primary_key

        def reencrypt_after_concurrent_write(token):
            rewritten = original(token)
            db.execute(update(mfa_models.MFAFactor).values(credential=concurrent))
            return rewritten

        monkeypatch.setattr(core_cryptography, "reencrypt_to_primary_key", reencrypt_after_concurrent_write)

        counts = core_key_rotation.reencrypt_in_batches(
            "mfa", lambda after_id, limit: mfa_crud.stage_reencrypt_batch_mfa(after_id, limit, db), db
        )

        assert _mfa_secret(db) == concurrent
        assert counts.rotated == 0


class TestModuleWiring:
    """Each module re-encrypts exactly its own encrypted columns."""

    def test_server_settings(self, db, rotating_keys):
        db.execute(
            insert(server_settings_models.ServerSettings).values(
                id=1,
                tileserver_api_key=_token(OLD_KEY, "tiles"),
                geocoding_api_key=_token(NEW_KEY, "geo"),
            )
        )
        db.execute(insert(server_settings_models.MailSettings).values(id=1, password=_token(OLD_KEY, "smtp")))
        db.commit()
        geo = db.execute(select(server_settings_models.ServerSettings.geocoding_api_key)).scalar_one()

        server_settings_service.reencrypt_stored_secrets(db)

        row = db.execute(select(server_settings_models.ServerSettings)).scalar_one()
        mail = db.execute(select(server_settings_models.MailSettings)).scalar_one()
        Fernet(NEW_KEY.encode()).decrypt(row.tileserver_api_key.encode())
        assert (_plain(row.tileserver_api_key), _plain(mail.password)) == ("tiles", "smtp")
        Fernet(NEW_KEY.encode()).decrypt(mail.password.encode())
        assert row.geocoding_api_key == geo

    def test_identity_providers(self, db, rotating_keys):
        db.execute(
            insert(identity_provider_models.IdentityProvider).values(
                id=uuid.uuid4(),
                name="Provider",
                slug="provider",
                client_id=_token(OLD_KEY, "client-id"),
                client_secret=_token(OLD_KEY, "client-secret"),
            )
        )
        db.commit()

        idp_provider_service.reencrypt_stored_secrets(db)

        row = db.execute(select(identity_provider_models.IdentityProvider)).scalar_one()
        assert (_plain(row.client_id), _plain(row.client_secret)) == ("client-id", "client-secret")
        Fernet(NEW_KEY.encode()).decrypt(row.client_id.encode())
        Fernet(NEW_KEY.encode()).decrypt(row.client_secret.encode())

    def test_the_provider_batch_continues_after_a_uuid_cursor(self, db, rotating_keys):
        ids = sorted(uuid.uuid4() for _ in range(2))
        for idp_id in ids:
            db.execute(
                insert(identity_provider_models.IdentityProvider).values(
                    id=idp_id,
                    name=f"Provider {idp_id}",
                    slug=f"provider-{idp_id}",
                    client_id=_token(OLD_KEY, "client-id"),
                    client_secret=_token(OLD_KEY, "client-secret"),
                )
            )
        db.commit()

        first = idp_crud.stage_reencrypt_batch_providers(None, 1, db)
        second = idp_crud.stage_reencrypt_batch_providers(first.last_id, 1, db)

        assert first.last_id == ids[0]
        assert second.last_id == ids[1]
        assert idp_crud.stage_reencrypt_batch_providers(second.last_id, 1, db).last_id is None

    def test_identity_provider_links(self, db, rotating_keys):
        db.execute(
            insert(identity_link_models.IdpSessionToken).values(
                id=uuid.uuid4(),
                session_id="session-1",
                user_id=MOCK_USER_ID,
                idp_id=uuid.uuid4(),
                refresh_token=_token(OLD_KEY, "refresh"),
                id_token=_token(OLD_KEY, "id-token"),
            )
        )
        db.commit()

        identity_links_service.reencrypt_stored_secrets(db)

        stored = db.execute(select(identity_link_models.IdpSessionToken.refresh_token)).scalar_one()
        assert _plain(stored) == "refresh"
        Fernet(NEW_KEY.encode()).decrypt(stored.encode())
        id_token = db.execute(select(identity_link_models.IdpSessionToken.id_token)).scalar_one()
        assert _plain(id_token) == "id-token"
        Fernet(NEW_KEY.encode()).decrypt(id_token.encode())

    def test_rotated_refresh_tokens(self, db, rotating_keys):
        now = datetime.now(UTC)
        db.execute(
            insert(rotated_token_models.RotatedRefreshToken).values(
                id=uuid.uuid4(),
                token_family_id="family",
                hashed_token="hash",
                client_fingerprint="c" * 64,
                rotation_count=1,
                rotated_at=now,
                expires_at=now,
                refresh_token_exp=now,
                replacement_refresh_token=_token(OLD_KEY, "replacement"),
            )
        )
        db.commit()

        rotated_token_service.reencrypt_stored_secrets(db)

        stored = db.execute(select(rotated_token_models.RotatedRefreshToken.replacement_refresh_token)).scalar_one()
        assert _plain(stored) == "replacement"
        Fernet(NEW_KEY.encode()).decrypt(stored.encode())

    def test_users_integrations(self, db, rotating_keys):
        stranger = _token(STRANGER_KEY, "stranger")
        db.execute(
            insert(user_integrations_models.UsersIntegrations).values(
                id=uuid.uuid4(),
                user_id=MOCK_USER_ID,
                strava_client_id=_token(OLD_KEY, "client-id"),
                strava_client_secret=_token(OLD_KEY, "client-secret"),
                strava_token=_token(OLD_KEY, "access"),
                strava_refresh_token=_token(NEW_KEY, "refresh"),
                garminconnect_token={
                    "di_token": _token(OLD_KEY, "di"),
                    "di_refresh_token": stranger,
                    "di_client_id": "plain-client",
                    "is_cn": False,
                },
            )
        )
        db.commit()
        refresh = db.execute(select(user_integrations_models.UsersIntegrations.strava_refresh_token)).scalar_one()

        user_integrations_service.reencrypt_stored_secrets(db)

        row = db.execute(select(user_integrations_models.UsersIntegrations)).scalar_one()
        assert [_plain(row.strava_client_id), _plain(row.strava_client_secret), _plain(row.strava_token)] == [
            "client-id",
            "client-secret",
            "access",
        ]
        Fernet(NEW_KEY.encode()).decrypt(row.strava_token.encode())
        assert row.strava_refresh_token == refresh
        garmin = row.garminconnect_token
        assert _plain(garmin["di_token"]) == "di"
        Fernet(NEW_KEY.encode()).decrypt(garmin["di_token"].encode())
        assert garmin["di_refresh_token"] == stranger
        assert garmin["di_client_id"] == "plain-client"
        assert garmin["is_cn"] is False

    def test_users_integrations_without_garmin_token_is_skipped(self, db, rotating_keys):
        db.execute(insert(user_integrations_models.UsersIntegrations).values(id=uuid.uuid4(), user_id=MOCK_USER_ID))
        db.commit()

        user_integrations_service.reencrypt_stored_secrets(db)

        row = db.execute(select(user_integrations_models.UsersIntegrations)).scalar_one()
        assert not row.garminconnect_token


class TestTokenSwapsSurviveRotation:
    """A refresh-token swap succeeds when the stored token was re-encrypted after the caller read it."""

    _TOKENS: ClassVar[dict[str, object]] = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": 2_000_000_000,
    }

    def _strava_row(self, db, stored):
        db.execute(
            insert(user_integrations_models.UsersIntegrations).values(
                id=uuid.uuid4(), user_id=MOCK_USER_ID, strava_refresh_token=stored
            )
        )
        db.commit()

    def _link_row(self, db, stored):
        db.execute(
            insert(identity_link_models.IdpSessionToken).values(
                id=uuid.uuid4(), session_id="session-1", user_id=MOCK_USER_ID, idp_id=uuid.uuid4(), refresh_token=stored
            )
        )
        db.commit()

    def _rotate(self, token):
        rewritten = core_cryptography.reencrypt_to_primary_key(token)
        assert rewritten is not None
        return rewritten

    def test_strava_replace_after_rotation(self, db, rotating_keys):
        read = _token(OLD_KEY, "refresh")
        self._strava_row(db, self._rotate(read))

        assert (
            user_integrations_crud.replace_strava_tokens_if_refresh_token(MOCK_USER_ID, read, self._TOKENS, db) is True
        )

    def test_strava_replace_with_other_token_fails(self, db, rotating_keys):
        self._strava_row(db, _token(NEW_KEY, "refresh"))

        assert (
            user_integrations_crud.replace_strava_tokens_if_refresh_token(
                MOCK_USER_ID, _token(OLD_KEY, "other"), self._TOKENS, db
            )
            is False
        )

    def test_strava_clear_after_rotation(self, db, rotating_keys):
        read = _token(OLD_KEY, "refresh")
        self._strava_row(db, self._rotate(read))

        assert user_integrations_crud.unlink_strava_tokens_if_refresh_token(MOCK_USER_ID, read, db) is True

    def test_strava_clear_with_other_token_fails(self, db, rotating_keys):
        self._strava_row(db, _token(NEW_KEY, "refresh"))

        assert (
            user_integrations_crud.unlink_strava_tokens_if_refresh_token(MOCK_USER_ID, _token(OLD_KEY, "other"), db)
            is False
        )

    def test_idp_replace_after_rotation(self, db, rotating_keys):
        read = _token(OLD_KEY, "refresh")
        self._link_row(db, self._rotate(read))
        replacement = _token(NEW_KEY, "next")

        assert identity_links_crud.replace_refresh_token_if_unchanged(
            "session-1", read, replacement, datetime.now(UTC), db
        )
        assert db.execute(select(identity_link_models.IdpSessionToken.refresh_token)).scalar_one() == replacement

    def test_idp_replace_with_other_token_fails(self, db, rotating_keys):
        stored = _token(NEW_KEY, "refresh")
        self._link_row(db, stored)

        assert not identity_links_crud.replace_refresh_token_if_unchanged(
            "session-1", _token(OLD_KEY, "other"), _token(NEW_KEY, "next"), datetime.now(UTC), db
        )
        assert db.execute(select(identity_link_models.IdpSessionToken.refresh_token)).scalar_one() == stored

    def test_idp_clear_after_rotation(self, db, rotating_keys):
        read = _token(OLD_KEY, "refresh")
        self._link_row(db, self._rotate(read))

        assert identity_links_crud.clear_refresh_token_if_unchanged("session-1", read, db)
        assert db.execute(select(identity_link_models.IdpSessionToken.refresh_token)).scalar_one() is None

    def test_idp_clear_with_other_token_fails(self, db, rotating_keys):
        stored = _token(NEW_KEY, "refresh")
        self._link_row(db, stored)

        assert not identity_links_crud.clear_refresh_token_if_unchanged("session-1", _token(OLD_KEY, "other"), db)
        assert db.execute(select(identity_link_models.IdpSessionToken.refresh_token)).scalar_one() == stored

    def _garmin_row(self, db, stored):
        db.execute(
            insert(user_integrations_models.UsersIntegrations).values(
                id=uuid.uuid4(), user_id=MOCK_USER_ID, garminconnect_token=stored
            )
        )
        db.commit()

    def test_garmin_swaps_after_rotation(self, db, rotating_keys):
        read = {"di_token": _token(OLD_KEY, "di"), "di_refresh_token": _token(OLD_KEY, "r"), "di_client_id": "c"}
        self._garmin_row(db, read)
        user_integrations_service.reencrypt_stored_secrets(db)

        assert (
            user_integrations_crud.replace_garminconnect_token_if_token(MOCK_USER_ID, read, {"di_token": "new"}, db)
            is True
        )

    def test_garmin_unlink_after_rotation(self, db, rotating_keys):
        read = {"di_token": _token(OLD_KEY, "di"), "di_refresh_token": None, "di_client_id": "c"}
        self._garmin_row(db, read)
        user_integrations_service.reencrypt_stored_secrets(db)

        assert user_integrations_crud.unlink_garminconnect_account_if_token(MOCK_USER_ID, read, db) is True

    def test_garmin_swap_with_other_token_fails(self, db, rotating_keys):
        self._garmin_row(db, {"di_token": _token(NEW_KEY, "di"), "di_client_id": "c"})
        other = {"di_token": _token(OLD_KEY, "other"), "di_client_id": "c"}

        assert (
            user_integrations_crud.replace_garminconnect_token_if_token(MOCK_USER_ID, other, {"di_token": "n"}, db)
            is False
        )
