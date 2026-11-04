"""Tests for the storage, refresh and revocation of identity-provider tokens."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from sqlalchemy.exc import OperationalError

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

    def test_a_failed_clear_propagates_so_the_caller_rolls_back(self, mock_db):
        service = _service()
        with (
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=[MagicMock(idp_id=3)],
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_user_identity_provider_refresh_token",
                side_effect=OperationalError("UPDATE", {}, Exception("db down")),
            ),
            patch.object(token_service_module.idp_event_publishers, "publish_idp_token_refresh_requested") as publish,
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", return_value=TokenAction.CLEAR),
            pytest.raises(OperationalError),
        ):
            service.request_idp_token_refresh(7, mock_db)
        publish.assert_not_called()


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

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.UpstreamError("token endpoint unresolved"),
            core_exceptions.ProcessingError("bad client secret"),
            OperationalError("SELECT", {}, Exception("db down")),
        ],
    )
    def test_the_errors_a_link_can_raise_do_not_stop_the_others(self, error):
        def fail_first(idp_id):
            if idp_id == 3:
                raise error

        service, _ = self._run([TokenAction.REFRESH, TokenAction.REFRESH], refresh_side_effect=fail_first)

        assert service.refresh_idp_session.call_count == 2

    def test_an_error_no_link_should_raise_is_not_hidden(self):
        def fail(_idp_id):
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError):
            self._run([TokenAction.REFRESH, TokenAction.REFRESH], refresh_side_effect=fail)


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

    def test_a_token_the_provider_revoked_is_cleared_and_committed(self, caplog):
        import logging

        from authlib.integrations.base_client import OAuthError

        service = _service()

        def reject(*_a, **_k):
            raise OAuthError("invalid_grant", "revoked")

        _, events, _, patches = self._setup(service, fetch=reject)

        with caplog.at_level(logging.DEBUG):
            assert self._refresh(service, patches) is None

        assert events == ["clear", "commit"]
        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_server_error_from_the_provider_keeps_the_token(self):
        service = _service()
        response = MagicMock(status_code=503, text="unavailable")

        def fail(*_a, **_k):
            raise httpx2.HTTPStatusError("unavailable", request=MagicMock(), response=response)

        _, events, _, patches = self._setup(service, fetch=fail)

        assert self._refresh(service, patches) is None
        assert events == []

    def test_a_rejection_clears_only_the_token_this_refresh_read(self):
        """A slower refresh's invalid_grant must not wipe the token a faster one just stored."""
        from authlib.integrations.base_client import OAuthError

        service = _service()

        def reject(*_a, **_k):
            raise OAuthError("invalid_grant", "revoked")

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

    def test_another_provider_error_response_keeps_the_token_with_a_warning(self, caplog):
        import logging

        from authlib.integrations.base_client import OAuthError

        service = _service()

        def refuse(*_a, **_k):
            raise OAuthError("invalid_client", "bad secret")

        _, events, _, patches = self._setup(service, fetch=refuse)

        with caplog.at_level(logging.DEBUG):
            assert self._refresh(service, patches) is None

        assert events == []
        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]
        assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)
        self.claims.release.assert_called_once_with(7, 3)

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("expires_in is not a number"),
            TypeError("expires_in is a list"),
            OverflowError("too far"),
            httpx2.InvalidURL("Invalid non-printable ASCII character in URL"),
        ],
    )
    def test_a_malformed_token_response_keeps_the_token_with_a_warning(self, caplog, error):
        import logging

        service = _service()

        def malformed(*_a, **_k):
            raise error

        _, events, _, patches = self._setup(service, fetch=malformed)

        with caplog.at_level(logging.DEBUG):
            assert self._refresh(service, patches) is None

        assert events == []
        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]
        self.claims.release.assert_called_once_with(7, 3)

    def test_an_unexpected_failure_propagates_and_keeps_the_token(self):
        service = _service()

        def explode(*_a, **_k):
            raise RuntimeError("bug")

        _, events, _, patches = self._setup(service, fetch=explode)

        with pytest.raises(RuntimeError, match="bug"):
            self._refresh(service, patches)

        assert events == []
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_key_that_cannot_be_loaded_keeps_the_token_and_propagates(self):
        """A missing or unreadable FERNET_KEY says nothing about the token, so the token is not cleared."""
        service = _service()
        client, events, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})
        patches[3] = patch.object(
            token_service_module.core_cryptography,
            "decrypt_token_fernet",
            side_effect=core_exceptions.CryptographyError(),
        )

        with pytest.raises(core_exceptions.CryptographyError) as exc_info:
            self._refresh(service, patches)

        assert not isinstance(exc_info.value, core_exceptions.UndecryptableError)
        assert events == []
        client.fetch_token.assert_not_called()
        self.claims.release.assert_called_once_with(7, 3)

    def test_a_token_the_key_cannot_decrypt_is_cleared(self):
        service = _service()
        client, events, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})
        patches[3] = patch.object(
            token_service_module.core_cryptography,
            "decrypt_token_fernet",
            side_effect=core_exceptions.UndecryptableError(),
        )

        assert self._refresh(service, patches) is None

        assert events == ["clear", "commit"]
        client.fetch_token.assert_not_called()

    def test_a_token_that_decrypts_to_nothing_is_cleared(self):
        service = _service()
        client, events, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})
        patches[3] = patch.object(token_service_module.core_cryptography, "decrypt_token_fernet", return_value="")

        assert self._refresh(service, patches) is None

        assert events == ["clear", "commit"]
        client.fetch_token.assert_not_called()

    def test_a_disabled_provider_is_refused(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {})
        patches[1] = patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=None)

        with pytest.raises(core_exceptions.NotFoundError):
            self._refresh(service, patches)


