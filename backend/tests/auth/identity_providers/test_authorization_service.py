"""The start of an SSO flow: the login request, its OAuth state and the browser link."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge

import core.exceptions as core_exceptions
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

HOST = "https://app.example.com"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
ALLOWED = {"gadgetbridge"}


@pytest.fixture
def service():
    return authorization_service.AuthorizationService(MagicMock(), HOST)


def _idp(enabled=True, **overrides):
    values = {"id": 1, "slug": "test", "name": "Test", "enabled": enabled}
    values.update(overrides)
    return SimpleNamespace(**values)


class TestBeginLogin:
    def _begin(self, service, *, idp=None, challenge=CHALLENGE, method="S256", redirect=None, header=None):
        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "create_login_oauth_state", return_value="state-id") as create_state,
            patch.object(service, "initiate_login", return_value="https://provider.example/auth") as initiate,
        ):
            url = service.begin_login("test", challenge, method, redirect, "10.0.0.1", header, ALLOWED, MagicMock())
        return url, create_state, initiate

    def test_an_unknown_provider_is_not_found(self, service):
        with pytest.raises(core_exceptions.NotFoundError):
            self._begin(service, idp=None)

    def test_a_disabled_provider_is_not_found(self, service):
        with pytest.raises(core_exceptions.NotFoundError):
            self._begin(service, idp=_idp(enabled=False))

    @pytest.mark.parametrize(("challenge", "method"), [("", "S256"), (CHALLENGE, ""), (CHALLENGE, "plain")])
    def test_pkce_is_mandatory_and_s256(self, service, challenge, method):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), challenge=challenge, method=method)

    def test_a_malformed_challenge_is_refused(self, service):
        with pytest.raises(core_exceptions.DomainError):
            self._begin(service, idp=_idp(), challenge="short")

    def test_a_redirect_that_leaves_the_app_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), redirect="https://evil.example/")

    def test_a_valid_request_returns_the_authorization_url(self, service):
        url, create_state, initiate = self._begin(service, idp=_idp(), redirect="/dashboard")

        assert url == "https://provider.example/auth"
        assert create_state.call_args.kwargs["redirect_path"] == "/dashboard"
        assert create_state.call_args.kwargs["ip_address"] == "10.0.0.1"
        assert initiate.call_args.kwargs["oauth_state_id"] == "state-id"

    @pytest.mark.parametrize(("header", "expected"), [(None, "web"), ("mobile", "mobile"), ("desktop", "web")])
    def test_the_client_type_comes_from_the_header_and_defaults_to_web(self, service, header, expected):
        _, create_state, _ = self._begin(service, idp=_idp(), header=header)

        assert create_state.call_args.kwargs["client_type"] == expected

    def test_a_custom_scheme_redirect_means_a_mobile_client(self, service):
        _, create_state, _ = self._begin(service, idp=_idp(), redirect="gadgetbridge://done", header="web")

        assert create_state.call_args.kwargs["client_type"] == "mobile"


def test_a_login_oauth_state_is_committed_before_the_browser_is_redirected(mock_db, service):
    with (
        patch.object(
            authorization_service.oauth_state_integration, "create_state_id_and_nonce", return_value=("s", "n")
        ),
        patch.object(authorization_service.oauth_state_integration, "create_oauth_state") as create,
    ):
        state_id = service.create_login_oauth_state(
            3,
            client_type="web",
            ip_address="127.0.0.1",
            redirect_path=None,
            code_challenge="c" * 43,
            code_challenge_method="S256",
            db=mock_db,
        )

    assert state_id == "s"
    assert create.call_args.kwargs["idp_id"] == 3
    mock_db.commit.assert_called_once()
    assert 43 <= len(create.call_args.kwargs["idp_code_verifier"]) <= 128


def test_the_authorization_url_carries_the_s256_challenge_of_the_states_verifier(mock_db):
    """PKCE between this server and the provider: a leaked code is useless without the verifier."""
    oidc = oidc_client_service.OidcClientService(MagicMock(), "v1")
    service = authorization_service.AuthorizationService(oidc, HOST)
    verifier = "v" * 64
    idp = SimpleNamespace(
        id=3, slug="idp", name="IdP", scopes="openid email", authorization_endpoint="https://idp.example/authorize"
    )
    state = SimpleNamespace(nonce="nonce-1", idp_code_verifier=verifier)
    with (
        patch.object(oidc, "decrypt_client_id", return_value="cid"),
        patch.object(
            authorization_service.oauth_state_integration, "get_oauth_state_by_id_and_not_used", return_value=state
        ),
    ):
        url = service.initiate_login(idp, "/", mock_db, oauth_state_id="state-1")

    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge"] == [create_s256_code_challenge(verifier)]
    assert query["code_challenge_method"] == ["S256"]
