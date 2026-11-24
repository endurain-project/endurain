"""A provider on the loopback interface and a browser that signs in through it, for the SSO tests."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

import core.config as core_config
import modules.auth.identity_providers.dependencies as idp_dependencies
from modules.auth.constants import ClientType
from tests.auth.identity_providers.fake_provider import FakeProvider, pkce_challenge

API = core_config.ROOT_PATH
VERIFIER = "v" * 43


@pytest.fixture
def provider(monkeypatch) -> Iterator[FakeProvider]:
    """A loopback identity provider the outbound-network policy allows."""
    fake = FakeProvider()
    monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.0/8"])
    yield fake
    fake.stop()


@pytest.fixture
def make_provider(committed_sessions, provider) -> Callable[..., uuid.UUID]:
    """Return a function that commits an enabled OIDC provider pointed at :func:`provider`; it returns the id."""
    from tests._factories.identity_links import make_oidc_provider

    def make(slug: str | None = None, **fields: Any) -> uuid.UUID:
        with committed_sessions() as db:
            issuer = fields.pop("issuer_url", provider.issuer)
            idp_id = make_oidc_provider(db, slug or f"idp-{uuid.uuid4().hex[:8]}", issuer, **fields)
            db.commit()
        return idp_id

    return make


@dataclass
class Started:
    """A login, link or step-up the browser started at the application, before the provider answered.

    Attributes:
        authorization_url: Where the application sent the browser.
        state: The state in it.
        nonce: The nonce in it.
        binding: The binding cookie value the browser holds.
        verifier: The PKCE verifier the client keeps.
    """

    authorization_url: str
    state: str
    nonce: str
    binding: str | None
    verifier: str


@dataclass
class Finished:
    """The answer to a provider callback.

    Attributes:
        response: The HTTP response.
        location: Where it redirected.
        query: The query of the location.
        fragment: The fragment of the location.
    """

    response: Response
    location: str
    query: dict[str, str]
    fragment: dict[str, str]

    @property
    def session_id(self) -> uuid.UUID:
        """The session a successful login handed to the token exchange."""
        return uuid.UUID(self.query["session_id"])


class Browser:
    """A browser (the anonymous client, without redirects) that goes through the SSO flow with a provider."""

    def __init__(self, client: TestClient, provider: FakeProvider) -> None:
        self.client = client
        self.provider = provider

    def start_login(self, slug: str, *, redirect: str | None = None, verifier: str = VERIFIER) -> Started:
        """Start a login at the application and return what the provider is sent."""
        params = {"code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"}
        if redirect is not None:
            params["redirect"] = redirect
        response = self.client.get(f"{API}/public/idp/login/{slug}", params=params, follow_redirects=False)
        assert response.status_code == 307, response.text
        return self.started(response, verifier)

    def started(self, response: Response, verifier: str = VERIFIER) -> Started:
        """Read the authorization request of a redirect to the provider, or of a start that answers it as JSON."""
        url = response.headers["location"] if "location" in response.headers else response.json()["authorization_url"]
        query = dict(parse_qsl(urlsplit(url).query))
        return Started(
            url,
            query.get("state", ""),
            query.get("nonce", ""),
            response.cookies.get(idp_dependencies.BINDING_COOKIE_NAME),
            verifier,
        )

    def callback(
        self,
        slug: str,
        *,
        state: str,
        code: str | None = None,
        error: str | None = None,
        binding: str | None = None,
        iss: str | None = None,
    ) -> Finished:
        """Call the application's callback as the browser the provider redirected."""
        params = {"state": state}
        if code is not None:
            params["code"] = code
        if error is not None:
            params["error"] = error
        if iss is not None:
            params["iss"] = iss
        headers = {}
        if binding is not None:
            headers["Cookie"] = f"{idp_dependencies.BINDING_COOKIE_NAME}={binding}"
        response = self.client.get(
            f"{API}/public/idp/callback/{slug}", params=params, headers=headers, follow_redirects=False
        )
        return self.finished(response)

    @staticmethod
    def finished(response: Response) -> Finished:
        """Read a callback's redirect."""
        location = response.headers.get("location", "")
        split = urlsplit(location)
        query = {key: values[0] for key, values in parse_qs(split.query).items()}
        fragment = {key: values[0] for key, values in parse_qs(split.fragment).items()}
        return Finished(response, location, query, fragment)

    def finish(self, slug: str, started: Started, *, with_iss: bool = False, **claims: Any) -> Finished:
        """Sign the user in at the provider and call the callback with what it hands back."""
        code, state = self.provider.authorize(started.authorization_url, **claims)
        return self.callback(
            slug, state=state, code=code, binding=started.binding, iss=self.provider.issuer if with_iss else None
        )

    def sign_in(self, slug: str, *, redirect: str | None = None, **claims: Any) -> tuple[Started, Finished]:
        """Run a whole login up to the token exchange."""
        started = self.start_login(slug, redirect=redirect)
        return started, self.finish(slug, started, **claims)

    def exchange(
        self, session_id: uuid.UUID, verifier: str = VERIFIER, client_type: ClientType = ClientType.WEB
    ) -> Response:
        """Exchange a login's session for its tokens."""
        return self.client.post(
            f"{API}/auth/sessions/{session_id}/tokens",
            json={"code_verifier": verifier},
            headers={"X-Client-Type": client_type.value},
        )


