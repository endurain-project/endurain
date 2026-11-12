"""The start of an SSO flow: the login request, its OAuth state and the browser link."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from authlib.oauth2.rfc7636 import create_s256_code_challenge

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.network as core_network
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

IDP_ID = uuid.uuid4()

HOST = "https://app.example.com"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.fixture
def service():
    return authorization_service.AuthorizationService(MagicMock(), HOST)


def _idp(enabled=True, **overrides):
    values = {"id": 1, "slug": "test", "name": "Test", "enabled": enabled}
    values.update(overrides)
    return SimpleNamespace(**values)


class TestBeginLogin:
    def _begin(self, service, *, idp=None, challenge=CHALLENGE, method="S256", redirect=None, uris=None):
        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "create_login_oauth_state", return_value="state-id") as create_state,
            patch.object(service, "initiate_login", return_value="https://provider.example/auth") as initiate,
        ):
            start = service.begin_login("test", challenge, method, redirect, "10.0.0.1", uris or set(), MagicMock())
        return start, create_state, initiate

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

    def test_a_custom_scheme_redirect_is_refused_without_a_listed_address(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), redirect="gadgetbridge://auth")

    def test_a_redirect_that_leaves_the_app_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), redirect="https://evil.example/")

    def test_an_unlisted_https_redirect_is_refused_when_another_is_listed(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(
                service,
                idp=_idp(),
                redirect="https://evil.example/auth/sso/callback",
                uris={"https://app.example.org/auth/sso/callback"},
            )

    def test_a_listed_https_redirect_means_a_mobile_client(self, service):
        address = "https://app.example.org/auth/sso/callback"
        _, create_state, _ = self._begin(service, idp=_idp(), redirect=address, uris={address})

        assert create_state.call_args.kwargs["client_type"] == "mobile"
        assert create_state.call_args.kwargs["redirect_path"] == address

    def test_only_the_listed_addresses_are_allowed(self, service):
        uris = {"gadgetbridge://auth"}
        self._begin(service, idp=_idp(), redirect="gadgetbridge://auth", uris=uris)
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), redirect="gadgetbridge://done", uris=uris)

    def test_a_valid_request_returns_the_authorization_url(self, service):
        start, create_state, initiate = self._begin(service, idp=_idp(), redirect="/dashboard")

        assert start.authorization_url == "https://provider.example/auth"
        assert create_state.call_args.kwargs["redirect_path"] == "/dashboard"
        assert create_state.call_args.kwargs["ip_address"] == "10.0.0.1"
        assert initiate.call_args.kwargs["oauth_state_id"] == "state-id"

    def test_the_login_is_bound_to_the_browser_that_starts_it(self, service):
        """The state keeps only the digest; the raw secret goes back to the caller for the cookie."""
        start, create_state, _ = self._begin(service, idp=_idp())

        assert start.browser_binding
        assert create_state.call_args.kwargs["browser_binding_hash"] == core_hashing.sha256_hex(start.browser_binding)
        assert start.browser_binding not in create_state.call_args.kwargs.values()

    def test_every_login_gets_its_own_binding(self, service):
        first, _, _ = self._begin(service, idp=_idp())
        second, _, _ = self._begin(service, idp=_idp())

        assert first.browser_binding != second.browser_binding

    @pytest.mark.parametrize("redirect", [None, "/dashboard"])
    def test_a_path_redirect_or_none_means_a_web_client(self, service, redirect):
        _, create_state, _ = self._begin(service, idp=_idp(), redirect=redirect)

        assert create_state.call_args.kwargs["client_type"] == "web"

    def test_a_custom_scheme_redirect_means_a_mobile_client(self, service):
        _, create_state, _ = self._begin(
            service, idp=_idp(), redirect="gadgetbridge://done", uris={"gadgetbridge://done"}
        )

        assert create_state.call_args.kwargs["client_type"] == "mobile"


def test_a_login_oauth_state_is_committed_before_the_browser_is_redirected(mock_db, service):
    with (
        patch.object(
            authorization_service.oauth_state_integration, "create_state_id_and_nonce", return_value=("s", "n")
        ),
        patch.object(authorization_service.oauth_state_integration, "create_oauth_state") as create,
    ):
        state_id = service.create_login_oauth_state(
            IDP_ID,
            client_type="web",
            ip_address="127.0.0.1",
            redirect_path=None,
            code_challenge="c" * 43,
            code_challenge_method="S256",
            browser_binding_hash="h" * 64,
            db=mock_db,
        )

    assert state_id == "s"
    assert create.call_args.kwargs["browser_binding_hash"] == "h" * 64
    assert create.call_args.kwargs["idp_id"] == IDP_ID
    mock_db.commit.assert_called_once()
    assert 43 <= len(create.call_args.kwargs["idp_code_verifier"]) <= 128


def test_the_authorization_url_carries_the_s256_challenge_of_the_states_verifier(mock_db):
    """PKCE between this server and the provider: a leaked code is useless without the verifier."""
    oidc = oidc_client_service.OidcClientService(MagicMock(), "v1")
    service = authorization_service.AuthorizationService(oidc, HOST)
    verifier = "v" * 64
    idp = SimpleNamespace(
        id=IDP_ID, slug="idp", name="IdP", scopes="openid email", authorization_endpoint="https://idp.example/authorize"
    )
    state = SimpleNamespace(nonce="nonce-1", idp_code_verifier=verifier)
    with (
        patch.object(authorization_service.core_network, "reject_private_url"),
        patch.object(oidc, "decrypt_client_id", return_value="cid"),
        patch.object(
            authorization_service.oauth_state_integration, "get_oauth_state_by_id_and_not_used", return_value=state
        ),
    ):
        url = service.initiate_login(idp, mock_db, "/", oauth_state_id="state-1")

    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge"] == [create_s256_code_challenge(verifier)]
    assert query["code_challenge_method"] == ["S256"]


def test_the_transaction_ends_before_discovery_reaches_the_provider(mock_db):
    """A pooled connection is not held while the issuer's discovery document is fetched."""
    oidc = MagicMock()
    service = authorization_service.AuthorizationService(oidc, HOST)
    idp = SimpleNamespace(
        id=IDP_ID,
        slug="idp",
        name="IdP",
        scopes="openid",
        authorization_endpoint=None,
        issuer_url="https://idp.example",
    )
    oidc.get_oidc_configuration.return_value = {"authorization_endpoint": "https://idp.example/authorize"}
    oidc.decrypt_client_id.return_value = "cid"
    state = SimpleNamespace(nonce="nonce-1", idp_code_verifier="v" * 64)
    order = MagicMock()
    order.attach_mock(mock_db.commit, "commit")
    order.attach_mock(oidc.get_oidc_configuration, "discovery")
    with (
        patch.object(authorization_service.core_network, "reject_private_url"),
        patch.object(
            authorization_service.oauth_state_integration, "get_oauth_state_by_id_and_not_used", return_value=state
        ),
    ):
        service.initiate_login(idp, mock_db, oauth_state_id="state-1")

    assert [call[0] for call in order.mock_calls] == ["commit", "discovery"]


