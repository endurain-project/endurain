"""Who may call which route: every route of the real application is checked against what it declares.

The routes are read from the router the application mounts (``api.router``), never from a list written here, and the
scopes each declares are read from its dependency tree. ``TestTheMatrixCoversTheApplication`` proves the table is the
built application's, and that a route that is neither scope-checked nor registered as open fails.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, cast

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute, iter_route_contexts
from jasil.audit.models import AuditLog
from sqlalchemy.orm import sessionmaker

import api as application_api
import core.config as core_config
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.constants as auth_constants
import modules.auth.dependencies as auth_dependencies
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
from tests._factories.api_keys import KeyHolder, key_client, make_api_key
from tests._factories.auth import SignedIn
from tests._factories.users import make_admin, make_user

PERMISSION_DENIED = "urn:endurain:error:permission-denied"
INVALID_TOKEN = "urn:endurain:error:invalid-token"
UNAUTHORIZED = "urn:endurain:error:unauthorized"

#: Every scope an API key may hold.
_KEY_SCOPES = frozenset(scope.value for scope in api_keys_constants.ApiKeyScope)

#: Scopes only an administrator holds.
_ADMIN_ONLY_SCOPES = frozenset(auth_constants.ADMIN_ACCESS_SCOPE) - frozenset(auth_constants.REGULAR_ACCESS_SCOPE)

#: A well-formed id for a path parameter nothing exists under.
_UNKNOWN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

#: Routes a caller reaches without credentials, each with what guards it instead.
_UNAUTHENTICATED_ROUTES = {
    "GET /api/v1/activities/{activity_id}/thumbnail": "signed ?t= token in the URL",
    "GET /api/v1/activities/{activity_id}/media/{media_id}/file": "signed ?t= token in the URL",
    "GET /api/v1/users/{user_id}/photo": "signed ?t= token in the URL",
    "POST /api/v1/auth/login": "the sign-in itself: credentials are in the body",
    "POST /api/v1/auth/mfa/verify": "completes a sign-in: the pending-MFA proof is in the body",
    "POST /api/v1/auth/refresh": "refresh token cookie",
    "POST /api/v1/auth/logout": "refresh token cookie",
    "POST /api/v1/auth/password-change": "forced password change: credentials are in the body",
    "POST /api/v1/auth/sessions/{session_id}/tokens": "token exchange of a session just created by an SSO callback",
    "POST /api/v1/public/password-reset/request": "anonymous by design: starts a reset by email",
    "POST /api/v1/public/password-reset/confirm": "emailed reset token in the body",
    "POST /api/v1/public/password-reset/validate": "emailed reset token in the body",
    "POST /api/v1/public/sign-up/request": "anonymous by design: self-service sign-up",
    "POST /api/v1/public/sign-up/confirm": "emailed sign-up token in the body",
    "POST /api/v1/public/sign-up/resend": "anonymous by design: resends the sign-up email",
    "POST /api/v1/public/email-change/confirm": "emailed token in the body",
    "POST /api/v1/public/email-change/cancel": "emailed token in the body",
    "GET /api/v1/public/activities/{activity_id}": "readable only when the activity is shared publicly",
    "GET /api/v1/public/activities/{activity_id}/detail": "readable only when the activity is shared publicly",
    "GET /api/v1/public/activities/exercise-titles": "readable only for activities shared publicly",
    "GET /api/v1/public/activities/{activity_id}/laps": "readable only when the activity is shared publicly",
    "GET /api/v1/public/activities/{activity_id}/sets": "readable only when the activity is shared publicly",
    "GET /api/v1/public/activities/{activity_id}/streams": "readable only when the activity is shared publicly",
    "GET /api/v1/public/activities/{activity_id}/streams/{stream_type}": "readable only when shared publicly",
    "GET /api/v1/public/activities/{activity_id}/workout-steps": "readable only when the activity is shared publicly",
    "GET /api/v1/public/idp": "lists the providers a sign-in page offers",
    "GET /api/v1/public/idp/login/{idp_slug}": "starts an SSO sign-in",
    "GET /api/v1/public/idp/link": "completes a link: the signed state is in the query",
    "GET /api/v1/public/idp/callback/{idp_slug}": "SSO callback: the signed state is in the query",
    "GET /api/v1/public/idp/{idp_slug}/icon": "provider icon shown on the sign-in page",
    "POST /api/v1/public/idp/{idp_slug}/backchannel-logout": "provider call: its signed logout token is the proof",
    "GET /api/v1/public/onboarding": "first-run setup status",
    "POST /api/v1/public/onboarding": "first-run setup, refused once an account exists",
    "GET /api/v1/public/server-settings": "settings the sign-in page needs",
    "GET /api/v1/public/server-settings/tile-maps-templates": "catalogue of map tile templates",
    "GET /api/v1/public/server-settings/login-photo": "branding shown on the sign-in page",
    "GET /api/v1/about": "server version and identity",
    "GET /api/v1/health": "liveness probe",
}

#: WebSocket routes, which authenticate by a one-time ticket in the first message rather than by a header.
_WEBSOCKET_ROUTES = {"/api/v1/ws": "one-time ticket issued by POST /api/v1/ws/ticket"}

#: Routes that authenticate but declare ``scopes=[]``: any signed-in caller or key may use them.
_ROUTES_WITHOUT_SCOPE = {
    "GET /api/v1/sync": "reads only the caller's own changes, whatever scopes the credential holds; each record kind "
    "is filtered by the scope of its kind inside the handler",
    "GET /api/v1/jobs": "lists only the caller's own jobs",
    "GET /api/v1/jobs/{job_id}": "a job is readable only by its owner",
}

_PATH_PARAMETER = re.compile(r"\{(\w+)(?::\w+)?\}")


@dataclass(frozen=True)
class RouteInfo:
    """What a route declares, read from its dependency tree.

    Attributes:
        method: The HTTP method.
        path: The path template, with the API root.
        scopes: Every scope the route's scope checks require.
        has_scope_check: Whether the route runs the scope check at all.
        authenticated: Whether the route resolves the caller's credential.
        session_only: Whether the route needs a signed-in session, which an API key is not.
        path_types: The type of each path parameter, as the route's handlers declare it.
    """

    method: str
    path: str
    scopes: frozenset[str]
    has_scope_check: bool
    authenticated: bool
    session_only: bool
    path_types: dict[str, Any]

    @property
    def key(self) -> str:
        """The route's identity, ``METHOD /path``."""
        return f"{self.method} {self.path}"

    @property
    def admin_scopes(self) -> frozenset[str]:
        """The scopes of the route only an administrator holds."""
        return self.scopes & _ADMIN_ONLY_SCOPES

    @property
    def key_can_hold_scopes(self) -> bool:
        """Whether an API key may hold every scope the route requires."""
        return self.scopes <= _KEY_SCOPES

    def url(self) -> str:
        """Return the path with every parameter filled by a well-formed value of its declared type."""
        return _PATH_PARAMETER.sub(lambda match: str(_sample(self.path_types.get(match.group(1)))), self.path)


