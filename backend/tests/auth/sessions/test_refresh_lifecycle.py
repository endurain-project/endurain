"""A refresh token rotates once; reusing a rotated one ends the session; concurrent refreshes have one winner."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.constants as auth_constants
import modules.auth.rotated_refresh_tokens.models as rotated_models
import modules.auth.sessions.models as sessions_models
from tests._factories.auth import SignedIn
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user

_REFRESH = f"{core_config.ROOT_PATH}/auth/refresh"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_COOKIE = authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME


def _signed_in(committed_sessions, sign_in) -> SignedIn:
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return sign_in(user)


def _refresher(app, refresh_token: str) -> TestClient:
    """A web client that holds a refresh cookie and no access token."""
    client = TestClient(
        app, headers={"X-Client-Type": auth_constants.ClientType.WEB.value, "Origin": app.state.cors_allow_origins[0]}
    )
    client.cookies.set(_COOKIE, refresh_token)
    return client


def _rotated_rows(committed_sessions, session_id: uuid.UUID) -> list[rotated_models.RotatedRefreshToken]:
    with committed_sessions() as db:
        return list(
            db.scalars(
                sa.select(rotated_models.RotatedRefreshToken).where(
                    rotated_models.RotatedRefreshToken.token_family_id == session_id
                )
            )
        )


def _session(committed_sessions, session_id: uuid.UUID) -> sessions_models.UsersSessions | None:
    with committed_sessions() as db:
        return db.get(sessions_models.UsersSessions, session_id)


def _end_grace_window(committed_sessions, session_id: uuid.UUID) -> None:
    """Move the rotation's grace window into the past, as if the rotation had happened a minute ago."""
    with committed_sessions() as db:
        db.execute(
            sa.update(rotated_models.RotatedRefreshToken)
            .where(rotated_models.RotatedRefreshToken.token_family_id == session_id)
            .values(
                rotated_at=datetime.now(UTC) - timedelta(minutes=1),
                expires_at=datetime.now(UTC) - timedelta(seconds=50),
            )
        )
        db.commit()


