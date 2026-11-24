"""Serving websocket connections and delivering hints to them."""

import asyncio
import uuid

import pytest

import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service
from tests._factories.users import make_user
from tests._factories.websockets import FakeWebSocket, client_left, data_frame, disconnect_frame

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
SESSION_1 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e01")
SESSION_2 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e02")


async def _manager_with(*connections, user_id=USER):
    manager = websocket_manager.WebSocketManager()
    for connection in connections:
        await manager.connect(user_id, SESSION_1, connection)
    return manager


class TestCloseRevokedConnections:
    async def _two_sessions(self):
        mine, other, someone_else = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        manager = websocket_manager.WebSocketManager()
        await manager.connect(USER, SESSION_1, mine)
        await manager.connect(USER, SESSION_2, other)
        await manager.connect(OTHER_USER, SESSION_1, someone_else)
        return manager, mine, other, someone_else

    async def test_a_revoked_session_closes_only_its_own_sockets(self):
        manager, mine, other, someone_else = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, SESSION_1, None, manager)

        assert mine.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]
        assert other.closed_with == someone_else.closed_with == []
        assert manager.get_connections(USER) == [other]

    async def test_a_user_wide_revocation_closes_every_socket_of_the_user(self):
        manager, mine, other, someone_else = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, None, None, manager)

        assert mine.closed_with == other.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]
        assert someone_else.closed_with == []
        assert manager.get_connections(USER) == []

    async def test_revoking_the_other_sessions_keeps_the_current_one(self):
        manager, mine, other, _ = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, None, SESSION_1, manager)

        assert mine.closed_with == []
        assert other.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]

    async def test_a_socket_that_cannot_be_closed_does_not_stop_the_others(self):
        manager, mine, other, _ = await self._two_sessions()
        mine.close_failure = RuntimeError("closed")

        await websocket_service.close_revoked_connections(USER, None, None, manager)

        assert other.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]
        assert manager.get_connections(USER) == []


class TestHasLiveSession:
    @pytest.fixture
    def session(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        return sign_in(user)

    def test_a_live_session_of_the_user_is_live(self, session):
        assert websocket_service.has_live_session(session.user.id, session.session_id) is True

    def test_an_unknown_session_is_not_live(self, session):
        assert websocket_service.has_live_session(session.user.id, uuid.uuid4()) is False

    def test_a_session_of_another_user_is_not_live(self, session):
        assert websocket_service.has_live_session(uuid.uuid4(), session.session_id) is False

    def test_an_expired_session_is_not_live(self, session, committed_sessions):
        import modules.auth.sessions.models as sessions_models

        with committed_sessions() as db:
            row = db.get(sessions_models.UsersSessions, session.session_id)
            row.expires_at = row.created_at
            db.commit()

        assert websocket_service.has_live_session(session.user.id, session.session_id) is False


class TestDeliverHint:
    async def test_a_user_without_a_connection_gets_no_push(self):
        manager = websocket_manager.WebSocketManager()

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is False

    async def test_every_connection_of_the_user_receives_the_hint(self):
        first, second = FakeWebSocket(), FakeWebSocket()
        manager = await _manager_with(first, second)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is True
        assert first.sent == second.sent == [{"message": "hi"}]

    async def test_one_broken_connection_does_not_stop_the_others_and_is_dropped(self):
        broken, healthy = FakeWebSocket(), FakeWebSocket()
        broken.send_failure = RuntimeError("closed")
        manager = await _manager_with(broken, healthy)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is True
        assert healthy.sent == [{"message": "hi"}]
        assert manager.get_connections(USER) == [healthy]

    async def test_the_hint_fails_when_every_send_fails(self):
        broken = FakeWebSocket()
        broken.send_failure = RuntimeError("closed")
        manager = await _manager_with(broken)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is False


class TestServeConnection:
    async def test_the_connection_is_registered_while_served_and_removed_after(self):
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket()
        seen = []

        async def receive():
            seen.append(manager.get_connections(USER))
            raise client_left()

        websocket.receive = receive

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert seen == [[websocket]]
        assert manager.get_connections(USER) == []

    async def test_a_leaving_client_ends_the_loop_without_a_close(self):
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket([disconnect_frame()])

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert websocket.closed_with == []
        assert manager.get_connections(USER) == []

    @pytest.mark.parametrize("frame", [{"text": "not json"}, {"bytes": b"\x00"}])
    async def test_a_data_frame_closes_the_connection(self, frame):
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket([data_frame(**frame)])

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert websocket.closed_with == [1008]
        assert manager.get_connections(USER) == []

    async def test_a_control_frame_does_not_close_the_connection(self):
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket([data_frame(), disconnect_frame()])

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert websocket.closed_with == []

    async def test_a_connection_is_closed_once_it_is_too_old(self, monkeypatch):
        monkeypatch.setattr(websocket_service, "MAX_CONNECTION_SECONDS", 0.01)
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket()

        await asyncio.wait_for(websocket_service.serve_connection(websocket, USER, SESSION_1, manager), timeout=5)

        assert websocket.closed_with == [1001]
        assert manager.get_connections(USER) == []

    async def test_the_connection_is_removed_however_the_loop_ends(self):
        manager = websocket_manager.WebSocketManager()
        websocket = FakeWebSocket([RuntimeError("boom")])

        with pytest.raises(RuntimeError):
            await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert manager.get_connections(USER) == []
