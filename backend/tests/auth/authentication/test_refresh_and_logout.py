"""A refresh is refused with one answer and an audit row per cause; a logout is idempotent and ends one session."""

import uuid
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import ClassVar
from urllib.parse import parse_qsl, urlsplit

import httpx2
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.network as core_network
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.token_service as authentication_token_service
import modules.auth.constants as auth_constants
import modules.auth.identity_provider_links.models as identity_links_models
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.rotated_refresh_tokens.models as rotated_models
import modules.auth.sessions.models as sessions_models
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.models as users_models
from tests._factories.identity_links import make_identity_link
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
    LOGOUT,
    MOBILE,
    REFRESH,
    WEB,
    Account,
    exchange,
    login,
    make_account,
    make_sso_session,
    session_count,
)

_COOKIE = authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME
_SESSION_ENDED = "urn:endurain:error:session-ended"


def _web(app, account: Account) -> tuple[TestClient, str, str]:
    """Sign the account in as a web client; return a client that holds its refresh cookie, and the ids."""
    signed_in = login(TestClient(app), account)
    refresh_token = signed_in.cookies[_COOKIE]
    return _bare(app, cookie=refresh_token), signed_in.json()["session_id"], refresh_token


def _bare(app, headers=WEB, *, cookie: str | None = None) -> TestClient:
    """A client with the web origin that holds a refresh cookie and no access token."""
    client = TestClient(app, headers={**headers, "Origin": app.state.cors_allow_origins[0]})
    if cookie is not None:
        client.cookies.set(_COOKIE, cookie)
    return client


def _mobile(app, account: Account) -> tuple[TestClient, dict]:
    client = TestClient(app)
    session_id = login(client, account, MOBILE).json()["session_id"]
    return client, exchange(client, session_id).json()


def _refusals(sessions) -> list[tuple[str, str]]:
    return [(row.outcome, row.details["reason"]) for row in audit_rows(sessions, authentication_audit_actions.REFRESH)]


def _update_session(sessions, session_id, **values) -> None:
    with sessions() as db:
        db.execute(
            sa.update(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.id == uuid.UUID(str(session_id)))
            .values(**values)
        )
        db.commit()


def _deactivate(sessions, account: Account) -> None:
    with sessions() as db:
        db.execute(sa.update(users_models.Users).where(users_models.Users.id == account.user.id).values(active=False))
        db.commit()


def _end_grace_window(sessions, session_id) -> None:
    with sessions() as db:
        db.execute(
            sa.update(rotated_models.RotatedRefreshToken)
            .where(rotated_models.RotatedRefreshToken.token_family_id == uuid.UUID(str(session_id)))
            .values(
                rotated_at=datetime.now(UTC) - timedelta(minutes=1),
                expires_at=datetime.now(UTC) - timedelta(seconds=50),
            )
        )
        db.commit()


