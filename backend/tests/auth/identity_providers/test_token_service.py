"""Tests for the storage and refresh of the identity-provider token of a session."""

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx2
import jasil.testing as jasil_testing
import pytest
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.token_service as token_service_module
import modules.auth.sessions.audit_actions as sessions_audit_actions
from modules.auth.identity_providers.token_policy import TokenAction
from tests._helpers.auth import MOCK_USER_ID

IDP_ID = uuid.uuid4()


def _service():
    return token_service_module.IdpTokenService(MagicMock())


SESSION = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _row(**overrides):
    values = {"session_id": SESSION, "user_id": MOCK_USER_ID, "idp_id": IDP_ID, "refresh_token": "encrypted"}
    values.update(overrides)
    return MagicMock(**values)


class TestRequestIdpTokenRefresh:
    """The request clears what needs no network call and queues the rest; it never calls the provider."""

    def _request(self, mock_db, action, row="default"):
        service = _service()
        row = _row() if row == "default" else row
        service.refresh_idp_session = MagicMock()
        with (
            patch.object(
                token_service_module.identity_provider_links_integration, "get_idp_session_token", return_value=row
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_idp_session_refresh_token_if_unchanged",
            ) as clear,
            patch.object(token_service_module.idp_event_publishers, "publish_idp_token_refresh_requested") as publish,
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", return_value=action),
        ):
            service.request_idp_token_refresh(MOCK_USER_ID, SESSION, mock_db)
        return service, clear, publish

    def test_an_expiring_token_queues_one_job_for_that_session(self, mock_db):
        service, clear, publish = self._request(mock_db, TokenAction.REFRESH)

        publish.assert_called_once_with(MOCK_USER_ID, SESSION, mock_db)
        clear.assert_not_called()
        service.refresh_idp_session.assert_not_called()

    def test_a_token_policy_retires_is_cleared_now(self, mock_db):
        _, clear, publish = self._request(mock_db, TokenAction.CLEAR)

        publish.assert_not_called()
        clear.assert_called_once_with(SESSION, "encrypted", mock_db)

    def test_a_valid_token_queues_nothing(self, mock_db):
        _, clear, publish = self._request(mock_db, TokenAction.SKIP)

        publish.assert_not_called()
        clear.assert_not_called()

    @pytest.mark.parametrize("row", [None, _row(refresh_token=None)])
    def test_a_session_without_a_token_is_left_alone(self, mock_db, row):
        with patch.object(token_service_module.token_policy, "should_refresh_idp_token") as policy:
            _, clear, publish = self._request(mock_db, TokenAction.REFRESH, row=row)

        policy.assert_not_called()
        publish.assert_not_called()
        clear.assert_not_called()

    def test_a_failed_clear_propagates_so_the_caller_rolls_back(self, mock_db):
        service = _service()
        with (
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_idp_session_token",
                return_value=_row(),
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_idp_session_refresh_token_if_unchanged",
                side_effect=OperationalError("UPDATE", {}, Exception("db down")),
            ),
            patch.object(token_service_module.idp_event_publishers, "publish_idp_token_refresh_requested") as publish,
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", return_value=TokenAction.CLEAR),
            pytest.raises(OperationalError),
        ):
            service.request_idp_token_refresh(MOCK_USER_ID, SESSION, mock_db)
        publish.assert_not_called()


