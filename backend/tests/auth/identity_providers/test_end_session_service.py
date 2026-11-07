"""RP-initiated logout: the session's ID token and the provider URL that ends the provider's session."""

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.end_session_service as end_session_module

SESSION = "11111111-1111-1111-1111-111111111111"
LOGIN = "https://endurain.example.com/login"


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture
def oidc():
    client = MagicMock()
    client.resolve_end_session_endpoint.return_value = "https://idp.example.com/logout"
    client.decrypt_client_id.return_value = "client-1"
    return client


def _idp():
    now = datetime.now(UTC)
    return idp_contracts.IdentityProviderState(
        id=3,
        name="Test IdP",
        slug="test",
        provider_type="oidc",
        enabled=True,
        client_id="enc-client",
        client_secret="enc-secret",
        issuer_url="https://idp.example.com",
        authorization_endpoint=None,
        token_endpoint=None,
        userinfo_endpoint=None,
        jwks_uri=None,
        scopes=None,
        icon=None,
        icon_uploaded=False,
        auto_create_users=False,
        sync_user_info=False,
        user_mapping=None,
        created_at=now,
        updated_at=now,
        version=1,
    )


def _service(oidc):
    return end_session_module.EndSessionService(oidc)


def _request(token):
    return idp_contracts.EndSessionRequest(
        idp=_idp(),
        encrypted_id_token=core_cryptography.encrypt_token_fernet(token),
    )


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


class TestReadEndSession:
    """The ID token and provider are read while the caller's transaction is still open."""

    def _read(self, *, row, idp=True):
        with (
            patch.object(
                end_session_module.identity_provider_links_integration, "get_idp_session_token", return_value=row
            ),
            patch.object(end_session_module.idp_crud, "get_identity_provider", return_value=_idp() if idp else None),
        ):
            return _service(MagicMock()).read_end_session(SESSION, MagicMock())

    def test_a_sign_in_that_holds_an_id_token_is_returned_with_its_provider(self):
        row = MagicMock(idp_id=3, id_token="ciphertext")

        request = self._read(row=row)

        assert request is not None
        assert request.encrypted_id_token == "ciphertext"

    def test_a_session_that_signed_in_through_no_provider_has_nothing_to_end(self):
        assert self._read(row=None) is None

    def test_a_sign_in_without_an_id_token_has_nothing_to_hint(self):
        assert self._read(row=MagicMock(idp_id=3, id_token=None)) is None

    def test_a_provider_that_no_longer_exists_has_nothing_to_end(self):
        assert self._read(row=MagicMock(idp_id=3, id_token="ciphertext"), idp=False) is None

    def test_the_encrypted_token_is_not_in_the_repr(self):
        assert "ciphertext" not in repr(idp_contracts.EndSessionRequest(idp=_idp(), encrypted_id_token="ciphertext"))


class TestEndSessionUrl:
    """The URL carries the hint, the client and, for the web app, the page to come back to."""

    def test_the_url_carries_the_hint_the_client_and_the_return_address(self, oidc):
        url = _service(oidc).end_session_url(_request("the-id-token"), LOGIN)

        assert url is not None
        assert url.startswith("https://idp.example.com/logout?")
        assert _query(url) == {
            "id_token_hint": "the-id-token",
            "client_id": "client-1",
            "post_logout_redirect_uri": LOGIN,
        }

    def test_without_a_return_address_the_url_has_none(self, oidc):
        url = _service(oidc).end_session_url(_request("the-id-token"), None)

        assert url is not None
        assert _query(url) == {"id_token_hint": "the-id-token", "client_id": "client-1"}

    def test_a_query_string_the_endpoint_already_has_is_kept(self, oidc):
        oidc.resolve_end_session_endpoint.return_value = "https://idp.example.com/logout?tenant=a%20b&x="

        url = _service(oidc).end_session_url(_request("the-id-token"), LOGIN)

        assert url is not None
        assert urlsplit(url).path == "/logout"
        query = _query(url)
        assert query["tenant"] == "a b"
        assert query["x"] == ""
        assert query["id_token_hint"] == "the-id-token"

    def test_a_provider_without_an_end_session_endpoint_has_no_url(self, oidc):
        oidc.resolve_end_session_endpoint.return_value = None

        assert _service(oidc).end_session_url(_request("the-id-token"), LOGIN) is None

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.UpstreamError("discovery unavailable"),
            core_exceptions.InvalidInputError("ssrf refused"),
        ],
    )
    def test_a_provider_failure_is_a_warning_and_no_url(self, oidc, caplog, error):
        oidc.resolve_end_session_endpoint.side_effect = error

        with caplog.at_level(logging.DEBUG):
            assert _service(oidc).end_session_url(_request("secret-token"), LOGIN) is None

        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]
        assert "secret-token" not in caplog.text

    def test_an_id_token_that_cannot_be_decrypted_is_a_warning_and_no_url(self, oidc, caplog):
        request = idp_contracts.EndSessionRequest(idp=_idp(), encrypted_id_token="not-a-fernet-token")

        with caplog.at_level(logging.DEBUG):
            assert _service(oidc).end_session_url(request, LOGIN) is None

        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]

    def test_the_id_token_is_never_logged_on_success(self, oidc, caplog):
        with caplog.at_level(logging.DEBUG):
            _service(oidc).end_session_url(_request("secret-token"), LOGIN)

        assert "secret-token" not in caplog.text