class TestRefreshRefusals:
    def test_a_web_refresh_without_the_cookie_is_a_session_ended_401(self, app):
        response = _bare(app).post(REFRESH)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED

    def test_a_web_refresh_from_an_origin_the_server_does_not_allow_is_a_403(self, app, account):
        _, _, refresh_token = _web(app, account)
        client = TestClient(app, headers={**WEB, "Origin": "https://evil.example"})
        client.cookies.set(_COOKIE, refresh_token)

        assert client.post(REFRESH).status_code == 403

    def test_a_session_of_another_user_is_refused_and_audited(self, app, committed_sessions, account):
        _, session_id, refresh_token = _web(app, account)
        other = make_account(committed_sessions)
        _update_session(committed_sessions, session_id, user_id=other.user.id)

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", "session_owner_mismatch")]

    def test_a_session_of_another_client_type_is_refused_and_audited(self, app, committed_sessions, account):
        _, session_id, refresh_token = _web(app, account)
        _update_session(committed_sessions, session_id, client_type="mobile")

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", "client_type_mismatch")]

    def test_a_timed_out_session_is_refused_and_audited(self, app, committed_sessions, account):
        _, session_id, refresh_token = _web(app, account)
        _update_session(committed_sessions, session_id, created_at=datetime.now(UTC) - timedelta(days=31))

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", "session_expired")]

    def test_a_session_whose_tokens_were_not_exchanged_is_refused_and_audited(
        self, app, client, committed_sessions, account
    ):
        session_id = login(client, account, MOBILE).json()["session_id"]
        with committed_sessions() as db:
            policy = server_settings_integration.get_session_policy(db)
        *_, minted = authentication_token_service.create_tokens(
            account.user,
            auth_constants.ClientType.MOBILE,
            access_tokens_integration.get_token_manager(),
            policy,
            uuid.UUID(session_id),
        )

        response = TestClient(app).post(REFRESH, json={"refresh_token": minted}, headers=MOBILE)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", "tokens_not_exchanged")]

    def test_an_inactive_account_is_refused_as_denied(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        _deactivate(committed_sessions, account)

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("denied", "user_inactive")]

    def test_a_replay_with_no_stored_replacement_is_refused_and_audited(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)
        with committed_sessions() as db:
            db.execute(sa.update(rotated_models.RotatedRefreshToken).values(replacement_refresh_token=None))
            db.commit()

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", "replay_unavailable")]

    def test_a_replay_for_an_account_deactivated_since_is_refused_as_denied(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)
        _deactivate(committed_sessions, account)

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("denied", "user_inactive")]

    def test_a_refused_refresh_clears_the_web_refresh_cookie(self, app):
        response = _bare(app, cookie="not-a-token").post(REFRESH)

        assert response.status_code == 401
        assert any(_COOKIE in header for header in response.headers.get_list("set-cookie"))


class TestRotationRecord:
    def test_a_rotation_records_the_presented_tokens_own_expiry(self, app, committed_sessions, account):
        _, session_id, refresh_token = _web(app, account)
        manager = access_tokens_integration.get_token_manager()
        expiry = manager.get_token_claim(refresh_token, "exp", access_tokens_integration.TokenType.REFRESH)

        _bare(app, cookie=refresh_token).post(REFRESH)

        with committed_sessions() as db:
            (row,) = db.scalars(
                sa.select(rotated_models.RotatedRefreshToken).where(
                    rotated_models.RotatedRefreshToken.token_family_id == uuid.UUID(session_id)
                )
            )
        assert row.refresh_token_exp.timestamp() == pytest.approx(int(expiry), abs=1)

    def test_a_refresh_near_the_absolute_timeout_reports_the_sessions_capped_expiry_for_the_body_and_the_cookie(
        self, app, committed_sessions, account
    ):
        _, session_id, refresh_token = _web(app, account)
        _update_session(committed_sessions, session_id, created_at=datetime.now(UTC) - timedelta(hours=718))

        response = _bare(app, cookie=refresh_token).post(REFRESH)

        assert response.status_code == 200
        assert response.json()["refresh_token_expires_in"] == pytest.approx(2 * 3600, abs=60)
        cookie = next(
            h for h in response.headers.get_list("set-cookie") if h.startswith(f"{_COOKIE}=") and '=""' not in h
        )
        expires = next(part.split("=", 1)[1] for part in cookie.split("; ") if part.lower().startswith("expires="))
        remaining = (parsedate_to_datetime(expires) - datetime.now(UTC)).total_seconds()
        assert remaining == pytest.approx(2 * 3600, abs=60)

    def test_an_exchange_near_the_absolute_timeout_tells_the_client_the_sessions_new_expiry(
        self, app, client, committed_sessions, account
    ):
        session_id = login(client, account, MOBILE).json()["session_id"]
        _update_session(committed_sessions, session_id, created_at=datetime.now(UTC) - timedelta(hours=718))

        response = exchange(client, session_id)

        assert response.status_code == 200
        assert response.json()["refresh_token_expires_in"] == pytest.approx(2 * 3600, abs=60)


