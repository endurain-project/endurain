"""Tests for identity-provider token maintenance integration operations."""

from unittest.mock import MagicMock, patch

import httpx2
import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.service as idp_service_module
from modules.auth.identity_providers import integration_service
from modules.auth.identity_providers.service import IdentityProviderService, TokenAction


def test_requesting_a_refresh_delegates_to_request_scoped_service(mock_db):
    with patch.object(integration_service, "_service") as service_factory:
        integration_service.request_idp_token_refresh(7, mock_db)
    service_factory.return_value.request_idp_token_refresh.assert_called_once_with(7, mock_db)


def test_clear_tokens_delegates_with_remote_revoke_option(mock_db):
    with patch.object(integration_service, "_service") as service_factory:
        integration_service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    service_factory.return_value.clear_all_idp_tokens.assert_called_once_with(7, mock_db, True)


def _service():
    return IdentityProviderService(MagicMock(), "https://app.example", "test")


class TestRequestIdpTokenRefresh:
    """The request clears what needs no network call and queues the rest; it never calls the provider."""

    def _request(self, mock_db, actions):
        service = _service()
        links = [MagicMock(idp_id=3 + index) for index in range(len(actions))]
        service._should_refresh_idp_token = MagicMock(side_effect=actions)
        service.refresh_idp_session = MagicMock()
        with (
            patch.object(
                idp_service_module.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=links,
            ),
            patch.object(
                idp_service_module.identity_provider_links_integration,
                "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
            ) as clear,
            patch.object(idp_service_module.idp_event_publishers, "publish_idp_token_refresh_requested") as publish,
        ):
            service.request_idp_token_refresh(7, mock_db)
        return service, clear, publish

    def test_a_link_to_refresh_queues_one_job_and_a_link_to_clear_is_cleared_now(self, mock_db):
        service, clear, publish = self._request(
            mock_db, [TokenAction.SKIP, TokenAction.REFRESH, TokenAction.CLEAR, TokenAction.REFRESH]
        )

        publish.assert_called_once_with(7, mock_db)
        clear.assert_called_once_with(7, 5, mock_db)
        service.refresh_idp_session.assert_not_called()

    def test_nothing_to_refresh_queues_nothing(self, mock_db):
        _, clear, publish = self._request(mock_db, [TokenAction.SKIP, TokenAction.CLEAR])

        publish.assert_not_called()
        clear.assert_called_once_with(7, 4, mock_db)

    def test_a_link_that_cannot_be_assessed_does_not_stop_the_others(self, mock_db):
        _, _, publish = self._request(mock_db, [RuntimeError("bad link"), TokenAction.REFRESH])

        publish.assert_called_once_with(7, mock_db)


class TestRefreshIdpTokens:
    """The job reads links in a short session and refreshes each outside any session."""

    def _run(self, actions, refresh_side_effect=None):
        service = _service()
        links = [MagicMock(idp_id=3 + index) for index in range(len(actions))]
        service._should_refresh_idp_token = MagicMock(side_effect=actions)
        open_sessions = 0
        open_during_refresh: list[int] = []

        class _Session:
            def __enter__(self):
                nonlocal open_sessions
                open_sessions += 1
                return MagicMock()

            def __exit__(self, *_exc):
                nonlocal open_sessions
                open_sessions -= 1
                return False

        def refresh(user_id, idp_id):
            open_during_refresh.append(open_sessions)
            if refresh_side_effect is not None:
                refresh_side_effect(idp_id)

        service.refresh_idp_session = MagicMock(side_effect=refresh)
        with (
            patch.object(idp_service_module.core_database, "SessionLocal", _Session),
            patch.object(
                idp_service_module.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=links,
            ),
        ):
            service.refresh_idp_tokens(7)
        return service, open_during_refresh

    def test_only_links_with_a_refresh_action_are_refreshed_with_no_session_open(self):
        service, open_during_refresh = self._run([TokenAction.SKIP, TokenAction.REFRESH, TokenAction.REFRESH])

        assert [call.args for call in service.refresh_idp_session.call_args_list] == [(7, 4), (7, 5)]
        assert open_during_refresh == [0, 0]

    def test_a_provider_that_fails_does_not_stop_the_others(self):
        def fail_first(idp_id):
            if idp_id == 3:
                raise core_exceptions.NotFoundError("disabled")

        service, _ = self._run([TokenAction.REFRESH, TokenAction.REFRESH], refresh_side_effect=fail_first)

        assert service.refresh_idp_session.call_count == 2


