"""An OpenID Connect provider on the loopback interface: the third party every SSO test talks to over real HTTP.

The provider publishes a discovery document and signing keys, redeems authorization codes at a token endpoint that
checks the client's credentials and the PKCE verifier, answers userinfo, revokes tokens, and signs ID tokens and
logout tokens with a test RSA key. Our application reaches it through its real HTTP client, address guard and
discovery cache; nothing of ours is replaced.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlsplit

from joserfc import jwt
from joserfc.jwk import RSAKey

CLIENT_ID = "endurain-client"
CLIENT_SECRET = "endurain-secret"
KEY_ID = "test-key-1"

_SIGNING_KEY: RSAKey | None = None
_SIGNING_KEY_LOCK = threading.Lock()


def signing_key() -> RSAKey:
    """Return the process-wide RSA key the providers sign with, generated on first use."""
    global _SIGNING_KEY
    with _SIGNING_KEY_LOCK:
        if _SIGNING_KEY is None:
            _SIGNING_KEY = RSAKey.generate_key(2048, parameters={"kid": KEY_ID, "use": "sig"})
        return _SIGNING_KEY


def pkce_challenge(verifier: str) -> str:
    """Return the S256 challenge of a PKCE verifier."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class FakeProvider:
    """A real HTTP identity provider whose answers a test steers.

    Attributes:
        sub: The subject the next sign-in is for.
        claims: Further claims of the next sign-in's ID token and userinfo (``email``, ``name``, ...).
        id_token_claims: Claims only the ID token carries, over ``claims``.
        auth_time_age: Seconds ago the user signed in at the provider, as the ID token's ``auth_time`` says.
        discovery_status: The status the discovery endpoint answers.
        discovery_raw: A body that replaces the discovery document.
        jwks_raw: A body that replaces the JWKS document.
        delays: Seconds each path waits before it answers, by path.
        discovery: Members that replace or extend the discovery document; a ``None`` value removes the member.
        jwks_keys: The ``keys`` the JWKS endpoint serves; the signing key's public part when ``None``.
        token_status: The status the token endpoint answers; 200 redeems the code.
        token_body: A body that replaces the token response, as a dict (JSON) or ``bytes``.
        expires_in: The ``expires_in`` of every token response.
        issue_id_token: Whether the token response carries an ID token.
        id_token_override: A string that replaces the ID token.
        userinfo_status: The status the userinfo endpoint answers.
        revoke_status: The status the revocation endpoint answers.
        refresh_status: The status the token endpoint answers a refresh-token grant.
        refresh_error: The OAuth error code of a refresh answered with an error status.
        refresh_issues_refresh_token: Whether a refresh response carries a new refresh token.
        refresh_raw_id_token: A value the refresh response carries as its ``id_token``, as it is.
        requests: ``(method, path, form-or-query, headers)`` of every request, in arrival order.
        revoked: The tokens the revocation endpoint was asked to revoke.
    """

    def __init__(self) -> None:
        self.sub = "provider-subject-1"
        self.claims: dict[str, Any] = {}
        self.id_token_claims: dict[str, Any] = {}
        self.auth_time_age = 0
        self.discovery: dict[str, Any] = {}
        self.discovery_status = 200
        self.discovery_raw: bytes | None = None
        self.jwks_raw: dict[str, Any] | bytes | None = None
        self.delays: dict[str, float] = {}
        self.jwks_keys: list[dict[str, Any]] | None = None
        self.token_status = 200
        self.token_body: dict[str, Any] | bytes | None = None
        self.issue_id_token = True
        self.expires_in: int | str = 3600
        self.id_token_override: str | None = None
        self.userinfo_status = 200
        self.userinfo_body: dict[str, Any] | bytes | None = None
        self.revoke_status = 200
        self.refresh_status = 200
        self.refresh_error = "invalid_grant"
        self.refresh_raw_id_token: object = None
        self.refresh_issues_refresh_token = True
        self.refresh_id_token_claims: dict[str, Any] | None = None
        self.on_token_request: Callable[[], None] | None = None
        self.requests: list[tuple[str, str, dict[str, str], dict[str, str]]] = []
        self.revoked: list[str] = []
        self._grants: dict[str, dict[str, Any]] = {}
        self._access_tokens: dict[str, dict[str, Any]] = {}
        self._refresh_tokens: dict[str, dict[str, Any]] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer._handle(self, "GET")

            def do_POST(self) -> None:
                outer._handle(self, "POST")

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.issuer = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut the server down."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def authorization_endpoint(self) -> str:
        """The provider's authorization endpoint."""
        return f"{self.issuer}/authorize"

    @property
    def token_endpoint(self) -> str:
        """The provider's token endpoint."""
        return f"{self.issuer}/token"

    @property
    def userinfo_endpoint(self) -> str:
        """The provider's userinfo endpoint."""
        return f"{self.issuer}/userinfo"

    @property
    def jwks_uri(self) -> str:
        """The provider's JWKS endpoint."""
        return f"{self.issuer}/jwks"

    def requests_to(self, path: str) -> list[tuple[str, str, dict[str, str], dict[str, str]]]:
        """Return the requests the provider received at a path."""
        return [request for request in self.requests if request[1] == path]

    def discovery_document(self) -> dict[str, Any]:
        """Return the discovery document the provider serves now."""
        document: dict[str, Any] = {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
            "revocation_endpoint": f"{self.issuer}/revoke",
            "end_session_endpoint": f"{self.issuer}/logout",
            "id_token_signing_alg_values_supported": ["RS256"],
        }
        for key, value in self.discovery.items():
            if value is None:
                document.pop(key, None)
            else:
                document[key] = value
        return document

    def sign(self, claims: dict[str, Any], *, header: dict[str, Any] | None = None, key: RSAKey | None = None) -> str:
        """Sign a JWT with the provider's key (or another one)."""
        return jwt.encode({"alg": "RS256", "kid": KEY_ID, **(header or {})}, claims, key or signing_key())

    def id_token_claims_for(
        self, *, client_id: str, nonce: str | None, access_token: str | None, subject: str | None = None
    ) -> dict[str, Any]:
        """Return the claims of an ID token this provider issues now."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": client_id,
            "sub": self.sub if subject is None else subject,
            "iat": now,
            "exp": now + 300,
            "auth_time": now - self.auth_time_age,
            **self.claims,
            **self.id_token_claims,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        if access_token is not None:
            digest = hashlib.sha256(access_token.encode()).digest()
            claims["at_hash"] = base64.urlsafe_b64encode(digest[: len(digest) // 2]).decode().rstrip("=")
        return claims

    def authorize(self, authorization_url: str, *, client_id: str = CLIENT_ID, **claims: Any) -> tuple[str, str]:
        """Sign the user in at the provider for an authorization request and return its code and state.

        Args:
            authorization_url: The URL our application sent the browser to.
            client_id: The client id the request must name.
            **claims: Claims that replace :attr:`claims` for this sign-in; ``sub`` names the subject.

        Returns:
            The authorization code and the state to hand back to the application's callback.
        """
        query = dict(parse_qsl(urlsplit(authorization_url).query))
        assert query["client_id"] == client_id, query
        assert query["response_type"] == "code"
        code = secrets.token_urlsafe(16)
        self._grants[code] = {
            "nonce": query.get("nonce"),
            "challenge": query.get("code_challenge"),
            "challenge_method": query.get("code_challenge_method"),
            "scope": query.get("scope", ""),
            "redirect_uri": query["redirect_uri"],
            "claims": claims,
            "query": query,
        }
        return code, query["state"]

    def logout_token(self, **overrides: Any) -> str:
        """Return a signed back-channel logout token for the current subject, with claims replaced by ``overrides``.

        A claim whose override is ``None`` is left out.
        """
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 120,
            "jti": uuid.uuid4().hex,
            "sub": self.sub,
            "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
        }
        claims.update(overrides)
        return self.sign({key: value for key, value in claims.items() if value is not None})

    def _handle(self, request: BaseHTTPRequestHandler, method: str) -> None:
        split = urlsplit(request.path)
        form: dict[str, str] = {k: v[0] for k, v in parse_qs(split.query).items()}
        if method == "POST":
            length = int(request.headers.get("Content-Length") or 0)
            form.update({k: v[0] for k, v in parse_qs(request.rfile.read(length).decode()).items()})
        headers = {key.lower(): value for key, value in request.headers.items()}
        self.requests.append((method, split.path, form, headers))
        status, body, extra = self._route(split.path, form, headers)
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        request.send_response(status)
        request.send_header("Content-Type", "application/json")
        request.send_header("Content-Length", str(len(payload)))
        for name, value in extra.items():
            request.send_header(name, value)
        request.end_headers()
        request.wfile.write(payload)

    def _route(
        self, path: str, form: dict[str, str], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any] | bytes, dict[str, str]]:
        if path in self.delays:
            # Latency of the provider, so a client that gives up waiting is seen to; not a wait for time to pass.
            threading.Event().wait(self.delays[path])
        if path == "/.well-known/openid-configuration":
            if self.discovery_status != 200:
                return self.discovery_status, {"error": "server_error"}, {}
            return 200, self.discovery_raw if self.discovery_raw is not None else self.discovery_document(), {}
        if path == "/jwks":
            if self.jwks_raw is not None:
                return 200, self.jwks_raw, {}
            keys = self.jwks_keys if self.jwks_keys is not None else [signing_key().as_dict(private=False)]
            return 200, {"keys": keys}, {}
        if path == "/token":
            return self._token(form, headers)
        if path == "/userinfo":
            return self._userinfo(headers)
        if path == "/revoke":
            self.revoked.append(form.get("token", ""))
            return self.revoke_status, {}, {}
        return 404, {"error": "not_found"}, {}

    def _client_authenticated(self, headers: dict[str, str]) -> bool:
        expected = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        return headers.get("authorization") == f"Basic {expected}"

    def _token(
        self, form: dict[str, str], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any] | bytes, dict[str, str]]:
        if self.on_token_request is not None:
            self.on_token_request()
        if not self._client_authenticated(headers):
            return 401, {"error": "invalid_client"}, {}
        if form.get("grant_type") == "refresh_token":
            return self._refresh(form)
        if self.token_status != 200:
            return self.token_status, {"error": "server_error"}, {}
        grant = self._grants.pop(form.get("code", ""), None)
        if grant is None:
            return 400, {"error": "invalid_grant"}, {}
        if grant["redirect_uri"] != form.get("redirect_uri"):
            return 400, {"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, {}
        if grant["challenge"] and pkce_challenge(form.get("code_verifier", "")) != grant["challenge"]:
            return 400, {"error": "invalid_grant", "error_description": "PKCE verification failed"}, {}
        if self.token_body is not None:
            return 200, self.token_body, {}
        access_token = f"at-{secrets.token_urlsafe(12)}"
        refresh_token = f"rt-{secrets.token_urlsafe(12)}"
        claims_override = grant["claims"]
        self._access_tokens[access_token] = {"sub": self.sub, **self.claims, **claims_override}
        self._refresh_tokens[refresh_token] = {"nonce": grant["nonce"], "claims": claims_override}
        response: dict[str, Any] = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "refresh_token": refresh_token,
            "scope": grant["scope"],
        }
        if self.issue_id_token and "openid" in grant["scope"].split():
            saved = self.claims
            self.claims = {**self.claims, **claims_override}
            try:
                subject = claims_override.get("sub")
                id_claims = self.id_token_claims_for(
                    client_id=CLIENT_ID, nonce=grant["nonce"], access_token=access_token, subject=subject
                )
            finally:
                self.claims = saved
            self._access_tokens[access_token] = {k: v for k, v in id_claims.items() if k not in _ID_ONLY}
            response["id_token"] = self.id_token_override or self.sign(id_claims)
        return 200, response, {}

    def _refresh(self, form: dict[str, str]) -> tuple[int, dict[str, Any] | bytes, dict[str, str]]:
        if self.refresh_status != 200:
            return self.refresh_status, {"error": self.refresh_error}, {}
        record = self._refresh_tokens.get(form.get("refresh_token", ""))
        if record is None:
            return 400, {"error": "invalid_grant"}, {}
        access_token = f"at-{secrets.token_urlsafe(12)}"
        refresh_token = f"rt-{secrets.token_urlsafe(12)}"
        self._refresh_tokens[refresh_token] = record
        response: dict[str, Any] = {"access_token": access_token, "token_type": "Bearer", "expires_in": self.expires_in}
        if self.refresh_issues_refresh_token:
            response["refresh_token"] = refresh_token
        if self.refresh_raw_id_token is not None:
            response["id_token"] = self.refresh_raw_id_token
        elif self.refresh_id_token_claims is not None:
            claims = self.id_token_claims_for(client_id=CLIENT_ID, nonce=None, access_token=access_token)
            claims.update(self.refresh_id_token_claims)
            response["id_token"] = self.sign({k: v for k, v in claims.items() if v is not None})
        return 200, response, {}

    def _userinfo(self, headers: dict[str, str]) -> tuple[int, dict[str, Any] | bytes, dict[str, str]]:
        if self.userinfo_status != 200:
            return self.userinfo_status, {"error": "server_error"}, {}
        if self.userinfo_body is not None:
            return 200, self.userinfo_body, {}
        token = headers.get("authorization", "").removeprefix("Bearer ")
        claims = self._access_tokens.get(token)
        if claims is None:
            return 401, {"error": "invalid_token"}, {}
        return 200, claims, {}


#: Claims only an ID token carries; userinfo leaves them out.
_ID_ONLY = {"iss", "aud", "iat", "exp", "auth_time", "nonce", "at_hash", "sid"}