class TestMobileRefresh:
    def test_the_token_in_the_body_rotates_the_session_and_answers_the_new_token_in_the_body(
        self, app, committed_sessions, account
    ):
        _, tokens = _mobile(app, account)

        response = TestClient(app).post(REFRESH, json={"refresh_token": tokens["refresh_token"]}, headers=MOBILE)

        body = response.json()
        assert response.status_code == 200
        assert body["refresh_token"] != tokens["refresh_token"]
        assert "set-cookie" not in response.headers

    def test_a_web_client_cannot_use_a_token_it_sends_in_the_body(self, app, account):
        _, tokens = _mobile(app, account)

        response = _bare(app).post(REFRESH, json={"refresh_token": tokens["refresh_token"]})

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED

    def test_a_mobile_refresh_without_a_body_is_a_session_ended_401(self, app):
        response = TestClient(app).post(REFRESH, headers=MOBILE)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED


class TestReuseEvent:
    def test_a_reuse_outside_the_grace_window_tells_the_session_owner(
        self, app, committed_sessions, account, published
    ):
        events = published(authentication_events.REFRESH_REUSE_DETECTED)
        _, session_id, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)
        _end_grace_window(committed_sessions, session_id)

        _bare(app, cookie=refresh_token).post(REFRESH)

        assert [e.payload for e in events] == [{"user_id": str(account.user.id)}]

    def test_a_replay_inside_the_grace_window_tells_nobody(self, app, account, published):
        events = published(authentication_events.REFRESH_REUSE_DETECTED)
        _, _, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)

        _bare(app, cookie=refresh_token).post(REFRESH)

        assert events == []


class TestLogout:
    def test_a_web_logout_ends_the_session_clears_the_cookie_and_is_audited(self, app, committed_sessions, account):
        client, _, _ = _web(app, account)

        response = client.post(LOGOUT)

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert response.headers["cache-control"] == "no-store"
        assert any(_COOKIE in header for header in response.headers.get_list("set-cookie"))
        assert session_count(committed_sessions, account.user.id) == 0
        (row,) = audit_rows(committed_sessions, authentication_audit_actions.LOGOUT)
        assert (row.outcome, row.target_id) == ("success", str(account.user.id))
        assert (row.actor_id, row.credential_type) == (str(account.user.id), "refresh_token")

    def test_a_mobile_logout_with_the_token_in_the_body_ends_the_session(self, app, committed_sessions, account):
        _, tokens = _mobile(app, account)

        response = TestClient(app).post(LOGOUT, json={"refresh_token": tokens["refresh_token"]}, headers=MOBILE)

        assert response.status_code == 200
        assert "set-cookie" not in response.headers
        assert session_count(committed_sessions, account.user.id) == 0

    def test_a_logout_ends_only_its_own_session(self, app, committed_sessions, account):
        client, _, _ = _web(app, account)
        _web(app, account)

        client.post(LOGOUT)

        assert session_count(committed_sessions, account.user.id) == 1

    def test_a_logout_without_a_usable_token_ends_nothing_writes_nothing_and_still_answers_200(
        self, app, committed_sessions, account
    ):
        _web(app, account)

        missing = _bare(app).post(LOGOUT)
        malformed = _bare(app, cookie="not-a-token").post(LOGOUT)

        assert (missing.status_code, malformed.status_code) == (200, 200)
        assert missing.json() == malformed.json() == {"idp_logout_url": None}
        assert any(_COOKIE in header for header in malformed.headers.get_list("set-cookie"))
        assert session_count(committed_sessions, account.user.id) == 1
        assert audit_rows(committed_sessions, authentication_audit_actions.LOGOUT) == []

    def test_a_logout_of_an_ended_session_writes_nothing(self, app, committed_sessions, account):
        client, _, _ = _web(app, account)
        client.post(LOGOUT)

        assert client.post(LOGOUT).status_code == 200
        assert len(audit_rows(committed_sessions, authentication_audit_actions.LOGOUT)) == 1

    def test_a_logout_from_an_origin_the_server_does_not_allow_is_a_403(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        client = TestClient(app, headers={**WEB, "Origin": "https://evil.example"})
        client.cookies.set(_COOKIE, refresh_token)

        assert client.post(LOGOUT).status_code == 403
        assert session_count(committed_sessions, account.user.id) == 1

    def test_a_logout_of_a_session_whose_tokens_were_not_exchanged_ends_nothing(
        self, app, client, committed_sessions, account
    ):
        session_id = login(client, account, MOBILE).json()["session_id"]
        with committed_sessions() as db:
            policy = server_settings_integration.get_session_policy(db)
        *_, minted = authentication_token_service.create_tokens(
            account.user,
            auth_constants.ClientType.MOBILE,
            access_tokens_integration.get_token_manager(),
            policy,
            uuid.UUID(session_id),
        )

        response = TestClient(app).post(LOGOUT, json={"refresh_token": minted}, headers=MOBILE)

        assert response.status_code == 200
        assert session_count(committed_sessions, account.user.id) == 1

    def test_a_session_signed_in_without_a_provider_answers_no_provider_url(self, app, account):
        client, _, _ = _web(app, account)

        assert client.post(LOGOUT).json()["idp_logout_url"] is None


def _oidc_provider(sessions) -> uuid.UUID:
    """Store a provider that has an issuer, whose discovery document the tests answer."""
    with sessions() as db:
        idp = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Keycloak",
                slug=f"keycloak-{uuid.uuid4().hex[:8]}",
                issuer_url="https://idp.example.com",
                client_id="endurain",
                client_secret="secret",
                enabled=True,
            ),
            db,
        )
        db.commit()
        return idp.id