class TestRefreshIdpTokens:
    """The job reads the session's sign-in in a short session and refreshes it outside any session."""

    def _run(self, action, row="default", refresh_side_effect=None):
        service = _service()
        row = _row() if row == "default" else row
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

        def refresh(session_id, claims):
            open_during_refresh.append(open_sessions)
            if refresh_side_effect is not None:
                refresh_side_effect()

        service.refresh_idp_session = MagicMock(side_effect=refresh)
        with (
            patch.object(token_service_module.core_database, "SessionLocal", _Session),
            patch.object(
                token_service_module.identity_provider_links_integration, "get_idp_session_token", return_value=row
            ),
            patch.object(token_service_module.token_policy, "should_refresh_idp_token", return_value=action),
        ):
            service.refresh_idp_tokens(MOCK_USER_ID, SESSION, self.claims)
        return service, open_during_refresh

    claims = MagicMock()

    def test_an_expiring_token_is_refreshed_with_no_session_open(self):
        service, open_during_refresh = self._run(TokenAction.REFRESH)

        service.refresh_idp_session.assert_called_once_with(SESSION, self.claims)
        assert open_during_refresh == [0]

    @pytest.mark.parametrize("action", [TokenAction.SKIP, TokenAction.CLEAR])
    def test_a_token_that_is_not_expiring_is_not_refreshed(self, action):
        service, _ = self._run(action)

        service.refresh_idp_session.assert_not_called()

    def test_a_session_without_a_sign_in_is_not_refreshed(self):
        service, _ = self._run(TokenAction.REFRESH, row=None)

        service.refresh_idp_session.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.NotFoundError("disabled"),
            core_exceptions.UpstreamError("token endpoint unresolved"),
            core_exceptions.ProcessingError("bad client secret"),
            OperationalError("SELECT", {}, Exception("db down")),
        ],
    )
    def test_the_errors_a_refresh_can_raise_are_logged(self, error):
        def fail():
            raise error

        service, _ = self._run(TokenAction.REFRESH, refresh_side_effect=fail)

        service.refresh_idp_session.assert_called_once()

    def test_an_error_no_refresh_should_raise_is_not_hidden(self):
        def fail():
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError):
            self._run(TokenAction.REFRESH, refresh_side_effect=fail)


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
        service._store_refreshed_token = MagicMock(side_effect=lambda *a, **k: events.append("store"))
        patches = [
            patch.object(token_service_module.core_database, "SessionLocal", _Session),
            patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=idp),
            patch.object(
                token_service_module.identity_provider_links_integration, "get_idp_session_token", return_value=_row()
            ),
            patch.object(token_service_module.core_cryptography, "decrypt_token_fernet", return_value="plain"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "clear_idp_session_refresh_token_if_unchanged",
                side_effect=lambda *a: events.append("clear") or True,
            ),
            patch.object(
                token_service_module.sessions_integration,
                "delete_session",
                side_effect=lambda *a: events.append("end-session"),
            ),
        ]
        return client, events, state, patches

    def _refresh(self, service, patches, claims=None):
        self.claims = claims or MagicMock(**{"claim.return_value": True})
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return service.refresh_idp_session(SESSION, self.claims)

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
        # The new token is written only over the one this refresh read, for this session.
        store_args = service._store_refreshed_token.call_args.args
        assert store_args[:5] == (SESSION, MOCK_USER_ID, IDP_ID, {"access_token": "new"}, "encrypted")
        client.close.assert_called_once()
        self.claims.claim.assert_called_once_with(SESSION)
        self.claims.release.assert_called_once_with(SESSION)

    def _refresh_with_id_token(self, *, verify, link="default", config="default"):
        """Refresh a session whose response carries an ID token, with the verification as given."""
        service = _service()
        response = {"access_token": "new", "id_token": "idt"}
        _, events, _, patches = self._setup(service, fetch=lambda *a, **k: response)
        link = SimpleNamespace(idp_subject="sub-1") if link == "default" else link
        service._oidc.get_oidc_configuration = MagicMock(
            return_value={"jwks_uri": "https://idp.example/jwks", "issuer": "https://idp.example"}
            if config == "default"
            else config
        )
        patches += [
            patch.object(
                token_service_module.identity_provider_links_integration,
                "get_user_identity_provider_by_user_id_and_idp_id",
                return_value=link,
            ),
            patch.object(token_service_module.id_token_service, "verify_id_token", verify),
        ]
        result = self._refresh(service, patches)
        return service, result, events

    def test_the_id_token_of_a_refresh_is_verified_like_a_login_without_a_nonce_and_stored(self):
        verify = MagicMock(return_value={"sub": "sub-1"})

        service, result, _ = self._refresh_with_id_token(verify=verify)

        assert result == {"access_token": "new", "id_token": "idt"}
        verify.assert_called_once_with(
            service._oidc.fetch_jwks,
            "idt",
            "https://idp.example/jwks",
            "https://idp.example",
            "cid",
            access_token="new",
        )
        assert service._store_refreshed_token.call_args.args[3] == {"access_token": "new", "id_token": "idt"}

    def test_an_id_token_that_fails_verification_is_not_stored_and_the_refresh_goes_on(self, caplog):
        verify = MagicMock(side_effect=core_exceptions.UnauthenticatedError("ID token signature is invalid"))

        service, result, events = self._refresh_with_id_token(verify=verify)

        assert result == {"access_token": "new"}
        assert service._store_refreshed_token.call_args.args[3] == {"access_token": "new"}
        assert events == ["store", "commit"]

    def test_an_id_token_of_another_subject_is_not_stored(self):
        verify = MagicMock(return_value={"sub": "someone-else"})

        service, result, _ = self._refresh_with_id_token(verify=verify)

        assert "id_token" not in result
        assert "id_token" not in service._store_refreshed_token.call_args.args[3]

    def test_an_id_token_is_not_stored_when_the_account_is_no_longer_linked(self):
        _, result, _ = self._refresh_with_id_token(verify=MagicMock(return_value={"sub": "sub-1"}), link=None)

        assert "id_token" not in result

    def test_an_id_token_is_not_stored_when_the_provider_publishes_no_signing_keys(self):
        verify = MagicMock()

        _, result, _ = self._refresh_with_id_token(verify=verify, config={})

        verify.assert_not_called()
        assert "id_token" not in result

    def test_an_id_token_that_is_not_a_string_is_not_stored(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new", "id_token": 7})

        assert self._refresh(service, patches) == {"access_token": "new"}

    def test_a_token_the_provider_revoked_ends_that_session_and_audits_it(self, caplog):
        import logging

        from authlib.integrations.base_client import OAuthError

        service = _service()

        def reject(*_a, **_k):
            raise OAuthError("invalid_grant", "revoked")

        _, events, _, patches = self._setup(service, fetch=reject)

        with jasil_testing.capture_audit() as audit, caplog.at_level(logging.DEBUG):
            assert self._refresh(service, patches) is None

        assert events == ["clear", "commit", "end-session", "commit"]
        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="session",
            target_id=str(SESSION),
            target_owner_id=str(MOCK_USER_ID),
        )
        assert entry.details == {"sessions_revoked": 1}
        assert [record.levelno for record in caplog.records if record.levelno == logging.WARNING] == [logging.WARNING]
        self.claims.release.assert_called_once_with(SESSION)

    def test_a_rejected_session_that_already_ended_is_not_audited_again(self):
        from authlib.integrations.base_client import OAuthError

        service = _service()

        def reject(*_a, **_k):
            raise OAuthError("invalid_grant", "revoked")

        _, _, _, patches = self._setup(service, fetch=reject)
        patches[5] = patch.object(
            token_service_module.sessions_integration,
            "delete_session",
            side_effect=core_exceptions.NotFoundError("Session not found"),
        )

        with jasil_testing.capture_audit() as audit:
            assert self._refresh(service, patches) is None

        audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)

    def test_a_server_error_from_the_provider_keeps_the_token_and_the_session(self):
        service = _service()
        response = MagicMock(status_code=503, text="unavailable")

        def fail(*_a, **_k):
            raise httpx2.HTTPStatusError("unavailable", request=MagicMock(), response=response)

        _, events, _, patches = self._setup(service, fetch=fail)

        assert self._refresh(service, patches) is None
        assert events == []

    def test_a_rejection_after_another_refresh_stored_a_token_keeps_the_session(self):
        """A slower refresh's invalid_grant must neither wipe the token a faster one stored nor end the session."""
        from authlib.integrations.base_client import OAuthError

        service = _service()

        def reject(*_a, **_k):
            raise OAuthError("invalid_grant", "revoked")

        _, events, _, patches = self._setup(service, fetch=reject)
        with patch.object(
            token_service_module.identity_provider_links_integration,
            "clear_idp_session_refresh_token_if_unchanged",
            return_value=False,
        ) as clear:
            patches.pop(4)
            assert self._refresh(service, patches) is None

        assert clear.call_args.args[:2] == (SESSION, "encrypted")
        assert "end-session" not in events

    def test_a_refresh_another_worker_is_running_is_skipped(self):
        service = _service()
        client, events, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})

        assert self._refresh(service, patches, claims=MagicMock(**{"claim.return_value": False})) is None
        client.fetch_token.assert_not_called()
        assert events == []
        self.claims.release.assert_not_called()

    def test_a_session_that_signed_in_through_no_provider_is_not_refreshed(self):
        service = _service()
        client, _, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})
        patches[2] = patch.object(
            token_service_module.identity_provider_links_integration, "get_idp_session_token", return_value=None
        )

        assert self._refresh(service, patches) is None
        client.fetch_token.assert_not_called()
        self.claims.release.assert_called_once_with(SESSION)

    def test_a_session_without_a_stored_token_is_not_refreshed(self):
        service = _service()
        client, _, _, patches = self._setup(service, fetch=lambda *a, **k: {"access_token": "new"})
        patches[2] = patch.object(
            token_service_module.identity_provider_links_integration,
            "get_idp_session_token",
            return_value=_row(refresh_token=None),
        )

        assert self._refresh(service, patches) is None
        client.fetch_token.assert_not_called()

    def test_the_claim_is_released_when_the_refresh_raises(self):
        service = _service()
        _, _, _, patches = self._setup(service, fetch=lambda *a, **k: {})
        patches[1] = patch.object(token_service_module.idp_crud, "get_identity_provider", return_value=None)

        with pytest.raises(core_exceptions.NotFoundError):
            self._refresh(service, patches)
        self.claims.release.assert_called_once_with(SESSION)

    def test_a_provider_outage_keeps_the_token(self):
        service = _service()

        def time_out(*_a, **_k):
            raise httpx2.ReadTimeout("slow")

        _, events, _, patches = self._setup(service, fetch=time_out)

        assert self._refresh(service, patches) is None
        assert events == []
        self.claims.release.assert_called_once_with(SESSION)

    def test_a_network_error_keeps_the_token(self):
        service = _service()

        def refuse(*_a, **_k):
            raise httpx2.ConnectError("down")

        _, events, _, patches = self._setup(service, fetch=refuse)

        assert self._refresh(service, patches) is None
        assert events == []

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
        self.claims.release.assert_called_once_with(SESSION)

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
        self.claims.release.assert_called_once_with(SESSION)

    def test_an_unexpected_failure_propagates_and_keeps_the_token(self):
        service = _service()

        def explode(*_a, **_k):
            raise RuntimeError("bug")

        _, events, _, patches = self._setup(service, fetch=explode)

        with pytest.raises(RuntimeError, match="bug"):
            self._refresh(service, patches)

        assert events == []
        self.claims.release.assert_called_once_with(SESSION)

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
        self.claims.release.assert_called_once_with(SESSION)

    def test_a_token_the_key_cannot_decrypt_is_cleared_and_the_session_lives_on(self):
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

    def test_a_token_that_decrypts_to_nothing_is_cleared_and_the_session_lives_on(self):
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