@pytest.fixture
def browser(client, provider) -> Browser:
    """The anonymous browser, with the provider it signs in at."""
    return Browser(client, provider)


@pytest.fixture
def sso_sign_up(committed_sessions) -> None:
    """Let the server create accounts through single sign-on."""
    from tests._factories.server_settings import edit_server_settings

    with committed_sessions() as db:
        edit_server_settings(db, signup_sso_enabled=True)
        db.commit()


@pytest.fixture
def other_provider(provider) -> Iterator[FakeProvider]:
    """A second loopback identity provider, with its own issuer, next to :func:`provider`."""
    fake = FakeProvider()
    yield fake
    fake.stop()


@dataclass
class LinkStart:
    """A link the signed-in user started at the application.

    Attributes:
        response: The start response.
        started: The authorization request, when the start succeeded.
    """

    response: Response
    started: Started | None


class LinkBrowser(Browser):
    """The browser of a signed-in user, who links a provider from their settings."""

    def __init__(self, browser: Browser, signed_in) -> None:
        super().__init__(browser.client, browser.provider)
        self.signed_in = signed_in

    def start_link(
        self, idp_id: uuid.UUID, *, redirect: str | None = None, revoke_other_sessions: bool = True, **step_up: Any
    ) -> LinkStart:
        """Start linking a provider; the step-up is the user's password unless ``step_up`` replaces it."""
        from tests._factories.users import PASSWORD

        body: dict[str, Any] = {
            "revoke_other_sessions": revoke_other_sessions,
            "step_up": step_up or {"current_password": PASSWORD},
        }
        if redirect is not None:
            body["redirect"] = redirect
        response = self.signed_in.client.post(f"{API}/profile/identity-providers/{idp_id}/link", json=body)
        if response.status_code != 200:
            return LinkStart(response, None)
        return LinkStart(response, self.started(response))


@pytest.fixture
def link_browser(browser, committed_sessions, sign_in) -> Callable[..., LinkBrowser]:
    """Return a function that signs a committed user in and gives their browser."""

    def make(user) -> LinkBrowser:
        return LinkBrowser(browser, sign_in(user))

    return make


class PasswordlessUser:
    """An account created by single sign-on, signed in with the tokens of its exchange.

    Attributes:
        browser: The browser it signed in with.
        slug: The provider's slug.
        idp_id: The provider's id.
        tokens: The exchange's response body.
    """

    def __init__(
        self, browser: Browser, slug: str, idp_id: uuid.UUID, tokens: dict[str, Any], refresh_cookie: str | None
    ) -> None:
        self.browser = browser
        self.slug = slug
        self.idp_id = idp_id
        self.tokens = tokens
        self.refresh_cookie = refresh_cookie

    @property
    def headers(self) -> dict[str, str]:
        """The headers of an authenticated web request."""
        return {"Authorization": f"Bearer {self.tokens['access_token']}", "X-Client-Type": "web"}

    def post(self, path: str, body: dict[str, Any]) -> Response:
        """POST as the account."""
        return self.browser.client.post(f"{API}{path}", json=body, headers=self.headers)

    def get(self, path: str) -> Response:
        """GET as the account."""
        return self.browser.client.get(f"{API}{path}", headers=self.headers)


@pytest.fixture
def sso_account(browser, make_provider, sso_sign_up) -> PasswordlessUser:
    """An account the provider created and signed in, which has no local password."""
    idp_id = make_provider("acme")
    browser.provider.claims = {"email": "sso-user@example.com", "email_verified": True}
    _, finished = browser.sign_in("acme")
    exchanged = browser.exchange(finished.session_id)
    import modules.auth.authentication.dependencies as authentication_dependencies

    return PasswordlessUser(
        browser,
        "acme",
        idp_id,
        exchanged.json(),
        exchanged.cookies.get(authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME),
    )


class FailingTables:
    """Statements on tables made to fail in PostgreSQL by a trigger that raises, so the application meets a database
    error it did not cause."""

    def __init__(self, sessions) -> None:
        self._sessions = sessions
        self._active: set[tuple[str, str]] = set()

    @staticmethod
    def _name(table: str, operation: str) -> str:
        return f"fail_{operation.lower()}_{table}"

    def fail(self, table: str, operation: str) -> None:
        """Make every ``INSERT``, ``UPDATE`` or ``DELETE`` on the table fail."""
        from sqlalchemy import text

        name = self._name(table, operation)
        with self._sessions() as db:
            db.execute(
                text(
                    f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RAISE EXCEPTION 'injected failure'; END $$"
                )
            )
            db.execute(
                text(f"CREATE TRIGGER {name} BEFORE {operation} ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()")
            )
            db.commit()
        self._active.add((table, operation))

    def heal(self, table: str, operation: str) -> None:
        """Let the statements on the table succeed again."""
        from sqlalchemy import text

        name = self._name(table, operation)
        with self._sessions() as db:
            db.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {table}"))
            db.execute(text(f"DROP FUNCTION IF EXISTS {name}()"))
            db.commit()
        self._active.discard((table, operation))


@pytest.fixture
def failing_table(committed_sessions) -> Iterator[FailingTables]:
    """Tables a test makes fail; they are healed when the test ends."""
    tables = FailingTables(committed_sessions)
    yield tables
    for table, operation in list(tables._active):
        tables.heal(table, operation)
