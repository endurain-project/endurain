"""Tests for the storage, refresh and revocation of identity-provider tokens."""

from unittest.mock import MagicMock, patch

import httpx2
import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.token_service as token_service_module
from modules.auth.identity_providers.token_policy import TokenAction


def _service():
    return token_service_module.IdpTokenService(MagicMock())


class TestRequestIdpTokenRefresh:
    """The request clears what needs no network call and queues the rest; it never calls the provider."""

    def _request(self, mock_db, actions):
        service = _service()
        links = [MagicMock(idp_id=3 + index) for index in range(len(actions))]
        service.refresh_idp_session = MagicMock()
        with (
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=links,
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_user_identity_provider_refresh_token",
            ) as clear,
            patch.object(token_service_module.idp_event_publishers, "publish_idp_token_refresh_requested") as publish,
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", side_effect=actions),
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

        def refresh(user_id, idp_id, claims):
            open_during_refresh.append(open_sessions)
            if refresh_side_effect is not None:
                refresh_side_effect(idp_id)

        service.refresh_idp_session = MagicMock(side_effect=refresh)
        with (
            patch.object(token_service_module.core_database, "SessionLocal", _Session),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=links,
            ),
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", side_effect=actions),
        ):
            service.refresh_idp_tokens(7, self.claims)
        return service, open_during_refresh

    claims = MagicMock()

    def test_only_links_with_a_refresh_action_are_refreshed_with_no_session_open(self):
        service, open_during_refresh = self._run([TokenAction.SKIP, TokenAction.REFRESH, TokenAction.REFRESH])

        assert [call.args for call in service.refresh_idp_session.call_args_list] == [
            (7, 4, self.claims),
            (7, 5, self.claims),
        ]
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

        service._oidc.resolve_token_endpoint = MagicMock(return_value="https://idp.example/token")
        service._oidc.decrypt_client_id = MagicMock(return_value="cid")
        service._oidc.decrypt_client_secret = MagicMock(return_value="secret")
        service._oidc.create_oauth_client = MagicMock(return_value=client)
        service.store_idp_tokens = MagicMock(side_effect=lambda *a, **k: events.append("store"))
        patches = [
            patch.object(token_service_module.core_database, "SessionLocal", _Session),
            patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=idp),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_user_identity_provider_refresh_token_by_user_id_and_idp_id",
                return_value="encrypted",
            ),
            patch.object(token_service_module.core_cryptography, "decrypt_token_fernet", return_value="plain"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_user_identity_provider_refresh_token_if_unchanged",
                side_effect=lambda *a: events.append("clear") or True,
            ),
        ]
        return client, events, state, patches

    def _refresh(self, service, patches, claims=None):
        from contextlib import ExitStack

        self.claims = claims or MagicMock(**{"claim.return_value": True})
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return service.refresh_idp_session(7, 3, self.claims)

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
        # The new token is written only over the one this refresh read.
        assert service.store_idp_tokens.call_args.kwargs["expected_refresh_token"] == "encrypted"
        client.close.assert_called_once()
        self.claims.release.assert_called_once_with(7, 3)

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
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_rejection_clears_only_the_token_this_refresh_read(self):
        """A slower refresh's invalid_grant must not wipe the token a faster one just stored."""
        service = _service()
        response = MagicMock(status_code=400, text="invalid_grant")

        def reject(*_a, **_k):
            raise httpx2.HTTPStatusError("rejected", request=MagicMock(), response=response)

        _, _, _, patches = self._setup(service, fetch=reject)
        with patch.object(
            token_service_module.identity_provider_links_integration,
            "clear_user_identity_provider_refresh_token_if_unchanged",
            return_value=False,
        ) as clear:
            patches.pop()
            assert self._refresh(service, patches) is None

        assert clear.call_args.args[:3] == (7, 3, "encrypted")

    def test_a_refresh_another_worker_is_running_is_skipped(self):
        service = _service()
        client, events, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})

        assert self._refresh(service, patches, claims=MagicMock(**{"claim.return_value": False})) is None
        client.fetch_token.assert_not_called()
        assert events == []
        self.claims.release.assert_not_called()

    def test_the_claim_is_released_when_the_refresh_raises(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {})
        patches[1] = patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=None)

        with pytest.raises(core_exceptions.NotFoundError):
            self._refresh(service, patches)
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_provider_outage_keeps_the_token(self):
        service = _service()

        def time_out(*_a, **_k):
            raise httpx2.ReadTimeout("slow")

        _, events, _, patches = self._setup(service, fetch=time_out)

        assert self._refresh(service, patches) is None
        assert events == []
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_disabled_provider_is_refused(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {})
        patches[1] = patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=None)

        with pytest.raises(core_exceptions.NotFoundError):
            self._refresh(service, patches)