def _discovery(monkeypatch, document: dict | Exception) -> None:
    """Answer the provider's discovery request the way the provider would, without a network."""
    monkeypatch.setattr(core_network.socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 0, "", ("8.8.8.8", 0))])

    def get(self, url, *args, **kwargs):
        if isinstance(document, Exception):
            raise document
        return httpx2.Response(200, json=document, request=httpx2.Request("GET", url))

    monkeypatch.setattr(httpx2.Client, "get", get)


class TestLogoutEndsTheProviderSession:
    """The provider and ID token are read before the session ends; the provider's URL is resolved after the commit."""

    _ISSUER: ClassVar[dict[str, str]] = {
        "issuer": "https://idp.example.com",
        "end_session_endpoint": "https://idp.example.com/logout?x=1",
    }

    def _signed_in(self, app, committed_sessions, account, client_type="web", idp_id=None):
        if idp_id is None:
            idp_id = _oidc_provider(committed_sessions)
            with committed_sessions() as db:
                make_identity_link(db, account.user.id, idp_id, "subject-1")
                db.commit()
        session_id = make_sso_session(
            committed_sessions,
            account.user,
            client_type=client_type,
            idp_id=idp_id,
            token_response={"id_token": "the-id-token"},
        )
        headers = WEB if client_type == "web" else MOBILE
        response = exchange(TestClient(app), session_id, headers=headers)
        return response.cookies.get(_COOKIE), response.json().get("refresh_token"), session_id

    def test_a_web_session_gets_the_providers_end_session_url_with_the_login_page_to_return_to(
        self, app, committed_sessions, account, monkeypatch
    ):
        refresh_token, _, _ = self._signed_in(app, committed_sessions, account)
        _discovery(monkeypatch, self._ISSUER)

        response = _bare(app, cookie=refresh_token).post(LOGOUT)

        url = urlsplit(response.json()["idp_logout_url"])
        assert (url.scheme, url.netloc, url.path) == ("https", "idp.example.com", "/logout")
        query = dict(parse_qsl(url.query))
        assert query["x"] == "1"
        assert query["id_token_hint"] == "the-id-token"
        assert query["client_id"] == "endurain"
        assert query["post_logout_redirect_uri"].endswith("/login")
        assert session_count(committed_sessions, account.user.id) == 0

    def test_a_mobile_client_gets_no_return_address(self, app, committed_sessions, account, monkeypatch):
        _, refresh_token, _ = self._signed_in(app, committed_sessions, account, "mobile")
        _discovery(monkeypatch, self._ISSUER)

        response = TestClient(app).post(LOGOUT, json={"refresh_token": refresh_token}, headers=MOBILE)

        query = dict(parse_qsl(urlsplit(response.json()["idp_logout_url"]).query))
        assert "post_logout_redirect_uri" not in query
        assert query["id_token_hint"] == "the-id-token"

    def test_a_provider_without_an_endpoint_leaves_the_url_null(self, app, committed_sessions, account, monkeypatch):
        refresh_token, _, _ = self._signed_in(app, committed_sessions, account)
        _discovery(monkeypatch, {"issuer": "https://idp.example.com"})

        response = _bare(app, cookie=refresh_token).post(LOGOUT)

        assert response.json() == {"idp_logout_url": None}
        assert session_count(committed_sessions, account.user.id) == 0

    def test_a_provider_that_cannot_be_reached_still_ends_the_session_and_leaves_the_url_null(
        self, app, committed_sessions, account, monkeypatch
    ):
        refresh_token, _, _ = self._signed_in(app, committed_sessions, account)
        _discovery(monkeypatch, httpx2.ConnectError("down"))

        response = _bare(app, cookie=refresh_token).post(LOGOUT)

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert session_count(committed_sessions, account.user.id) == 0

    def test_a_logout_leaves_the_provider_sign_in_of_the_users_other_session_alone(
        self, app, committed_sessions, account, monkeypatch
    ):
        idp_id = _oidc_provider(committed_sessions)
        with committed_sessions() as db:
            make_identity_link(db, account.user.id, idp_id, "subject-1")
            db.commit()
        refresh_token, _, ended = self._signed_in(app, committed_sessions, account, idp_id=idp_id)
        _, _, other = self._signed_in(app, committed_sessions, account, idp_id=idp_id)
        _discovery(monkeypatch, self._ISSUER)

        _bare(app, cookie=refresh_token).post(LOGOUT)

        with committed_sessions() as db:
            kept = set(db.scalars(sa.select(identity_links_models.IdpSessionToken.session_id)))
        assert session_count(committed_sessions, account.user.id) == 1
        assert other in kept
        # The provider sign-in of the ended session stays, so that its token can still be revoked at the provider.
        assert ended in kept