def _sample(annotation: Any) -> Any:
    """Return a well-formed value for a path parameter of the given type."""
    if isinstance(annotation, type) and issubclass(annotation, uuid.UUID):
        return _UNKNOWN_ID
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation)).value
    if annotation is int:
        return 1
    return "slug"


def _read_tree(dependant: Dependant, info: dict[str, Any]) -> None:
    """Collect what a dependency tree declares: scope checks, the credential and session dependencies, path types."""
    for field in dependant.path_params:
        info["path_types"][field.name] = field.field_info.annotation
    for child in dependant.dependencies:
        if child.call is auth_dependencies.check_scopes:
            info["has_scope_check"] = True
            info["scopes"].update(child.own_oauth_scopes or ())
        if child.call is auth_dependencies.get_principal:
            info["authenticated"] = True
        if child.call is auth_dependencies.get_sid_from_access_token:
            info["session_only"] = True
        _read_tree(child, info)


def _routes_of(routes: list[Any]) -> tuple[list[RouteInfo], list[str]]:
    """Return the HTTP routes under the API root and the paths of its other routes (WebSockets)."""
    http: list[RouteInfo] = []
    other: list[str] = []
    for context in iter_route_contexts(routes):
        path = context.path or ""
        if not path.startswith(core_config.ROOT_PATH):
            continue
        if not isinstance(context.original_route, APIRoute):
            other.append(path)
            continue
        info: dict[str, Any] = {"scopes": set(), "has_scope_check": False, "authenticated": False}
        info |= {"session_only": False, "path_types": {}}
        _read_tree(context.dependant, info)
        info["scopes"] = frozenset(info["scopes"])
        http.extend(RouteInfo(method, path, **info) for method in sorted(context.methods or ()))
    return http, other


