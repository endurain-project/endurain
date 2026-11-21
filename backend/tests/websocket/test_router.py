"""The websocket routes through the production application: the ticket, the handshake and the live socket."""

import dataclasses
import uuid

import jasil.runtime as jasil_runtime
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from starlette.testclient import WebSocketDenialResponse

import core.config as core_config
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.sessions.models as sessions_models
import modules.websocket.dependencies as websocket_dependencies
import modules.websocket.integration_service as websocket_integration
import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service
import modules.websocket.subscriber_registry as websocket_subscriber_registry
import modules.websocket.ticket_store as websocket_ticket_store
from tests._factories.users import make_user
from tests._factories.websockets import UnavailableState

_TICKET_URL = f"{core_config.ROOT_PATH}/ws/ticket"
_SOCKET_URL = f"{core_config.ROOT_PATH}/ws"


@pytest.fixture
def signed_in(committed_sessions, sign_in):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return sign_in(user)


def _store() -> websocket_ticket_store.WsTicketStore:
    platform = jasil_runtime.get_active_platform()
    return websocket_dependencies.get_ws_ticket_store(platform.state, platform.clock)


def _ticket(signed_in) -> str:
    return signed_in.client.post(_TICKET_URL).json()["ticket"]


def _refused_with(client, ticket: str, **kwargs) -> int:
    """Open the socket and return the close code the server answered the handshake with."""
    with (
        pytest.raises((WebSocketDisconnect, WebSocketDenialResponse)) as refusal,
        client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}", **kwargs),
    ):
        pass
    return refusal.value.code if isinstance(refusal.value, WebSocketDisconnect) else refusal.value.status_code


class TestIssueTicket:
    def test_the_ticket_is_bound_to_the_user_and_session_that_asked(self, signed_in):
        response = signed_in.client.post(_TICKET_URL)

        assert response.status_code == 201
        owner = _store().consume_ticket(response.json()["ticket"])
        assert owner == websocket_ticket_store.WsTicketOwner(user_id=signed_in.user.id, session_id=signed_in.session_id)

    def test_the_ticket_is_a_credential_no_cache_may_keep(self, signed_in):
        response = signed_in.client.post(_TICKET_URL)

        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    def test_every_request_gets_a_different_ticket(self, signed_in):
        assert _ticket(signed_in) != _ticket(signed_in)

    def test_a_state_outage_is_a_503_not_a_ticket(self, signed_in):
        platform = jasil_runtime.get_active_platform()
        jasil_runtime.set_active_platform(dataclasses.replace(platform, state=UnavailableState()))

        assert signed_in.client.post(_TICKET_URL).status_code == 503


