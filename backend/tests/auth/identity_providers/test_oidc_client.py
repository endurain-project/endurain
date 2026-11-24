"""The client that reaches a provider's discovery document, signing keys and endpoints, over real HTTP.

The provider is the loopback one of the SSO tests; the cache it fills is the platform's in-memory state, and an
outage is a state backend that is down.
"""

import httpx2
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.config as core_config
import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.network as core_network
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
from tests._factories.identity_links import make_oidc_provider
from tests.auth.identity_providers.test_state_stores import DownState


class CooldownDown(MemoryState):
    """A state whose cooldown claims fail while its cache still answers."""

    def __init__(self) -> None:
        super().__init__(jasil_testing.FixedClock())

    def set_if_absent(self, key, value, *args, **kwargs):
        raise StateBackendUnavailableError("down")


@pytest.fixture
def make_idp(committed_sessions, provider):
    """Return a function that commits a provider and reads it back as the services see it."""

    def make(slug: str = "acme", **fields):
        with committed_sessions() as db:
            idp_id = make_oidc_provider(db, slug, fields.pop("issuer_url", provider.issuer), **fields)
            db.commit()
        with committed_sessions() as db:
            return idp_crud.get_identity_provider(idp_id, db)

    return make


@pytest.fixture
def client() -> oidc_client_service.OidcClientService:
    return oidc_client_service.OidcClientService(MemoryState(jasil_testing.FixedClock()), "test")


class TestDiscovery:
    def test_the_document_is_fetched_once_and_then_served_from_the_cache(self, client, make_idp, provider):
        idp = make_idp()

        first = client.get_oidc_configuration(idp)
        second = client.get_oidc_configuration(idp)

        assert first == second == provider.discovery_document()
        assert len(provider.requests_to("/.well-known/openid-configuration")) == 1

    def test_a_forgotten_document_is_fetched_afresh(self, client, make_idp, provider):
        idp = make_idp()
        client.get_oidc_configuration(idp)

        client.forget_discovery(idp.id)
        client.get_oidc_configuration(idp)

        assert len(provider.requests_to("/.well-known/openid-configuration")) == 2

    def test_the_issuer_the_document_names_must_be_the_configured_one(self, client, make_idp, provider):
        idp = make_idp()
        provider.discovery = {"issuer": "https://another-issuer.example"}

        assert client.get_oidc_configuration(idp) is None
        assert client.get_oidc_configuration(idp) is None
        assert len(provider.requests_to("/.well-known/openid-configuration")) == 2

    @pytest.mark.parametrize(
        "break_it",
        [
            lambda provider: setattr(provider, "discovery_status", 500),
            lambda provider: setattr(provider, "discovery_raw", b"<html>not json</html>"),
            lambda provider: setattr(provider, "discovery_raw", [1, 2]),
        ],
        ids=["server-error", "not-json", "not-an-object"],
    )
    def test_a_document_that_cannot_be_read_is_none_and_not_cached(self, break_it, client, make_idp, provider):
        idp = make_idp()
        break_it(provider)

        assert client.get_oidc_configuration(idp) is None

        provider.discovery_status, provider.discovery_raw = 200, None
        assert client.get_oidc_configuration(idp) is not None

    def test_a_provider_that_answers_too_slowly_has_no_document(self, client, make_idp, provider, monkeypatch):
        idp = make_idp()
        provider.delays = {"/.well-known/openid-configuration": 0.6}
        # The client waits ten seconds; the test shortens only that wait.
        monkeypatch.setattr(
            client,
            "http_client",
            lambda: httpx2.Client(transport=core_network.PinnedAddressTransport(purpose="oidc_client"), timeout=0.2),
        )

        assert client.get_oidc_configuration(idp) is None

    def test_a_provider_that_cannot_be_reached_has_no_document(self, client, make_idp):
        assert client.get_oidc_configuration(make_idp(issuer_url="http://127.0.0.1:9")) is None

    def test_a_provider_without_an_issuer_has_no_document(self, client, make_idp):
        idp = make_idp(provider_type="oauth2", issuer_url=None, scopes="profile")

        assert client.get_oidc_configuration(idp) is None

    def test_an_issuer_on_a_private_address_is_refused_unless_the_host_is_allowed(
        self, client, make_idp, provider, monkeypatch
    ):
        idp = make_idp()
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        assert client.get_oidc_configuration(idp) is None
        assert provider.requests == []

    def test_a_cache_that_is_down_or_holds_garbage_costs_a_fetch_and_nothing_more(self, make_idp, provider):
        idp = make_idp()
        down = oidc_client_service.OidcClientService(DownState(), "test")
        garbage_state = MemoryState(jasil_testing.FixedClock())
        garbage = oidc_client_service.OidcClientService(garbage_state, "test")
        garbage_state.set(garbage._discovery_key(idp.id), b"{not json", ttl_seconds=60)

        assert down.get_oidc_configuration(idp) == provider.discovery_document()
        assert garbage.get_oidc_configuration(idp) == provider.discovery_document()
        down.forget_discovery(idp.id)