_HTTP_ROUTES, _OTHER_ROUTES = _routes_of(application_api.router.routes)
_AUTHENTICATED = [route for route in _HTTP_ROUTES if route.authenticated]
_SCOPED = [route for route in _AUTHENTICATED if route.scopes]
_ADMIN = [route for route in _AUTHENTICATED if route.admin_scopes]
_SESSION_ONLY_FOR_KEYS = [route for route in _SCOPED if route.session_only and route.key_can_hold_scopes]
_KEY_REACHABLE = [route for route in _AUTHENTICATED if route.key_can_hold_scopes and not route.session_only]


def _ids(routes: list[RouteInfo]) -> list[str]:
    return [route.key for route in routes]


def _committed_user(committed_sessions: sessionmaker, make: Callable[..., Any] = make_user, **fields: Any):
    with committed_sessions() as db:
        user = make(db, **fields)
        db.commit()
    return user


def _holder(
    app: FastAPI,
    committed_sessions: sessionmaker,
    scopes: set[str] | frozenset[str],
    make: Callable[..., Any] = make_user,
) -> KeyHolder:
    """Return a client holding a key of exactly these scopes, owned by a new user (admin when ``make_admin``).

    ``model_construct`` lets a key row hold scopes the request schema would refuse, as a row written by an older
    version or by hand could.
    """
    with committed_sessions() as db:
        user = make(db)
        key, raw_key = make_api_key(db, user, scopes=cast(list[api_keys_constants.ApiKeyScope], sorted(scopes)))
        db.commit()
    return key_client(app, user, key, raw_key)


def _call(client, route: RouteInfo):
    return client.request(route.method, route.url())


def _is_refused(response) -> bool:
    return response.status_code in {401, 403}


def _audit_rows(committed_sessions: sessionmaker, action) -> list[AuditLog]:
    with committed_sessions() as db:
        return list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action.id)))


def _assert_scope_denied(response, route: RouteInfo, *, within: frozenset[str]) -> None:
    """Assert the 403 a missing scope answers with: problem type, the missing scopes and the scope challenge."""
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["type"] == PERMISSION_DENIED
    assert body["missing_scopes"], body
    assert set(body["missing_scopes"]) <= within
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer") and 'error="insufficient_scope"' in challenge


def _assert_one_scope_denial(committed_sessions: sessionmaker, holder_user_id: uuid.UUID, missing: list[str]) -> None:
    rows = _audit_rows(committed_sessions, authentication_audit_actions.SCOPE_DENIED)
    assert [(row.outcome, row.actor_id) for row in rows] == [("denied", str(holder_user_id))]
    assert rows[0].details is not None and rows[0].details["missing_scopes"] == missing


