"""The tokens of ended sessions are revoked at their provider (RFC 7009) and then forgotten."""

import logging
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from cryptography.fernet import Fernet

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.service as identity_links_service
import modules.auth.identity_providers.token_revocation_service as revocation_module
from tests._helpers.db import create_sqlite_session_factory

IDP_ID = uuid.uuid4()
OTHER_IDP_ID = uuid.uuid4()

ENDPOINT = "https://idp.example/revoke"


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    with patch.object(revocation_module.core_database, "SessionLocal", session_factory):
        yield session_factory
    session_factory.kw["bind"].dispose()


@pytest.fixture
def oidc():
    client = MagicMock()
    client.revoke_token.return_value = MagicMock(status_code=200)
    oidc = MagicMock()
    oidc.resolve_revocation_endpoint.return_value = ENDPOINT
    oidc.decrypt_client_id.return_value = "cid"
    oidc.decrypt_client_secret.return_value = "secret"
    oidc.create_oauth_client.return_value = client
    return oidc


def _store(factory, session_id, *, refresh="plain", user_id=7, idp_id=IDP_ID):
    encrypted = core_cryptography.encrypt_token_fernet(refresh) if refresh is not None else None
    with factory() as db:
        identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, encrypted, None, db)
        db.commit()
    return encrypted


def _rows(factory):
    with factory() as db:
        return {row.session_id: row for row in identity_links_crud.get_idp_session_tokens_page(None, 100, db)}


def _run(oidc, factory, *, alive=(), user_id=None, idp=True):
    """Revoke the ended sessions, with ``alive`` naming the sessions that still exist."""
    service = revocation_module.IdpTokenRevocationService(oidc)
    provider = MagicMock(id=IDP_ID, enabled=True) if idp else None
    with (
        patch.object(
            identity_links_service.sessions_integration,
            "get_existing_session_ids",
            side_effect=lambda ids, db: set(ids) & set(alive),
        ),
        patch.object(revocation_module.idp_crud, "get_identity_provider", return_value=provider),
    ):
        return service.revoke_ended_sessions(user_id=user_id)


