"""Linked Strava integrations and the fake Strava HTTP API, for tests on the real database.

Strava is a third party: :class:`FakeStrava` answers at the HTTP layer the client uses (``requests``' transport
adapter), so ``stravalib`` parses the payloads, and everything of ours runs for real.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jasil.providers as platform_providers
import pytest
import requests
import requests.adapters
from jasil.audit.models import AuditLog
from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.notifications.models as notifications_models
import modules.users.users_integrations.contracts as user_integrations_contracts
import modules.users.users_integrations.integration_service as user_integrations_integration

#: The Strava application id and secret a linked user is given.
CLIENT_ID = "424242"
CLIENT_SECRET = "strava-client-secret"
ACCESS_TOKEN = "strava-access-token"
REFRESH_TOKEN = "strava-refresh-token"

_API_PREFIX = "/api/v3"


@dataclass(frozen=True)
class Reply:
    """What the fake Strava answers to a request.

    Attributes:
        status: The HTTP status.
        body: The JSON body, or ``None`` for an empty one; a ``str`` or ``bytes`` body is sent as it is.
        headers: The response headers.
    """

    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Call:
    """A request the client sent to the fake Strava.

    Attributes:
        method: The HTTP method.
        path: The path below ``/api/v3``, or ``/oauth/...`` for the authorization endpoints.
        params: The query parameters, one value each.
        form: The form fields of the body, one value each.
        headers: The request headers.
    """

    method: str
    path: str
    params: dict[str, str]
    form: dict[str, str]
    headers: dict[str, str]


def ok(body: Any = None) -> Reply:
    """Answer 200 with a JSON body.

    Args:
        body: The JSON body.

    Returns:
        The reply.
    """
    return Reply(200, body)


def refused(status: int, *, resource: str | None = None, headers: dict[str, str] | None = None) -> Reply:
    """Answer an error, with the ``errors`` list Strava puts in the body when it names a resource.

    Args:
        status: The HTTP status.
        resource: The resource the error names, such as ``RefreshToken``.
        headers: The response headers.

    Returns:
        The reply.
    """
    errors = [{"resource": resource, "field": "refresh_token", "code": "invalid"}] if resource else []
    return Reply(status, {"message": HTTPStatus(status).phrase, "errors": errors}, headers or {})


def rate_limited(*, daily: bool = False) -> Reply:
    """Answer 429 with the usage headers of the 15-minute or the daily limit.

    Args:
        daily: Whether the daily usage reached the daily limit, rather than the 15-minute one.

    Returns:
        The reply.
    """
    usage = "100,1000" if daily else "100,50"
    return refused(429, headers={"X-RateLimit-Limit": "100,1000", "X-RateLimit-Usage": usage})


class FakeStrava:
    """Strava's HTTP API, answering by method and path and recording what it was asked.

    A request nobody arranged an answer for is answered 500 and listed in :attr:`unrouted`, which the fixture
    asserts empty when the test ends.
    """

    def __init__(self) -> None:
        """Start with no routes and no calls."""
        self._routes: dict[tuple[str, str], list[Reply | Callable[[Call], Reply]]] = {}
        self.calls: list[Call] = []
        self.unrouted: list[str] = []

    def on(self, method: str, path: str, *replies: Reply | Callable[[Call], Reply]) -> None:
        """Arrange the answers to a route: each call takes the next one, and the last repeats.

        Args:
            method: The HTTP method.
            path: The path below ``/api/v3``, or ``/oauth/token`` and ``/oauth/deauthorize``.
            *replies: The answers, in order; a callable receives the call and returns one.
        """
        self._routes[(method.upper(), path)] = list(replies)

    def made(self, method: str, path: str) -> list[Call]:
        """List the calls made to a route.

        Args:
            method: The HTTP method.
            path: The route's path.

        Returns:
            The calls, in order.
        """
        return [call for call in self.calls if (call.method, call.path) == (method.upper(), path)]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the network under ``requests`` with this fake for the test.

        Args:
            monkeypatch: The test's monkeypatch, which restores the transport afterwards.
        """

        def send(_adapter: requests.adapters.HTTPAdapter, request: requests.PreparedRequest, **_kwargs: object):
            return self._answer(request)

        monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)

    def _answer(self, request: requests.PreparedRequest) -> requests.Response:
        """Build the response to a request from the arranged routes.

        Args:
            request: What the client sent.

        Returns:
            The response.
        """
        url = urlsplit(str(request.url))
        path = url.path.removeprefix(_API_PREFIX)
        body = request.body if isinstance(request.body, str) else (request.body or b"").decode()
        call = Call(
            method=str(request.method).upper(),
            path=path,
            params={key: values[0] for key, values in parse_qs(url.query).items()},
            form={key: values[0] for key, values in parse_qs(body).items()},
            headers=dict(request.headers),
        )
        self.calls.append(call)
        replies = self._routes.get((call.method, call.path))
        if not replies:
            self.unrouted.append(f"{call.method} {call.path}")
            reply: Reply = refused(500)
        else:
            chosen = replies.pop(0) if len(replies) > 1 else replies[0]
            reply = chosen(call) if callable(chosen) else chosen
        response = requests.Response()
        response.status_code = reply.status
        response.reason = HTTPStatus(reply.status).phrase
        response.url = str(request.url)
        response.request = request
        response.encoding = "utf-8"
        response.headers.update({"Content-Type": "application/json", **reply.headers})
        if isinstance(reply.body, bytes | str):
            response._content = reply.body if isinstance(reply.body, bytes) else reply.body.encode()
        else:
            response._content = b"" if reply.body is None else json.dumps(reply.body).encode()
        return response