class TestHandshake:
    def test_a_valid_ticket_opens_a_socket_that_receives_the_users_hints(self, holding_client, signed_in):
        ticket = _ticket(signed_in)

        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket:
            websocket_integration.push_to_user(signed_in.user.id, {"message": "NEW", "notification_id": 3})
            assert socket.receive_json() == {"message": "NEW", "notification_id": 3}

    def test_another_users_hint_does_not_reach_the_socket(self, holding_client, signed_in):
        ticket = _ticket(signed_in)

        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket:
            websocket_integration.push_to_user(uuid.uuid4(), {"message": "NOT_FOR_YOU"})
            websocket_integration.push_to_user(signed_in.user.id, {"message": "FOR_YOU"})
            assert socket.receive_json() == {"message": "FOR_YOU"}

    def test_an_unknown_ticket_is_refused_as_a_policy_violation(self, holding_client):
        assert _refused_with(holding_client, "bad-ticket") == 1008

    def test_a_ticket_opens_one_socket_only(self, holding_client, signed_in):
        ticket = _ticket(signed_in)
        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}"):
            pass

        assert _refused_with(holding_client, ticket) == 1008

    def test_a_missing_ticket_is_refused(self, holding_client):
        with (
            pytest.raises((WebSocketDisconnect, WebSocketDenialResponse)),
            holding_client.websocket_connect(_SOCKET_URL),
        ):
            pass

    def test_a_foreign_browser_origin_is_refused_and_keeps_the_ticket(self, holding_client, signed_in):
        ticket = _ticket(signed_in)

        assert _refused_with(holding_client, ticket, headers={"origin": "https://evil.example"}) == 1008
        assert _store().consume_ticket(ticket) is not None

    def test_the_null_origin_is_refused(self, holding_client, signed_in):
        assert _refused_with(holding_client, _ticket(signed_in), headers={"origin": "null"}) == 1008

    def test_every_browser_origin_is_refused_when_none_are_configured(self, holding_client, signed_in):
        origin = holding_client.app.state.cors_allow_origins[0]
        holding_client.app.state.cors_allow_origins = []

        assert _refused_with(holding_client, _ticket(signed_in), headers={"origin": origin}) == 1008

    def test_a_client_that_sends_no_origin_is_not_a_browser_and_is_let_through(self, holding_client, signed_in):
        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={_ticket(signed_in)}"):
            pass

    def test_a_served_origin_is_let_through(self, holding_client, signed_in):
        origin = holding_client.app.state.cors_allow_origins[0]
        ticket = _ticket(signed_in)

        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}", headers={"origin": origin}):
            pass

    def test_a_network_over_the_handshake_limit_is_refused_and_keeps_the_ticket(self, holding_client, signed_in):
        ticket = _ticket(signed_in)
        store = _store()
        for _ in range(websocket_ticket_store.MAX_HANDSHAKES_PER_WINDOW):
            assert store.allow_handshake("testclient")

        assert _refused_with(holding_client, ticket) == 1013
        assert store.consume_ticket(ticket) is not None

    def test_a_state_outage_closes_with_try_again_later(self, holding_client, signed_in):
        ticket = _ticket(signed_in)
        platform = jasil_runtime.get_active_platform()
        jasil_runtime.set_active_platform(dataclasses.replace(platform, state=UnavailableState()))

        assert _refused_with(holding_client, ticket) == 1013

    def test_a_ticket_whose_session_is_gone_is_closed_as_revoked(self, holding_client, committed_sessions, signed_in):
        ticket = _ticket(signed_in)
        with committed_sessions() as db:
            db.execute(
                delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == signed_in.session_id)
            )
            db.commit()

        with (
            holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket,
            pytest.raises(WebSocketDisconnect) as closed,
        ):
            socket.receive_json()

        assert closed.value.code == websocket_manager.SESSION_ENDED_CLOSE_CODE

    def test_the_ticket_of_an_expired_session_is_closed_as_revoked(self, holding_client, committed_sessions, signed_in):
        ticket = _ticket(signed_in)
        with committed_sessions() as db:
            db.execute(
                update(sessions_models.UsersSessions)
                .where(sessions_models.UsersSessions.id == signed_in.session_id)
                .values(expires_at=sessions_models.UsersSessions.created_at)
            )
            db.commit()

        with (
            holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket,
            pytest.raises(WebSocketDisconnect) as closed,
        ):
            socket.receive_json()

        assert closed.value.code == websocket_manager.SESSION_ENDED_CLOSE_CODE


class TestLiveSocket:
    def test_a_frame_from_the_client_closes_the_socket_as_a_policy_violation(self, holding_client, signed_in):
        ticket = _ticket(signed_in)

        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket:
            socket.send_text("hello")
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()

        assert closed.value.code == 1008

    def test_a_socket_older_than_the_limit_is_closed_as_going_away(self, holding_client, signed_in, monkeypatch):
        monkeypatch.setattr(websocket_service, "MAX_CONNECTION_SECONDS", 0.05)
        ticket = _ticket(signed_in)

        with (
            holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}") as socket,
            pytest.raises(WebSocketDisconnect) as closed,
        ):
            socket.receive_json()

        assert closed.value.code == 1001

    def test_a_leaving_client_is_dropped_from_the_registry(self, holding_client, signed_in):
        ticket = _ticket(signed_in)

        with holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ticket}"):
            assert len(websocket_manager.get_websocket_manager().get_connections(signed_in.user.id)) == 1
        holding_client.portal.call(lambda: None)

        assert websocket_manager.get_websocket_manager().get_connections(signed_in.user.id) == []

    def test_logging_out_closes_the_sockets_of_that_session_only(self, holding_client, signed_in, sign_in):
        platform = jasil_runtime.get_active_platform()
        websocket_subscriber_registry.register_bus_subscribers(platform.events)
        other_session = sign_in(signed_in.user)
        ours, theirs = _ticket(signed_in), _ticket(other_session)

        with (
            holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={ours}") as closing,
            holding_client.websocket_connect(f"{_SOCKET_URL}?ticket={theirs}") as staying,
        ):
            browser = TestClient(
                holding_client.app,
                headers={"X-Client-Type": "web", "Origin": holding_client.app.state.cors_allow_origins[0]},
            )
            browser.cookies.set(authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME, signed_in.refresh_token)
            assert browser.post(f"{core_config.ROOT_PATH}/auth/logout").status_code == 200

            with pytest.raises(WebSocketDisconnect) as closed:
                closing.receive_json()
            websocket_integration.push_to_user(signed_in.user.id, {"message": "STILL_HERE"})
            assert staying.receive_json() == {"message": "STILL_HERE"}

        assert closed.value.code == websocket_manager.SESSION_ENDED_CLOSE_CODE