class TestRefreshIdpSession:
    """One refresh reads, calls the provider and writes in separate short sessions."""

    def _setup(self, service, *, fetch):
        idp = MagicMock(enabled=True)
        client = MagicMock()
        client.fetch_token.side_effect = fetch
        events: list[str] = []
        state = {"open": 0}

        class _Session:
            def __enter__(self):
                state["open"] += 1
                db = MagicMock()
                db.commit.side_effect = lambda: events.append("commit")
                return db

            def __exit__(self, *_exc):
                state["open"] -= 1
                return False

        service._resolve_token_endpoint = MagicMock(return_value="https://idp.example/token")
        service._decrypt_client_id = MagicMock(return_value="cid")
        service._decrypt_client_secret = MagicMock(return_value="secret")
        service._create_oauth_client = MagicMock(return_value=client)
        service._store_idp_tokens = MagicMock(side_effect=lambda *a: events.append("store"))
        patches = [
            patch.object(idp_service_module.core_database, "SessionLocal", _Session),
            patch.object(idp_service_module.idp_crud, "get_identity_provider", return_value=idp),
            patch.object(
                idp_service_module.identity_provider_links_integration,
                "get_user_identity_provider_refresh_token_by_user_id_and_idp_id",
                return_value="encrypted",
            ),
            patch.object(idp_service_module.core_cryptography, "decrypt_token_fernet", return_value="plain"),
            patch.object(
                idp_service_module.identity_provider_links_integration,
                "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
                side_effect=lambda *a: events.append("clear"),
            ),
        ]
        return client, events, state, patches

    def _refresh(self, service, patches):
        from contextlib import ExitStack

        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return service.refresh_idp_session(7, 3)

    def test_the_provider_is_called_with_no_session_open_and_the_new_tokens_are_committed(self):
        service = _service()
        open_during_call: list[int] = []
        client, events, state, patches = self._setup(
            service, fetch=lambda *a, **k: open_during_call.append(state["open"]) or {"access_token": "new"}
        )

        result = self._refresh(service, patches)

        assert result == {"access_token": "new"}
        assert open_during_call == [0]
        assert events == ["store", "commit"]
        client.close.assert_called_once()

    @pytest.mark.parametrize("status_code", [400, 401])
    def test_a_token_the_provider_rejects_is_cleared_and_committed(self, status_code):
        service = _service()
        response = MagicMock(status_code=status_code, text="invalid_grant")
        error = httpx2.HTTPStatusError("rejected", request=MagicMock(), response=response)

        def reject(*_a, **_k):
            raise error

        _, events, _, patches = self._setup(service, fetch=reject)

        assert self._refresh(service, patches) is None
        assert events == ["clear", "commit"]

    def test_a_provider_outage_keeps_the_token(self):
        service = _service()

        def time_out(*_a, **_k):
            raise httpx2.ReadTimeout("slow")

        _, events, _, patches = self._setup(service, fetch=time_out)

        assert self._refresh(service, patches) is None
        assert events == []

    def test_a_disabled_provider_is_refused(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {})
        patches[1] = patch.object(idp_service_module.idp_crud, "get_identity_provider", return_value=None)

        with pytest.raises(core_exceptions.NotFoundError):
            self._refresh(service, patches)


def test_service_clears_tokens_after_failed_remote_revocation(mock_db):
    service = IdentityProviderService(MagicMock(), "https://app.example", "test")
    service.revoke_idp_token = MagicMock(side_effect=RuntimeError("offline"))
    with (
        patch.object(
            idp_service_module.identity_provider_links_integration,
            "get_user_identity_providers_by_user_id",
            return_value=[MagicMock(idp_id=3)],
        ),
        patch.object(
            idp_service_module.identity_provider_links_integration,
            "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
        ) as clear,
    ):
        service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    service.revoke_idp_token.assert_called_once_with(7, 3, mock_db)
    clear.assert_called_once_with(7, 3, mock_db)