class TestLogoutOfARotatedToken:
    def test_a_rotated_token_used_outside_its_grace_window_ends_the_whole_family(
        self, app, committed_sessions, account
    ):
        _, session_id, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)
        _end_grace_window(committed_sessions, session_id)

        response = _bare(app, cookie=refresh_token).post(LOGOUT)

        assert response.status_code == 200
        assert session_count(committed_sessions, account.user.id) == 0
        (row,) = audit_rows(committed_sessions, authentication_audit_actions.REFRESH_TOKEN_REUSE)
        assert (row.outcome, row.target_id) == ("denied", str(account.user.id))

    def test_a_retry_in_the_grace_window_from_the_rotating_client_ends_nothing(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        _bare(app, cookie=refresh_token).post(REFRESH)

        response = _bare(app, cookie=refresh_token).post(LOGOUT)

        assert response.status_code == 200
        assert session_count(committed_sessions, account.user.id) == 1

    def test_the_current_token_ends_its_session_without_a_reuse_check(self, app, committed_sessions, account):
        _, _, refresh_token = _web(app, account)
        current = _bare(app, cookie=refresh_token).post(REFRESH).cookies[_COOKIE]

        _bare(app, cookie=current).post(LOGOUT)

        assert session_count(committed_sessions, account.user.id) == 0
        assert audit_rows(committed_sessions, authentication_audit_actions.REFRESH_TOKEN_REUSE) == []