def test_service_clears_the_stored_token_of_every_link(mock_db):
    service = _service()
    with (
        patch.object(
            token_service_module.identity_provider_links_integration,
            "get_user_identity_providers_by_user_id",
            return_value=[MagicMock(idp_id=3), MagicMock(idp_id=4)],
        ),
        patch.object(
            token_service_module.identity_provider_links_integration,
            "clear_user_identity_provider_refresh_token",
        ) as clear,
    ):
        service.clear_all_idp_tokens(7, mock_db)
    assert [call.args for call in clear.call_args_list] == [(7, 3, mock_db), (7, 4, mock_db)]


def test_a_failed_clear_on_logout_propagates_so_the_caller_rolls_back(mock_db):
    service = _service()
    with (
        patch.object(
            token_service_module.identity_provider_links_integration,
            "get_user_identity_providers_by_user_id",
            return_value=[MagicMock(idp_id=3)],
        ),
        patch.object(
            token_service_module.identity_provider_links_integration,
            "clear_user_identity_provider_refresh_token",
            side_effect=OperationalError("UPDATE", {}, Exception("db down")),
        ),
        pytest.raises(OperationalError),
    ):
        service.clear_all_idp_tokens(7, mock_db)


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


class TestStoreIdpTokensExpiry:
    """The access-token expiry is read the way authlib accepts it, so no refresh token is silently dropped."""

    def _stored_expiry(self, token_response):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration, "store_user_identity_provider_tokens"
            ) as store,
        ):
            before = datetime.now(UTC)
            _service().store_idp_tokens(7, 3, token_response, MagicMock())
            after = datetime.now(UTC)
        store.assert_called_once()
        return store.call_args.kwargs["access_token_expires_at"], before, after

    def test_a_numeric_string_expires_in_is_stored(self):
        expires_at, before, after = self._stored_expiry({"refresh_token": "rt", "expires_in": "300"})

        assert before + timedelta(seconds=300) <= expires_at <= after + timedelta(seconds=300)

    @pytest.mark.parametrize("token_response", [{"refresh_token": "rt"}, {"refresh_token": "rt", "expires_in": None}])
    def test_an_absent_or_null_expires_in_uses_the_default(self, token_response):
        expires_at, before, after = self._stored_expiry(token_response)

        default = timedelta(seconds=token_service_module.DEFAULT_TOKEN_EXPIRY_SECONDS)
        assert before + default <= expires_at <= after + default

    def test_a_non_numeric_expires_in_is_not_swallowed(self):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration, "store_user_identity_provider_tokens"
            ) as store,
            pytest.raises(ValueError),
        ):
            _service().store_idp_tokens(7, 3, {"refresh_token": "rt", "expires_in": "soon"}, MagicMock())
        store.assert_not_called()


class TestStoreIdpTokensFailures:
    """Only a failed encryption degrades; a database error reaches the caller, whose transaction it spoils."""

    @pytest.mark.parametrize("expected", [None, "read-ciphertext"])
    def test_a_database_error_propagates(self, expected):
        error = OperationalError("UPDATE", {}, Exception("db down"))
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "store_user_identity_provider_tokens",
                side_effect=error,
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "replace_user_identity_provider_tokens_if_unchanged",
                side_effect=error,
            ),
            pytest.raises(OperationalError),
        ):
            _service().store_idp_tokens(
                7, 3, {"refresh_token": "rt", "expires_in": 60}, MagicMock(), expected_refresh_token=expected
            )

    def test_a_failed_encryption_is_logged_and_login_continues(self, caplog):
        import logging

        with (
            patch.object(
                token_service_module.core_cryptography,
                "encrypt_token_fernet",
                side_effect=core_exceptions.CryptographyError(),
            ),
            patch.object(
                token_service_module.identity_provider_links_integration, "store_user_identity_provider_tokens"
            ) as store,
            caplog.at_level(logging.DEBUG),
        ):
            _service().store_idp_tokens(7, 3, {"refresh_token": "rt", "expires_in": 60}, MagicMock())

        store.assert_not_called()
        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.ERROR]