class TestSigningKeys:
    def test_the_key_set_is_fetched_once_and_cached(self, client, provider):
        first = client.fetch_jwks(provider.jwks_uri)
        second = client.fetch_jwks(provider.jwks_uri)

        assert first == second
        assert [key["kid"] for key in first["keys"]] == ["test-key-1"]
        assert len(provider.requests_to("/jwks")) == 1

    def test_a_refresh_fetches_afresh_at_most_once_per_cooldown(self, client, provider):
        client.fetch_jwks(provider.jwks_uri)

        client.fetch_jwks(provider.jwks_uri, refresh=True)
        client.fetch_jwks(provider.jwks_uri, refresh=True)

        assert len(provider.requests_to("/jwks")) == 2

    def test_a_refresh_while_the_cooldown_is_unavailable_uses_the_cached_set(self, provider):
        state = MemoryState(jasil_testing.FixedClock())
        working = oidc_client_service.OidcClientService(state, "test")
        working.fetch_jwks(provider.jwks_uri)

        degraded = oidc_client_service.OidcClientService(CooldownDown(), "test")
        degraded._state.set(degraded._jwks_key(provider.jwks_uri), state.get(working._jwks_key(provider.jwks_uri)))

        assert degraded.fetch_jwks(provider.jwks_uri, refresh=True)["keys"]
        assert len(provider.requests_to("/jwks")) == 1

    @pytest.mark.parametrize(
        ("raw", "error", "detail"),
        [
            ({"nothing": "here"}, core_exceptions.UpstreamError, "invalid JWKS format"),
            (b"<html>no</html>", core_exceptions.UpstreamError, "invalid JWKS JSON"),
        ],
    )
    def test_a_key_document_that_is_not_one_is_an_upstream_error(self, raw, error, detail, client, provider):
        provider.jwks_raw = raw

        with pytest.raises(error, match=detail):
            client.fetch_jwks(provider.jwks_uri)

    def test_an_endpoint_that_answers_with_an_error_is_an_upstream_error(self, client, provider):
        provider.discovery = {"jwks_uri": f"{provider.issuer}/missing"}

        with pytest.raises(core_exceptions.UpstreamError, match="404"):
            client.fetch_jwks(f"{provider.issuer}/missing")

    def test_an_endpoint_that_answers_too_slowly_is_a_timeout(self, client, provider, monkeypatch):
        provider.delays = {"/jwks": 0.6}
        # The client waits ten seconds; the test shortens only that wait.
        monkeypatch.setattr(
            client,
            "http_client",
            lambda: httpx2.Client(transport=core_network.PinnedAddressTransport(purpose="oidc_client"), timeout=0.2),
        )

        with pytest.raises(oidc_client_service.UpstreamTimeoutError):
            client.fetch_jwks(provider.jwks_uri)

    def test_an_endpoint_on_a_private_address_is_refused_unless_the_host_is_allowed(
        self, client, provider, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        with pytest.raises(core_exceptions.InvalidInputError):
            client.fetch_jwks(provider.jwks_uri)
        assert provider.requests == []

    def test_an_endpoint_that_cannot_be_reached_fails_the_fetch(self, client):
        with pytest.raises(core_exceptions.DomainError):
            client.fetch_jwks("http://127.0.0.1:9/jwks")


class TestCredentials:
    def test_the_client_id_and_secret_are_read_back_in_plain_text(self, client, make_idp):
        idp = make_idp()

        assert client.decrypt_client_id(idp) == "endurain-client"
        assert client.decrypt_client_secret(idp) == "endurain-secret"

    @pytest.mark.parametrize("field", ["client_id", "client_secret"])
    def test_a_credential_the_key_cannot_decrypt_is_a_configuration_error(self, field, client, make_idp):
        idp = make_idp().model_copy(update={field: "not-encrypted"})

        with pytest.raises(core_exceptions.ProcessingError, match="configuration error"):
            (client.decrypt_client_id if field == "client_id" else client.decrypt_client_secret)(idp)

    @pytest.mark.parametrize("field", ["client_id", "client_secret"])
    def test_a_credential_that_decrypts_to_nothing_is_a_configuration_error(self, field, client, make_idp):
        idp = make_idp().model_copy(update={field: core_cryptography.encrypt_token_fernet("")})

        with pytest.raises(core_exceptions.ProcessingError, match="configuration error"):
            (client.decrypt_client_id if field == "client_id" else client.decrypt_client_secret)(idp)


class TestUserinfo:
    """What a sign-in learns about the user, asked of the client directly with the token answer a provider gave."""

    @pytest.fixture
    def oauth_client(self, client):
        with client.create_oauth_client("endurain-client", "endurain-secret") as oauth_client:
            yield oauth_client

    def _token_response(self, provider, **claims):
        claims = provider.id_token_claims_for(client_id="endurain-client", nonce=None, access_token=None) | claims
        return {"access_token": "at", "id_token": provider.sign(claims)}

    def _get(self, client, oauth_client, provider, token_response, *, endpoint="USERINFO", require_id_token=True):
        return client.get_userinfo(
            token_response,
            provider.userinfo_endpoint if endpoint == "USERINFO" else endpoint,
            oauth_client,
            provider.jwks_uri,
            provider.issuer,
            "endurain-client",
            require_id_token=require_id_token,
        )

    def test_a_required_id_token_needs_the_signing_keys_the_provider_publishes(self, client, oauth_client, provider):
        with pytest.raises(core_exceptions.UpstreamError, match="no issuer or signing keys"):
            client.get_userinfo(
                self._token_response(provider), None, oauth_client, None, None, "endurain-client", require_id_token=True
            )

    def test_a_required_id_token_that_the_response_lacks_is_an_upstream_error(self, client, oauth_client, provider):
        with pytest.raises(core_exceptions.UpstreamError, match="no ID token"):
            self._get(client, oauth_client, provider, {"access_token": "at"})

    def test_without_a_userinfo_endpoint_the_verified_id_token_is_the_identity(self, client, oauth_client, provider):
        claims = self._get(client, oauth_client, provider, self._token_response(provider, sub="alice"), endpoint=None)

        assert claims["sub"] == "alice"
        assert provider.requests_to("/userinfo") == []

    def test_a_response_without_an_access_token_asks_userinfo_nothing(self, client, oauth_client, provider):
        token_response = self._token_response(provider, sub="alice")
        del token_response["access_token"]

        claims = self._get(client, oauth_client, provider, token_response)

        assert claims["sub"] == "alice"
        assert provider.requests_to("/userinfo") == []

    def test_userinfo_is_the_identity_of_a_provider_that_issues_no_id_token(self, client, oauth_client, provider):
        provider.userinfo_body = {"sub": "alice", "sid": "dropped", "email": "a@example.com"}

        claims = self._get(client, oauth_client, provider, {"access_token": "at"}, require_id_token=False)

        assert claims == {"sub": "alice", "email": "a@example.com"}

    def test_an_id_token_that_cannot_be_verified_without_keys_and_no_userinfo_is_no_identity(
        self, client, oauth_client, provider
    ):
        token_response = {"access_token": "at", "id_token": "a.b.c"}

        with pytest.raises(core_exceptions.ProcessingError, match="Unable to retrieve user information"):
            client.get_userinfo(
                token_response, None, oauth_client, None, None, "endurain-client", require_id_token=False
            )

    def test_nothing_to_go_on_is_no_identity(self, client, oauth_client, provider):
        provider.userinfo_status = 500

        with pytest.raises(core_exceptions.ProcessingError, match="Unable to retrieve user information"):
            self._get(client, oauth_client, provider, {"access_token": "at"}, require_id_token=False)


class TestEndpoints:
    def test_a_configured_token_endpoint_wins_over_the_discovered_one(self, client, make_idp, provider):
        idp = make_idp(token_endpoint=f"{provider.issuer}/own-token")

        assert client.resolve_token_endpoint(idp) == f"{provider.issuer}/own-token"
        assert provider.requests == []

    def test_a_missing_token_endpoint_is_discovered(self, client, make_idp, provider):
        assert client.resolve_token_endpoint(make_idp()) == provider.token_endpoint

    def test_a_token_endpoint_that_cannot_be_found_is_an_upstream_error(self, client, make_idp, provider):
        provider.discovery = {"token_endpoint": None}

        with pytest.raises(core_exceptions.UpstreamError, match="token endpoint"):
            client.resolve_token_endpoint(make_idp())

    def test_a_discovered_token_endpoint_on_a_private_address_is_refused_unless_allowed(
        self, client, make_idp, provider, monkeypatch
    ):
        idp = make_idp()
        provider.discovery = {"token_endpoint": "http://10.0.0.5/token"}
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.1"])

        with pytest.raises(core_exceptions.InvalidInputError):
            client.resolve_token_endpoint(idp)

    @pytest.mark.parametrize(
        ("resolve", "member"),
        [
            ("resolve_revocation_endpoint", "revocation_endpoint"),
            ("resolve_end_session_endpoint", "end_session_endpoint"),
        ],
    )
    def test_the_advertised_endpoint_is_returned_or_none_when_there_is_none(
        self, resolve, member, client, make_idp, provider
    ):
        idp = make_idp()

        assert getattr(client, resolve)(idp) == provider.discovery_document()[member]
        provider.discovery = {member: None}
        client.forget_discovery(idp.id)
        assert getattr(client, resolve)(idp) is None

    @pytest.mark.parametrize("resolve", ["resolve_revocation_endpoint", "resolve_end_session_endpoint"])
    def test_a_provider_without_an_issuer_advertises_no_endpoint_and_one_whose_document_is_down_is_an_error(
        self, resolve, client, make_idp, provider
    ):
        plain = make_idp("plain", provider_type="oauth2", issuer_url=None, scopes="profile")
        assert getattr(client, resolve)(plain) is None

        provider.discovery_status = 500
        with pytest.raises(core_exceptions.UpstreamError, match="discovery document is unavailable"):
            getattr(client, resolve)(make_idp("other", issuer_url=f"{provider.issuer}/"))

    @pytest.mark.parametrize(
        ("resolve", "member"),
        [
            ("resolve_revocation_endpoint", "revocation_endpoint"),
            ("resolve_end_session_endpoint", "end_session_endpoint"),
        ],
    )
    def test_an_advertised_endpoint_on_a_private_address_is_refused(
        self, resolve, member, client, make_idp, provider, monkeypatch
    ):
        idp = make_idp()
        provider.discovery = {member: "http://10.0.0.5/x"}
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.1"])

        with pytest.raises(core_exceptions.InvalidInputError):
            getattr(client, resolve)(idp)