class TestAuthorizationEndpointGuard:
    """The browser is only sent to an authorization endpoint the server would itself be willing to dial over TLS."""

    @staticmethod
    def _url(service, endpoint):
        idp = _idp(authorization_endpoint=endpoint, scopes=None, issuer_url=None)
        with patch.object(service._oidc, "decrypt_client_id", return_value="cid"):
            staged = SimpleNamespace(idp=idp, purpose=None, state_id="state-1", nonce="nonce-1", idp_code_verifier=None)
            return service.authorization_url(staged)

    @pytest.fixture
    def service(self):
        return authorization_service.AuthorizationService(MagicMock(), HOST)

    def test_plain_http_to_a_public_host_is_refused(self, service):
        with (
            patch("core.network.socket.getaddrinfo", return_value=[(2, 1, 0, "", ("8.8.8.8", 0))]),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
            pytest.raises(core_exceptions.InvalidInputError, match="must use https"),
        ):
            self._url(service, "http://idp.example.com/authorize")

    def test_plain_http_to_an_allowlisted_host_is_allowed(self, service):
        with (
            patch("core.network.socket.getaddrinfo", return_value=[(2, 1, 0, "", ("10.0.0.5", 0))]),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]),
        ):
            url = self._url(service, "http://idp.example.com/authorize")
        assert url.startswith("http://idp.example.com/authorize?")

    def test_https_to_a_public_host_is_allowed(self, service):
        with (
            patch("core.network.socket.getaddrinfo", return_value=[(2, 1, 0, "", ("8.8.8.8", 0))]),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
        ):
            url = self._url(service, "https://idp.example.com/authorize")
        assert url.startswith("https://idp.example.com/authorize?")