class TestRevokeEndedSessions:
    def test_the_refresh_token_is_posted_to_the_revocation_endpoint_and_the_row_is_deleted(self, oidc, factory):
        _store(factory, "gone", refresh="plain-refresh")

        deleted = _run(oidc, factory)

        assert deleted == 1
        client = oidc.create_oauth_client.return_value
        client.revoke_token.assert_called_once_with(ENDPOINT, token="plain-refresh", token_type_hint="refresh_token")
        client.close.assert_called_once()
        assert _rows(factory) == {}

    def test_the_client_authenticates_with_the_providers_credentials(self, oidc, factory):
        _store(factory, "gone")

        _run(oidc, factory)

        oidc.create_oauth_client.assert_called_once_with(client_id="cid", client_secret="secret")

    def test_a_session_that_still_exists_is_left_alone(self, oidc, factory):
        _store(factory, "alive")
        _store(factory, "gone")

        _run(oidc, factory, alive=("alive",))

        assert set(_rows(factory)) == {"alive"}
        oidc.create_oauth_client.return_value.revoke_token.assert_called_once()

    def test_only_the_named_users_sessions_are_handled(self, oidc, factory):
        _store(factory, "mine", user_id=7)
        _store(factory, "theirs", user_id=8)

        _run(oidc, factory, user_id=7)

        assert set(_rows(factory)) == {"theirs"}

    def test_an_orphan_from_the_sweep_is_handled_without_an_event(self, oidc, factory):
        """The sweep names no user: it covers sessions that expired or were purged with no event."""
        _store(factory, "expired", user_id=7)
        _store(factory, "purged", user_id=8)

        assert _run(oidc, factory) == 2
        assert _rows(factory) == {}

    def test_a_provider_without_a_revocation_endpoint_only_forgets_the_row(self, oidc, factory):
        oidc.resolve_revocation_endpoint.return_value = None
        _store(factory, "gone")

        assert _run(oidc, factory) == 1

        oidc.create_oauth_client.assert_not_called()
        assert _rows(factory) == {}

    def test_a_sign_in_that_holds_no_token_is_deleted_without_a_provider_call(self, oidc, factory):
        _store(factory, "gone", refresh=None)

        assert _run(oidc, factory) == 1

        oidc.resolve_revocation_endpoint.assert_not_called()
        assert _rows(factory) == {}

    def test_a_token_no_key_decrypts_is_deleted_without_a_provider_call(self, oidc, factory):
        with factory() as db:
            identity_links_crud.create_idp_session_token("gone", 7, IDP_ID, "not-a-fernet-token", None, db)
            db.commit()

        assert _run(oidc, factory) == 1

        oidc.resolve_revocation_endpoint.assert_not_called()
        assert _rows(factory) == {}

    def test_a_key_that_cannot_be_loaded_keeps_the_row(self, oidc, factory):
        _store(factory, "gone")
        with patch.object(
            revocation_module.core_cryptography, "decrypt_token_fernet", side_effect=core_exceptions.CryptographyError()
        ):
            assert _run(oidc, factory) == 0

        assert set(_rows(factory)) == {"gone"}

    def test_a_provider_that_no_longer_exists_only_forgets_the_row(self, oidc, factory):
        _store(factory, "gone")

        assert _run(oidc, factory, idp=False) == 1

        oidc.resolve_revocation_endpoint.assert_not_called()
        assert _rows(factory) == {}

    @pytest.mark.parametrize("status_code", [200, 400, 401, 403])
    def test_an_answer_that_settles_the_request_deletes_the_row(self, oidc, factory, status_code):
        """A 2xx revoked it; any other answer below 500 refuses it for good, which a retry would not change."""
        oidc.create_oauth_client.return_value.revoke_token.return_value = MagicMock(status_code=status_code)
        _store(factory, "gone")

        assert _run(oidc, factory) == 1
        assert _rows(factory) == {}

    @pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503])
    def test_a_server_error_or_a_retryable_answer_keeps_the_row_for_a_retry(self, oidc, factory, status_code):
        oidc.create_oauth_client.return_value.revoke_token.return_value = MagicMock(status_code=status_code)
        _store(factory, "gone")

        assert _run(oidc, factory) == 0
        assert set(_rows(factory)) == {"gone"}

    @pytest.mark.parametrize("error", [httpx2.ConnectError("down"), httpx2.ReadTimeout("slow")])
    def test_a_network_error_keeps_the_row_for_a_retry(self, oidc, factory, error):
        oidc.create_oauth_client.return_value.revoke_token.side_effect = error
        _store(factory, "gone")

        assert _run(oidc, factory) == 0

        assert set(_rows(factory)) == {"gone"}
        oidc.create_oauth_client.return_value.close.assert_called_once()

    def test_an_unreachable_discovery_document_keeps_the_row_for_a_retry(self, oidc, factory):
        oidc.resolve_revocation_endpoint.side_effect = core_exceptions.UpstreamError("unavailable")
        _store(factory, "gone")

        assert _run(oidc, factory) == 0
        assert set(_rows(factory)) == {"gone"}

    def test_an_endpoint_the_ssrf_guard_refuses_only_forgets_the_row(self, oidc, factory):
        oidc.resolve_revocation_endpoint.side_effect = core_exceptions.InvalidInputError("private address")
        _store(factory, "gone")

        assert _run(oidc, factory) == 1
        assert _rows(factory) == {}

    def test_an_unreachable_provider_is_not_called_again_for_its_other_sessions(self, oidc, factory):
        oidc.create_oauth_client.return_value.revoke_token.side_effect = httpx2.ConnectError("down")
        for session_id in ("a", "b", "c"):
            _store(factory, session_id)

        _run(oidc, factory)

        oidc.create_oauth_client.return_value.revoke_token.assert_called_once()
        assert set(_rows(factory)) == {"a", "b", "c"}

    def test_an_unreachable_provider_does_not_stop_another_providers_sessions(self, oidc, factory):
        oidc.create_oauth_client.return_value.revoke_token.side_effect = [
            httpx2.ConnectError("down"),
            MagicMock(status_code=200),
        ]
        _store(factory, "slow-idp", idp_id=IDP_ID)
        _store(factory, "other-idp", idp_id=OTHER_IDP_ID)
        first_by_id = next(iter(_rows(factory)))

        assert _run(oidc, factory) == 1
        assert set(_rows(factory)) == {first_by_id}

    def test_a_provider_error_for_one_session_does_not_stop_the_others(self, oidc, factory):
        oidc.decrypt_client_secret.side_effect = [core_exceptions.ProcessingError("bad secret"), "secret"]
        _store(factory, "a")
        _store(factory, "b")
        first_by_id = next(iter(_rows(factory)))

        assert _run(oidc, factory) == 1
        assert set(_rows(factory)) == {first_by_id}

    def test_a_token_another_refresh_stored_meanwhile_is_not_deleted(self, oidc, factory):
        """The row holds the token that was read when the provider was called, or it is kept for the next pass."""
        _store(factory, "gone", refresh="old")

        def refresh_meanwhile(*_args, **_kwargs):
            with factory() as db:
                identity_links_crud.replace_refresh_token_if_unchanged(
                    "gone",
                    core_cryptography.encrypt_token_fernet("old"),
                    core_cryptography.encrypt_token_fernet("new"),
                    datetime.now(UTC),
                    db,
                )
                db.commit()
            return MagicMock(status_code=200)

        oidc.create_oauth_client.return_value.revoke_token.side_effect = refresh_meanwhile

        assert _run(oidc, factory) == 0
        assert core_cryptography.decrypt_token_fernet(_rows(factory)["gone"].refresh_token) == "new"

    def test_a_large_table_is_walked_in_windows(self, oidc, factory):
        for index in range(5):
            _store(factory, f"gone-{index}")

        with patch.object(revocation_module, "BATCH_SIZE", 2):
            assert _run(oidc, factory) == 5
        assert _rows(factory) == {}

    def test_the_token_is_never_logged(self, oidc, factory, caplog):
        oidc.create_oauth_client.return_value.revoke_token.return_value = MagicMock(status_code=400)
        _store(factory, "gone", refresh="secret-refresh-value")

        with caplog.at_level(logging.DEBUG):
            _run(oidc, factory)

        assert "secret-refresh-value" not in caplog.text

    def test_no_database_session_is_open_during_the_provider_call(self, oidc, factory):
        _store(factory, "gone")
        open_sessions = 0
        open_during_call = []
        real_factory = factory

        class _Counting:
            def __call__(self):
                return self

            def __enter__(self):
                nonlocal open_sessions
                open_sessions += 1
                self._db = real_factory()
                return self._db

            def __exit__(self, *exc):
                nonlocal open_sessions
                open_sessions -= 1
                self._db.close()
                return False

        def call(*_args, **_kwargs):
            open_during_call.append(open_sessions)
            return MagicMock(status_code=200)

        oidc.create_oauth_client.return_value.revoke_token.side_effect = call
        with patch.object(revocation_module.core_database, "SessionLocal", _Counting()):
            _run(oidc, factory)

        assert open_during_call == [0]