def test_service_clears_tokens_after_failed_remote_revocation(mock_db):
    service = _service()
    service.revoke_idp_token = MagicMock(side_effect=RuntimeError("offline"))
    with (
        patch.object(
            token_service_module.identity_provider_links_integration,
            "get_user_identity_providers_by_user_id",
            return_value=[MagicMock(idp_id=3)],
        ),
        patch.object(
            token_service_module.identity_provider_links_integration,
            "clear_user_identity_provider_refresh_token",
        ) as clear,
    ):
        service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    service.revoke_idp_token.assert_called_once_with(7, 3, mock_db)
    clear.assert_called_once_with(7, 3, mock_db)


class TestRevokeIdpToken:
    """The revocation call carries the client secret and the refresh token, so it must not reach internal hosts."""

    def _revoke(self, *, guard_error=None):
        from contextlib import ExitStack

        service = _service()
        idp = MagicMock(enabled=True, issuer_url="https://idp.example")
        idp.name = "Pocket ID"
        service._oidc.get_oidc_configuration = MagicMock(return_value={"revocation_endpoint": "http://10.0.0.5/revoke"})
        service._oidc.decrypt_client_id = MagicMock(return_value="cid")
        service._oidc.decrypt_client_secret = MagicMock(return_value="secret")
        http_client = MagicMock()
        http_client.post.return_value = MagicMock(status_code=200)
        service._oidc.http_client = MagicMock()
        service._oidc.http_client.return_value.__enter__.return_value = http_client
        with ExitStack() as stack:
            stack.enter_context(patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=idp))
            stack.enter_context(
                patch.object(
                    token_service_module.identity_provider_links_integration,
                    "get_user_identity_provider_refresh_token_by_user_id_and_idp_id",
                    return_value="encrypted",
                )
            )
            stack.enter_context(
                patch.object(token_service_module.core_cryptography, "decrypt_token_fernet", return_value="plain")
            )
            guard = stack.enter_context(
                patch.object(token_service_module.core_network, "reject_private_url", side_effect=guard_error)
            )
            result = service.revoke_idp_token(7, 3, MagicMock())
        return result, guard, http_client, service

    def test_a_public_endpoint_is_called_without_following_redirects(self):
        result, guard, http_client, service = self._revoke()

        assert result is True
        guard.assert_called_once_with("http://10.0.0.5/revoke", purpose="oidc_revocation")
        http_client.post.assert_called_once()
        service._oidc.http_client.assert_called_once_with()

    def test_an_internal_endpoint_is_never_called(self):
        result, _, http_client, _ = self._revoke(guard_error=core_exceptions.InvalidInputError("private address"))

        assert result is False
        http_client.post.assert_not_called()


class TestStoreIdpTokens:
    """The callbacks store unconditionally; a refresh stores only over the token it read."""

    def _store(self, expected=None):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration, "store_user_identity_provider_tokens"
            ) as store,
            patch.object(
                token_service_module.identity_provider_links_integration,
                "replace_user_identity_provider_tokens_if_unchanged",
                return_value=False,
            ) as replace,
        ):
            _service().store_idp_tokens(
                7, 3, {"refresh_token": "rt", "expires_in": 60}, MagicMock(), expected_refresh_token=expected
            )
        return store, replace

    def test_a_callback_store_is_unconditional(self):
        store, replace = self._store()

        assert store.call_args.kwargs["encrypted_refresh_token"] == "ciphertext"
        replace.assert_not_called()

    def test_a_refresh_store_is_conditional_on_the_token_read(self):
        store, replace = self._store(expected="read-ciphertext")

        store.assert_not_called()
        assert replace.call_args.args[:4] == (7, 3, "read-ciphertext", "ciphertext")