def link_strava(
    db: Session,
    user_id: uuid.UUID,
    *,
    expires_in: timedelta = timedelta(hours=6),
    access_token: str = ACCESS_TOKEN,
    refresh_token: str = REFRESH_TOKEN,
    client_id: str | None = CLIENT_ID,
    sync_gear: bool = False,
) -> None:
    """Store a user's Strava client and tokens through the integrations module (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user to link.
        expires_in: How long from now the access token stays valid; negative for an expired one.
        access_token: The access token.
        refresh_token: The refresh token.
        client_id: The Strava application id, or ``None`` to store no client.
        sync_gear: Whether the user syncs Strava gear.
    """
    if client_id is not None:
        user_integrations_integration.set_strava_client(user_id, client_id, CLIENT_SECRET, db, if_match="*")
    user_integrations_integration.link_strava_account(
        user_id, token_payload(access_token, refresh_token, expires_in), db
    )
    if sync_gear:
        user_integrations_integration.set_strava_sync_gear(user_id, True, db)


def audit_rows(db: Session, *action_ids: str) -> list[AuditLog]:
    """Read the audit rows of the given actions, oldest first.

    Args:
        db: Database session.
        *action_ids: The actions to read.

    Returns:
        The rows.
    """
    statement = select(AuditLog).where(AuditLog.action_id.in_(action_ids)).order_by(AuditLog.occurred_at, AuditLog.id)
    return list(db.scalars(statement))


def notifications_of(
    db: Session, user_id: uuid.UUID, notification_type: int
) -> list[notifications_models.Notification]:
    """Read a user's notifications of one type.

    Args:
        db: Database session.
        user_id: The user.
        notification_type: The stored notification type.

    Returns:
        The notifications.
    """
    statement = select(notifications_models.Notification).where(
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.type == notification_type,
    )
    return list(db.scalars(statement))


def token_payload(
    access_token: str, refresh_token: str, expires_in: timedelta = timedelta(hours=6)
) -> user_integrations_contracts.StravaTokens:
    """Build the tokens Strava's token endpoint returns.

    Args:
        access_token: The access token.
        refresh_token: The refresh token.
        expires_in: How long from now the access token stays valid.

    Returns:
        The token response body.
    """
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int((datetime.now(UTC) + expires_in).timestamp()),
    }


def summary_activity(activity_id: int, **overrides: object) -> dict[str, Any]:
    """Build an activity as the activities list returns it.

    Args:
        activity_id: Strava's id of the activity.
        **overrides: Fields that replace the defaults of a one-hour run.

    Returns:
        The payload.
    """
    values: dict[str, Any] = {
        "id": activity_id,
        "name": "Morning run",
        "distance": 10000.0,
        "moving_time": 3500,
        "elapsed_time": 3600,
        "total_elevation_gain": 50.0,
        "sport_type": "Run",
        "start_date": "2025-03-10T08:00:00Z",
        "start_date_local": "2025-03-10T08:00:00Z",
        "timezone": "(GMT+00:00) UTC",
        "average_speed": 2.78,
        "max_speed": 5.0,
        "gear_id": None,
    }
    values.update(overrides)
    return values