class TestTheMatrixCoversTheApplication:
    def test_the_table_is_the_routes_of_the_built_application(self, app):
        built, other = _routes_of(app.routes)

        assert built == _HTTP_ROUTES
        assert other == _OTHER_ROUTES

    def test_every_route_checks_scopes_or_is_registered_as_unauthenticated(self):
        unclassified = [
            route.key
            for route in _HTTP_ROUTES
            if not route.has_scope_check and route.key not in _UNAUTHENTICATED_ROUTES
        ]

        assert unclassified == [], "Guard with Security(check_scopes, ...) or register as open, with a reason:\n  " + (
            "\n  ".join(unclassified)
        )

    def test_a_route_that_resolves_the_caller_also_checks_scopes(self):
        unchecked = [route.key for route in _AUTHENTICATED if not route.has_scope_check]

        assert unchecked == []

    def test_the_unauthenticated_register_holds_only_routes_that_resolve_no_caller(self):
        by_key = {route.key: route for route in _HTTP_ROUTES}

        assert sorted(set(_UNAUTHENTICATED_ROUTES) - set(by_key)) == [], "stale entries"
        assert sorted(key for key in _UNAUTHENTICATED_ROUTES if by_key[key].authenticated) == []
        assert sorted(key for key in _UNAUTHENTICATED_ROUTES if by_key[key].has_scope_check) == []

    def test_a_route_that_declares_no_scope_is_registered_with_its_reason(self):
        empty = {route.key for route in _AUTHENTICATED if not route.scopes}

        assert empty == set(_ROUTES_WITHOUT_SCOPE)
        assert all(_ROUTES_WITHOUT_SCOPE.values())

    def test_every_other_route_under_the_api_root_is_a_registered_websocket(self):
        assert sorted(_OTHER_ROUTES) == sorted(_WEBSOCKET_ROUTES)

    def test_every_websocket_route_of_the_application_is_one_the_register_names(self, app):
        sockets = [
            context.path
            for context in iter_route_contexts(app.routes)
            if isinstance(context.original_route, APIWebSocketRoute)
        ]

        assert sorted(sockets) == sorted(_WEBSOCKET_ROUTES)

    def test_every_scope_a_route_requires_is_one_the_server_issues(self):
        required = {scope for route in _HTTP_ROUTES for scope in route.scopes}

        assert required <= set(auth_constants.ADMIN_ACCESS_SCOPE)


@pytest.mark.parametrize("route", _AUTHENTICATED, ids=_ids(_AUTHENTICATED))
def test_a_request_without_credentials_is_refused_before_anything_else(client, route):
    response = _call(client, route)

    assert response.status_code == 401, response.text
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert response.json()["type"] == INVALID_TOKEN


@pytest.mark.parametrize("route", _SCOPED, ids=_ids(_SCOPED))
def test_a_key_without_the_routes_scope_is_refused_and_the_refusal_is_audited(app, committed_sessions, route):
    holder = _holder(app, committed_sessions, _KEY_SCOPES - route.scopes)

    response = _call(holder.client, route)

    _assert_scope_denied(response, route, within=route.scopes)
    _assert_one_scope_denial(committed_sessions, holder.user.id, response.json()["missing_scopes"])


@pytest.mark.parametrize("route", _KEY_REACHABLE, ids=_ids(_KEY_REACHABLE))
def test_a_key_holding_exactly_the_routes_scopes_is_not_refused(app, committed_sessions, route):
    holder = _holder(app, committed_sessions, route.scopes)

    response = _call(holder.client, route)

    assert not _is_refused(response), response.text


@pytest.mark.parametrize("route", _SESSION_ONLY_FOR_KEYS, ids=_ids(_SESSION_ONLY_FOR_KEYS))
def test_a_key_holding_the_routes_scopes_is_still_refused_where_a_session_is_needed(app, committed_sessions, route):
    holder = _holder(app, committed_sessions, route.scopes)

    response = _call(holder.client, route)

    assert response.status_code == 403, response.text
    assert response.json()["type"] == PERMISSION_DENIED
    assert "signed-in session" in response.json()["detail"]


@pytest.mark.parametrize("route", _ADMIN, ids=_ids(_ADMIN))
def test_a_key_cannot_exceed_the_role_of_its_owner(app, committed_sessions, route):
    holder = _holder(app, committed_sessions, route.scopes)

    response = _call(holder.client, route)

    _assert_scope_denied(response, route, within=route.admin_scopes)
    _assert_one_scope_denial(committed_sessions, holder.user.id, response.json()["missing_scopes"])


def test_an_administrators_key_keeps_the_administrator_scope_it_holds(app, committed_sessions):
    holder = _holder(app, committed_sessions, {"users:read-all"}, make=make_admin)

    response = holder.client.get(f"{core_config.ROOT_PATH}/users/{holder.user.id}/identity-providers")

    assert response.status_code == 200


@pytest.mark.parametrize("route", _ADMIN, ids=_ids(_ADMIN))
def test_a_regular_user_is_refused_on_an_administrators_route(
    committed_sessions, sign_in: Callable[[users_schema.UserRead], SignedIn], route
):
    user = _committed_user(committed_sessions)

    response = _call(sign_in(user).client, route)

    _assert_scope_denied(response, route, within=route.admin_scopes)
    _assert_one_scope_denial(committed_sessions, user.id, response.json()["missing_scopes"])