class TestRotation:
    def test_a_refresh_returns_new_tokens_and_the_session_holds_the_new_refresh_token(
        self, app, committed_sessions, sign_in
    ):
        signed_in = _signed_in(committed_sessions, sign_in)
        before = _session(committed_sessions, signed_in.session_id)

        response = _refresher(app, signed_in.refresh_token).post(_REFRESH)

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == str(signed_in.session_id)
        assert body["access_token"] != signed_in.access_token
        new_refresh_token = response.cookies[_COOKIE]
        assert new_refresh_token != signed_in.refresh_token
        after = _session(committed_sessions, signed_in.session_id)
        assert before is not None and after is not None
        assert after.rotation_count == before.rotation_count + 1
        assert after.refresh_token != before.refresh_token
        assert len(_rotated_rows(committed_sessions, signed_in.session_id)) == 1
        assert _refresher(app, new_refresh_token).post(_REFRESH).status_code == 200

    def test_the_new_access_token_is_accepted(self, app, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)

        body = _refresher(app, signed_in.refresh_token).post(_REFRESH).json()

        authorised = TestClient(
            app,
            headers={
                "Authorization": f"Bearer {body['access_token']}",
                "X-Client-Type": auth_constants.ClientType.WEB.value,
            },
        )
        assert authorised.get(_PROFILE).status_code == 200

    def test_a_replay_inside_the_grace_window_gets_the_same_replacement_without_a_second_rotation(
        self, app, committed_sessions, sign_in
    ):
        signed_in = _signed_in(committed_sessions, sign_in)
        first = _refresher(app, signed_in.refresh_token).post(_REFRESH)

        replay = _refresher(app, signed_in.refresh_token).post(_REFRESH)

        assert replay.status_code == 200
        assert replay.cookies[_COOKIE] == first.cookies[_COOKIE]
        assert replay.json()["session_id"] == str(signed_in.session_id)
        assert len(_rotated_rows(committed_sessions, signed_in.session_id)) == 1
        session = _session(committed_sessions, signed_in.session_id)
        assert session is not None and session.rotation_count == 1
        assert audit_rows(committed_sessions, authentication_audit_actions.REFRESH_TOKEN_REUSE) == []

    def test_a_replay_inside_the_grace_window_from_another_client_is_reuse(self, app, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        _refresher(app, signed_in.refresh_token).post(_REFRESH)
        thief = _refresher(app, signed_in.refresh_token)

        response = thief.post(_REFRESH, headers={"User-Agent": "another-client"})

        assert response.status_code == 401
        assert _session(committed_sessions, signed_in.session_id) is None


class TestReuse:
    def test_a_rotated_token_presented_after_the_grace_window_ends_the_session_and_its_access_token(
        self, app, committed_sessions, sign_in
    ):
        signed_in = _signed_in(committed_sessions, sign_in)
        rotated = _refresher(app, signed_in.refresh_token).post(_REFRESH)
        assert rotated.status_code == 200
        _end_grace_window(committed_sessions, signed_in.session_id)

        response = _refresher(app, signed_in.refresh_token).post(_REFRESH)

        assert response.status_code == 401
        assert response.json()["type"] == "urn:endurain:error:session-ended"
        assert _session(committed_sessions, signed_in.session_id) is None
        assert _rotated_rows(committed_sessions, signed_in.session_id) == []
        assert signed_in.client.get(_PROFILE).status_code == 401
        assert _refresher(app, rotated.cookies[_COOKIE]).post(_REFRESH).status_code == 401

    def test_reuse_is_audited_as_denied_against_the_token_owner(self, app, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        _refresher(app, signed_in.refresh_token).post(_REFRESH)
        _end_grace_window(committed_sessions, signed_in.session_id)

        _refresher(app, signed_in.refresh_token).post(_REFRESH)

        rows = audit_rows(committed_sessions, authentication_audit_actions.REFRESH_TOKEN_REUSE)
        assert [(row.outcome, row.target_type, row.target_id) for row in rows] == [
            ("denied", "user", str(signed_in.user.id))
        ]

    def test_a_refresh_of_an_ended_session_is_refused_and_audited(self, app, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        with committed_sessions() as db:
            db.execute(sa.delete(sessions_models.UsersSessions))
            db.commit()

        response = _refresher(app, signed_in.refresh_token).post(_REFRESH)

        assert response.status_code == 401
        assert response.json()["type"] == "urn:endurain:error:session-ended"
        rows = audit_rows(committed_sessions, authentication_audit_actions.REFRESH)
        assert [(row.outcome, row.details["reason"]) for row in rows] == [("failure", "session_not_found")]

    def test_a_refresh_token_that_is_not_the_sessions_is_refused_and_audited(self, app, committed_sessions, sign_in):
        first = _signed_in(committed_sessions, sign_in)
        second = sign_in(first.user)
        other = _session(committed_sessions, second.session_id)
        assert other is not None
        forged = _refresher(app, first.refresh_token)
        with committed_sessions() as db:
            db.execute(
                sa.update(sessions_models.UsersSessions)
                .where(sessions_models.UsersSessions.id == first.session_id)
                .values(refresh_token=other.refresh_token)
            )
            db.commit()

        response = forged.post(_REFRESH)

        assert response.status_code == 401
        rows = audit_rows(committed_sessions, authentication_audit_actions.REFRESH)
        assert [(row.outcome, row.details["reason"]) for row in rows] == [("failure", "invalid_token")]
        assert _session(committed_sessions, first.session_id) is not None


class TestConcurrentRefresh:
    def test_two_simultaneous_refreshes_of_one_token_rotate_the_session_once(self, app, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        barrier = threading.Barrier(2)

        def refresh():
            client = _refresher(app, signed_in.refresh_token)
            barrier.wait(timeout=10)
            return client.post(_REFRESH)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = (future.result(timeout=60) for future in [pool.submit(refresh), pool.submit(refresh)])

        assert (first.status_code, second.status_code) == (200, 200)
        assert first.cookies[_COOKIE] == second.cookies[_COOKIE]
        assert first.cookies[_COOKIE] != signed_in.refresh_token
        assert len(_rotated_rows(committed_sessions, signed_in.session_id)) == 1
        session = _session(committed_sessions, signed_in.session_id)
        assert session is not None and session.rotation_count == 1
        assert _refresher(app, first.cookies[_COOKIE]).post(_REFRESH).status_code == 200
        assert audit_rows(committed_sessions, authentication_audit_actions.REFRESH_TOKEN_REUSE) == []