def detailed_activity(activity_id: int, **overrides: object) -> dict[str, Any]:
    """Build an activity as the activity endpoint returns it.

    Args:
        activity_id: Strava's id of the activity.
        **overrides: Fields that replace the defaults of a one-hour run.

    Returns:
        The payload.
    """
    return summary_activity(
        activity_id,
        **{
            "average_heartrate": 145.0,
            "max_heartrate": 175.0,
            "calories": 500.0,
            "description": "Easy loop",
            "start_latlng": None,
            **overrides,
        },
    )


def streams_payload(**streams: list[Any]) -> dict[str, Any]:
    """Build the streams Strava returns keyed by type.

    Args:
        **streams: The values of each stream, by the stream's name (``time``, ``heartrate``, ``latlng``, ...).

    Returns:
        The payload.
    """
    return {
        name: {"data": data, "series_type": "time", "original_size": len(data), "resolution": "high"}
        for name, data in streams.items()
    }


def lap_payload(lap_index: int = 1, **overrides: object) -> dict[str, Any]:
    """Build a lap as the laps endpoint returns it.

    Args:
        lap_index: The lap's position in the activity, from one.
        **overrides: Fields that replace the defaults of a lap over the first four samples.

    Returns:
        The payload.
    """
    values: dict[str, Any] = {
        "id": 900 + lap_index,
        "lap_index": lap_index,
        "name": f"Lap {lap_index}",
        "start_index": 0,
        "end_index": 3,
        "start_date": "2025-03-10T08:00:00Z",
        "start_date_local": "2025-03-10T08:00:00Z",
        "elapsed_time": 30,
        "moving_time": 30,
        "distance": 100.0,
        "average_speed": 3.0,
        "max_speed": 4.0,
        "average_heartrate": 140.0,
        "max_heartrate": 150.0,
    }
    values.update(overrides)
    return values


def athlete_payload(bikes: list[str] | None = None, shoes: list[str] | None = None) -> dict[str, Any]:
    """Build the athlete with the gear ids listed on the profile.

    Args:
        bikes: The Strava ids of the athlete's bikes.
        shoes: The Strava ids of the athlete's shoes.

    Returns:
        The payload.
    """
    return {
        "id": 12345,
        "firstname": "Test",
        "lastname": "Athlete",
        "bikes": [{"id": gear_id, "name": "listed", "primary": False, "distance": 0} for gear_id in bikes or []],
        "shoes": [{"id": gear_id, "name": "listed", "primary": False, "distance": 0} for gear_id in shoes or []],
    }


def gear_payload(gear_id: str, **overrides: object) -> dict[str, Any]:
    """Build a piece of gear as the gear endpoint returns it.

    Args:
        gear_id: Strava's id of the gear.
        **overrides: Fields that replace the defaults.

    Returns:
        The payload.
    """
    values: dict[str, Any] = {
        "id": gear_id,
        "name": "Road bike",
        "brand_name": "Canyon",
        "model_name": "Endurace",
        "primary": False,
        "distance": 1000.0,
        "resource_state": 3,
    }
    values.update(overrides)
    return values


class UnavailableState:
    """A platform state provider whose backing store is down: every operation raises, as Redis does when unreachable."""

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Answer any state operation by raising.

        Args:
            name: The operation asked for.

        Returns:
            A function that raises.
        """

        def unavailable(*_args: object, **_kwargs: object) -> Any:
            raise platform_providers.StateBackendUnavailableError(f"{name}: the state store is down")

        return unavailable


def revoke_strava_access(db: Session, user_id: uuid.UUID, *, revoked_ago: timedelta) -> None:
    """Clear a linked user's tokens as a revocation that happened some time ago (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user whose access Strava revoked; their Strava must be linked.
        revoked_ago: How long before now the access was revoked.
    """
    stored = user_integrations_integration.require_user_integrations(user_id, db)
    assert stored.strava_refresh_token is not None
    user_integrations_integration.unlink_strava_tokens_if_refresh_token(
        user_id, stored.strava_refresh_token, db, revoked_at=datetime.now(UTC) - revoked_ago
    )
    db.flush()