@pytest.mark.parametrize("route", _ADMIN, ids=_ids(_ADMIN))
def test_an_administrator_gets_past_the_scope_check_of_an_administrators_route(
    committed_sessions, sign_in: Callable[[users_schema.UserRead], SignedIn], route
):
    admin = _committed_user(committed_sessions, make_admin)

    response = _call(sign_in(admin).client, route)

    assert not _is_refused(response), response.text


_GEARS = f"{core_config.ROOT_PATH}/gears"


class TestADeadCredentialIsRefused:
    def test_a_token_of_an_inactive_user_is_a_401(self, committed_sessions, sign_in):
        user = _committed_user(committed_sessions, active=False)

        response = sign_in(user).client.get(_GEARS)

        assert response.status_code == 401
        assert response.json()["type"] == INVALID_TOKEN

    def test_a_token_whose_user_is_deactivated_after_signing_in_is_a_401(self, committed_sessions, sign_in):
        signed_in = sign_in(_committed_user(committed_sessions))
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == signed_in.user.id).values(active=False)
            )
            db.commit()

        assert signed_in.client.get(_GEARS).status_code == 401

    def test_a_token_whose_session_has_ended_is_a_401(self, committed_sessions, sign_in):
        signed_in = sign_in(_committed_user(committed_sessions))
        with committed_sessions() as db:
            db.execute(
                sa.delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == signed_in.session_id)
            )
            db.commit()

        response = signed_in.client.get(_GEARS)

        assert response.status_code == 401
        assert response.json()["type"] == INVALID_TOKEN

    def test_a_security_generation_bump_alone_does_not_end_an_access_token(self, committed_sessions, sign_in):
        """The generation stamps one-time proofs (resets, MFA, OAuth state); a token ends with its session row."""
        signed_in = sign_in(_committed_user(committed_sessions))
        with committed_sessions() as db:
            security_generation_integration.stage_bump(signed_in.user.id, db)
            db.commit()

        assert signed_in.client.get(_GEARS).status_code == 200

    def test_a_revoked_key_is_a_401_and_the_refusal_is_audited(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, {"gears:read"})
        with committed_sessions() as db:
            api_keys_integration.revoke_api_key(holder.key.id, holder.user.id, db)
            db.commit()

        response = holder.client.get(_GEARS)

        assert response.status_code == 401
        assert response.json()["type"] == UNAUTHORIZED
        assert response.headers["WWW-Authenticate"].startswith("ApiKey")
        _assert_key_refusal(committed_sessions, "revoked", outcome="failure")

    def test_an_expired_key_is_a_401_and_the_refusal_is_audited(self, app, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            key, raw_key = make_api_key(
                db,
                user,
                scopes=[api_keys_constants.ApiKeyScope.GEARS_READ],
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
            db.commit()

        response = key_client(app, user, key, raw_key).client.get(_GEARS)

        assert response.status_code == 401
        assert response.json()["type"] == UNAUTHORIZED
        assert response.headers["WWW-Authenticate"].startswith("ApiKey")
        _assert_key_refusal(committed_sessions, "expired", outcome="failure")

    def test_an_unknown_key_is_a_401_and_the_refusal_is_audited(self, client, committed_sessions):
        response = client.get(_GEARS, headers={"X-API-Key": "endurain_not-a-key"})

        assert response.status_code == 401
        assert response.json()["type"] == UNAUTHORIZED
        assert response.headers["WWW-Authenticate"].startswith("ApiKey")
        _assert_key_refusal(committed_sessions, "unknown_key", outcome="failure")

    def test_a_key_of_an_inactive_owner_is_a_403_and_the_refusal_is_audited(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, {"gears:read"})
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == holder.user.id).values(active=False)
            )
            db.commit()

        response = holder.client.get(_GEARS)

        assert response.status_code == 403
        assert response.json()["type"] == PERMISSION_DENIED
        _assert_key_refusal(committed_sessions, "owner_inactive", outcome="denied")


def _assert_key_refusal(committed_sessions: sessionmaker, reason: str, *, outcome: str) -> None:
    rows = _audit_rows(committed_sessions, authentication_audit_actions.API_KEY_AUTHENTICATE)
    assert [(row.outcome, (row.details or {}).get("reason")) for row in rows] == [(outcome, reason)]