class TestStoreSessionTokens:
    """A sign-in stores a row tied to its session, with a token when the provider issued one."""

    def _store(self, token_response, *, encrypt=None):
        with (
            patch.object(
                token_service_module.core_cryptography,
                "encrypt_token_fernet",
                **({"side_effect": encrypt} if encrypt else {"return_value": "ciphertext"}),
            ),
            patch.object(
                token_service_module.identity_provider_links_integration, "create_idp_session_token"
            ) as create,
        ):
            before = datetime.now(UTC)
            _service().store_session_tokens(SESSION, MOCK_USER_ID, IDP_ID, token_response, MagicMock(), idp_sid=None)
            after = datetime.now(UTC)
        return create, before, after

    def test_a_refresh_token_is_stored_encrypted_with_its_expiry(self):
        create, before, after = self._store({"refresh_token": "rt", "expires_in": 60})

        args = create.call_args.args
        assert args[:4] == (SESSION, MOCK_USER_ID, IDP_ID, "ciphertext")
        assert before + timedelta(seconds=60) <= args[4] <= after + timedelta(seconds=60)

    def test_a_provider_that_issues_no_refresh_token_still_records_the_sign_in(self):
        create, _, _ = self._store({"access_token": "at"})

        assert create.call_args.args[:5] == (SESSION, MOCK_USER_ID, IDP_ID, None, None)

    def test_a_failed_encryption_is_logged_and_the_sign_in_is_recorded_without_a_token(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG):
            create, _, _ = self._store(
                {"refresh_token": "rt", "expires_in": 60}, encrypt=core_exceptions.CryptographyError()
            )

        assert create.call_args.args[:5] == (SESSION, MOCK_USER_ID, IDP_ID, None, None)
        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.ERROR]

    def test_the_id_token_is_stored_encrypted_beside_the_refresh_token(self):
        with (
            patch.object(
                token_service_module.core_cryptography, "encrypt_token_fernet", side_effect=lambda value: f"enc:{value}"
            ),
            patch.object(
                token_service_module.identity_provider_links_integration, "create_idp_session_token"
            ) as create,
        ):
            _service().store_session_tokens(
                SESSION, MOCK_USER_ID, IDP_ID, {"refresh_token": "rt", "id_token": "idt"}, MagicMock(), idp_sid=None
            )

        assert create.call_args.args[3] == "enc:rt"
        assert create.call_args.kwargs == {"encrypted_id_token": "enc:idt", "idp_sid": None}

    def test_an_id_token_is_stored_even_when_the_provider_issued_no_refresh_token(self):
        with (
            patch.object(
                token_service_module.core_cryptography, "encrypt_token_fernet", side_effect=lambda value: f"enc:{value}"
            ),
            patch.object(
                token_service_module.identity_provider_links_integration, "create_idp_session_token"
            ) as create,
        ):
            _service().store_session_tokens(
                SESSION, MOCK_USER_ID, IDP_ID, {"id_token": "idt"}, MagicMock(), idp_sid=None
            )

        assert create.call_args.args[3] is None
        assert create.call_args.kwargs == {"encrypted_id_token": "enc:idt", "idp_sid": None}

    def test_the_provider_session_id_is_stored_with_the_sign_in(self):
        with patch.object(
            token_service_module.identity_provider_links_integration, "create_idp_session_token"
        ) as create:
            _service().store_session_tokens(
                SESSION, MOCK_USER_ID, IDP_ID, {"access_token": "at"}, MagicMock(), idp_sid="sid-1"
            )

        assert create.call_args.kwargs["idp_sid"] == "sid-1"

    def test_a_response_without_an_id_token_stores_none(self):
        create, _, _ = self._store({"refresh_token": "rt"})

        assert create.call_args.kwargs == {"encrypted_id_token": None, "idp_sid": None}

    def test_an_id_token_that_cannot_be_encrypted_is_dropped_without_its_value_in_the_log(self, caplog):
        import logging

        def encrypt(value):
            if value == "idt-secret":
                raise core_exceptions.CryptographyError()
            return "ciphertext"

        with caplog.at_level(logging.DEBUG):
            create, _, _ = self._store({"refresh_token": "rt", "id_token": "idt-secret"}, encrypt=encrypt)

        assert create.call_args.args[3] == "ciphertext"
        assert create.call_args.kwargs == {"encrypted_id_token": None, "idp_sid": None}
        assert "idt-secret" not in caplog.text

    def test_a_numeric_string_expires_in_is_stored(self):
        create, before, after = self._store({"refresh_token": "rt", "expires_in": "300"})

        assert before + timedelta(seconds=300) <= create.call_args.args[4] <= after + timedelta(seconds=300)

    @pytest.mark.parametrize("token_response", [{"refresh_token": "rt"}, {"refresh_token": "rt", "expires_in": None}])
    def test_an_absent_or_null_expires_in_uses_the_default(self, token_response):
        create, before, after = self._store(token_response)

        default = timedelta(seconds=token_service_module.DEFAULT_TOKEN_EXPIRY_SECONDS)
        assert before + default <= create.call_args.args[4] <= after + default

    def test_a_non_numeric_expires_in_is_not_swallowed(self):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration, "create_idp_session_token"
            ) as create,
            pytest.raises(ValueError),
        ):
            _service().store_session_tokens(
                SESSION, MOCK_USER_ID, IDP_ID, {"refresh_token": "rt", "expires_in": "soon"}, MagicMock(), idp_sid=None
            )
        create.assert_not_called()

    def test_a_database_error_propagates(self):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "create_idp_session_token",
                side_effect=OperationalError("INSERT", {}, Exception("db down")),
            ),
            pytest.raises(OperationalError),
        ):
            _service().store_session_tokens(
                SESSION, MOCK_USER_ID, IDP_ID, {"refresh_token": "rt"}, MagicMock(), idp_sid=None
            )


class TestStoreRefreshedToken:
    """A refresh stores only over the token it read, and only when the provider returned a new one."""

    def _store(self, token_response, *, replaced=True):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "replace_idp_session_token_if_unchanged",
                return_value=replaced,
            ) as replace,
        ):
            _service()._store_refreshed_token(
                SESSION, MOCK_USER_ID, IDP_ID, token_response, "read-ciphertext", MagicMock()
            )
        return replace

    def test_the_new_token_replaces_the_one_that_was_read(self):
        replace = self._store({"refresh_token": "rt", "expires_in": 60})

        assert replace.call_args.args[:4] == (SESSION, "read-ciphertext", "ciphertext", replace.call_args.args[3])
        assert replace.call_args.args[3] > datetime.now(UTC)

    def test_the_new_id_token_replaces_the_stored_one(self):
        with (
            patch.object(
                token_service_module.core_cryptography, "encrypt_token_fernet", side_effect=lambda value: f"enc:{value}"
            ),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "replace_idp_session_token_if_unchanged",
                return_value=True,
            ) as replace,
        ):
            _service()._store_refreshed_token(
                SESSION,
                MOCK_USER_ID,
                IDP_ID,
                {"refresh_token": "rt", "id_token": "idt"},
                "read-ciphertext",
                MagicMock(),
            )

        assert replace.call_args.kwargs == {"encrypted_id_token": "enc:idt"}

    def test_a_refresh_without_an_id_token_leaves_the_stored_one(self):
        replace = self._store({"refresh_token": "rt"})

        assert replace.call_args.kwargs == {"encrypted_id_token": None}

    def test_a_response_without_a_refresh_token_stores_nothing(self):
        replace = self._store({"access_token": "at"})

        replace.assert_not_called()

    def test_a_token_another_refresh_stored_is_kept(self):
        replace = self._store({"refresh_token": "rt"}, replaced=False)

        replace.assert_called_once()

    def test_a_database_error_propagates(self):
        with (
            patch.object(token_service_module.core_cryptography, "encrypt_token_fernet", return_value="ciphertext"),
            patch.object(
                token_service_module.identity_provider_links_integration,
                "replace_idp_session_token_if_unchanged",
                side_effect=OperationalError("UPDATE", {}, Exception("db down")),
            ),
            pytest.raises(OperationalError),
        ):
            _service()._store_refreshed_token(
                SESSION, MOCK_USER_ID, IDP_ID, {"refresh_token": "rt"}, "read", MagicMock()
            )
