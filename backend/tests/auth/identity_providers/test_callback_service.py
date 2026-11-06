"""The end of an SSO flow: accepting the provider callback, matching the user and creating the session."""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.oauth_state.constants as oauth_state_constants

_LOGIN = oauth_state_constants.OAuthStatePurpose.LOGIN
_LINK = oauth_state_constants.OAuthStatePurpose.LINK

HOST = "https://app.example.com"
AUD = "client-id-123"


@pytest.fixture
def service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), HOST)


def _idp(enabled=True, **overrides):
    values = {"id": 1, "slug": "test", "name": "Test", "enabled": enabled}
    values.update(overrides)
    return SimpleNamespace(**values)


def _oauth_state(**overrides):
    values = {"idp_id": 1, "client_type": "web", "user_id": None, "browser_binding_hash": None, "purpose": _LOGIN}
    values.update(overrides)
    return SimpleNamespace(**values)


class TestPrepareCallback:
    def _prepare(self, service, *, idp, oauth_state, claimed=True, browser_binding=None):
        self.claim = MagicMock(return_value=claimed)
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            patch.object(service, "claim_oauth_state", self.claim),
        ):
            return service.prepare_callback("test", "state-id", browser_binding, MagicMock())

    def test_an_unknown_or_disabled_provider_is_not_found(self, service):
        for idp in (None, _idp(enabled=False)):
            with pytest.raises(core_exceptions.NotFoundError):
                self._prepare(service, idp=idp, oauth_state=_oauth_state())

    def test_an_unknown_state_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(), oauth_state=None)

    def test_a_state_issued_for_another_provider_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(id=1), oauth_state=_oauth_state(idp_id=2))

    def test_a_replayed_state_is_refused_with_the_same_message(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(), oauth_state=_oauth_state(), claimed=False)

    def test_a_good_state_is_claimed_and_returned_with_its_provider(self, service):
        idp, oauth_state = _idp(), _oauth_state()

        assert self._prepare(service, idp=idp, oauth_state=oauth_state) == (idp, oauth_state)

    def test_a_link_finishes_in_the_browser_that_started_it(self, service):
        idp = _idp()
        oauth_state = _oauth_state(user_id=7, purpose=_LINK, browser_binding_hash=core_hashing.sha256_hex("binding"))

        assert self._prepare(service, idp=idp, oauth_state=oauth_state, browser_binding="binding") == (idp, oauth_state)

    @pytest.mark.parametrize("browser_binding", [None, "", "another-browser"])
    def test_a_link_from_another_browser_is_refused_before_the_state_is_claimed(self, service, browser_binding):
        """The attacker's own link URL, opened by a victim, must not bind the victim's IdP account to it."""
        oauth_state = _oauth_state(user_id=7, purpose=_LINK, browser_binding_hash=core_hashing.sha256_hex("binding"))

        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(), oauth_state=oauth_state, browser_binding=browser_binding)
        self.claim.assert_not_called()

    def test_a_link_state_without_a_binding_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(
                service, idp=_idp(), oauth_state=_oauth_state(user_id=7, purpose=_LINK), browser_binding="binding"
            )

    def test_a_login_needs_no_binding(self, service):
        """A login is bound to its client by PKCE at the token exchange instead."""
        idp, oauth_state = _idp(), _oauth_state()

        assert self._prepare(service, idp=idp, oauth_state=oauth_state) == (idp, oauth_state)


def _login(redirect_path=None):
    return callback_service.CallbackResult(
        user=SimpleNamespace(username="a"), userinfo={}, mode="login", redirect_path=redirect_path
    )


class TestCompleteCallback:
    def _complete(self, service, result, oauth_state, *, session_id="session-1", error=None):
        with (
            patch.object(service, "handle_callback", side_effect=error, return_value=result),
            patch.object(service, "create_callback_session", return_value=session_id) as create_session,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state", oauth_state, "10.0.0.1", "agent", MagicMock(), MagicMock()
            )
        return url, create_session

    def _state(self, **overrides):
        values = {"id": "state-id", "redirect_path": None, "user_id": None, "purpose": _LOGIN}
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_a_link_returns_to_the_originating_page_without_a_session(self, service):
        user = SimpleNamespace(username="alice")

        url, create_session = self._complete(
            service,
            callback_service.CallbackResult(user=user, userinfo={}, mode="link"),
            self._state(redirect_path="/settings/security", user_id=7, purpose=_LINK),
        )

        assert url == f"{HOST}/settings/security?idp_link=success&idp_name=Test"
        create_session.assert_not_called()

    def test_a_login_returns_the_session_id_for_the_token_exchange(self, service):
        url, _ = self._complete(service, _login(), self._state())

        assert url == f"{HOST}/login?sso=success&session_id=session-1"

    def test_a_login_passes_the_provider_and_its_tokens_to_the_session(self, service):
        result = callback_service.CallbackResult(
            user=SimpleNamespace(username="a"), userinfo={}, mode="login", token_response={"refresh_token": "rt"}
        )

        state = self._state()
        _, create_session = self._complete(service, result, state)

        assert create_session.call_args.args[5:7] == (1, {"refresh_token": "rt"})
        assert create_session.call_args.args[4] is state

    def test_a_login_carries_a_relative_return_path(self, service):
        url, _ = self._complete(service, _login(redirect_path="/activities?x=1"), self._state())

        assert url.endswith("&redirect=/activities%3Fx%3D1")
        assert "external_redirect" not in url

    def test_a_custom_scheme_return_path_is_flagged_for_the_native_client(self, service):
        url, _ = self._complete(
            service,
            _login(redirect_path="gadgetbridge://done"),
            self._state(),
        )

        assert url.endswith("&external_redirect=true")

    def test_the_session_id_is_not_logged_in_the_clear(self, service, caplog):
        with caplog.at_level(logging.DEBUG):
            self._complete(service, _login(), self._state(), session_id="secret-session")

        assert "secret-session" not in caplog.text

    def test_a_refused_sign_in_returns_to_the_login_page_with_its_reason(self, service, caplog):
        refusal = callback_service.user_provisioning_service.SsoSignInRefusedError(
            "The identity provider did not share an email address", login_error="sso_email_missing"
        )

        with caplog.at_level(logging.WARNING, logger=callback_service.logger.name):
            url, _ = self._complete(service, None, self._state(), error=refusal)

        assert url == f"{HOST}/login?error=sso_email_missing"
        # An identity provider's configuration problem, not a failure of this server.
        assert [record.levelno for record in caplog.records] == [logging.WARNING]

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.UpstreamError("down"),
            core_exceptions.NotFoundError("User not found"),
            core_exceptions.ConflictError("already linked"),
            core_exceptions.UnauthenticatedError("ID token names no subject"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_an_expected_refusal_is_a_warning_without_a_traceback(self, service, caplog, error):
        with caplog.at_level(logging.DEBUG, logger=callback_service.logger.name):
            url, _ = self._complete(service, None, self._state(), error=error)

        assert url == f"{HOST}/login?error=sso_failed"
        assert [record.levelno for record in caplog.records] == [logging.WARNING]
        assert caplog.records[0].exc_info is None

    @pytest.mark.parametrize(
        "error",
        [core_exceptions.ProcessingError("internal"), RuntimeError("boom")],
        ids=lambda error: type(error).__name__,
    )
    def test_an_internal_failure_is_an_error_with_a_traceback(self, service, caplog, error):
        with caplog.at_level(logging.DEBUG, logger=callback_service.logger.name):
            self._complete(service, None, self._state(), error=error)

        assert [record.levelno for record in caplog.records] == [logging.ERROR]
        assert caplog.records[0].exc_info is not None

    def test_a_failed_login_returns_to_the_login_page_with_an_error(self, service):
        url, _ = self._complete(service, None, self._state(), error=core_exceptions.UpstreamError("down"))

        assert url == f"{HOST}/login?error=sso_failed"

    def test_a_failed_link_returns_to_the_originating_page_with_an_error(self, service):
        url, _ = self._complete(
            service,
            None,
            self._state(redirect_path="/settings/security", user_id=7, purpose=_LINK),
            error=RuntimeError("boom"),
        )

        assert url == f"{HOST}/settings/security?idp_link=error"


class TestHandleCallback:
    """The callback fetches userinfo after a successful token exchange."""

    def test_login_mode_returns_userinfo_from_token_exchange(self, service):
        idp = MagicMock(
            issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp", provider_type="oauth2"
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        token_response = {"access_token": "at"}
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = token_response
        user = MagicMock(id=1, username="alice")
        userinfo = {"sub": "user-1", "email": "a@example.com"}

        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value=userinfo) as get_userinfo,
            patch.object(callback_service.user_provisioning_service, "find_or_create_user", return_value=user),
        ):
            result = service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        get_userinfo.assert_called_once()
        assert result.userinfo == userinfo
        assert result.user is user
        assert oauth_client.fetch_token.call_args.kwargs["code_verifier"] is oauth_state.idp_code_verifier

    def test_login_mode_hands_the_token_response_back_for_the_session_and_stores_nothing(self, service):
        idp = MagicMock(
            issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp", provider_type="oauth2"
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at", "refresh_token": "rt"}
        user = MagicMock(id=1, username="alice", active=True)
        db = MagicMock()

        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "user-1"}),
            patch.object(callback_service.user_provisioning_service, "find_or_create_user", return_value=user),
        ):
            result = service.handle_callback(idp, "code", "state", oauth_state, db)

        assert result.token_response == {"access_token": "at", "refresh_token": "rt"}
        service._tokens.store_session_tokens.assert_not_called()
        db.commit.assert_called_once()

    def test_link_mode_stores_no_token_because_it_creates_no_session(self, service):
        idp = MagicMock(
            id=3,
            issuer_url=None,
            userinfo_endpoint="https://idp.example.com/userinfo",
            slug="idp",
            sync_user_info=False,
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=7, purpose=_LINK, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at", "refresh_token": "rt"}
        user = MagicMock(id=7, username="alice")
        db = MagicMock()

        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "user-1"}),
            patch.object(callback_service.users_integration, "get_user", return_value=user),
            patch.object(
                callback_service.identity_provider_links_integration,
                "get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch.object(callback_service.identity_provider_links_integration, "create_user_identity_provider"),
            patch.object(callback_service.user_provisioning_service, "stage_identity_link"),
            patch.object(callback_service.idp_event_publishers, "publish_idp_linked"),
        ):
            result = service.handle_callback(idp, "code", "state", oauth_state, db)

        assert result.mode == "link"
        assert result.token_response == {}
        service._tokens.store_session_tokens.assert_not_called()


_STATE = SimpleNamespace(id="state-id", expires_at=datetime(2026, 11, 6, 12, 10, tzinfo=UTC))


class TestCreateCallbackSession:
    """The provider's sign-in is stored with the session it creates, in the same transaction."""

    def _create(self, service, *, active=True, token_response=None):
        user = SimpleNamespace(id=7, username="alice", active=active, email="a@example.com", model_dump=lambda: {})
        db = MagicMock()
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        order.attach_mock(service._tokens.store_session_tokens, "store")
        with (
            patch.object(callback_service.users_integration, "require_active_user"),
            patch.object(callback_service.users_schema.UserRead, "model_validate", return_value=SimpleNamespace(id=7)),
            patch.object(callback_service.sessions_integration, "create_session") as create_session,
        ):
            order.attach_mock(create_session, "create_session")
            session_id = service.create_callback_session(
                user, "10.0.0.1", "agent", MagicMock(), _STATE, 3, token_response or {"refresh_token": "rt"}, db
            )
        return session_id, create_session, order

    def test_the_session_expires_when_the_exchange_window_does(self, service):
        _, create_session, _ = self._create(service)

        assert create_session.call_args.args[6] == _STATE.expires_at
        assert create_session.call_args.kwargs["oauth_state_id"] == "state-id"

    def test_an_exchange_window_without_a_timezone_is_read_as_utc(self, service):
        naive = SimpleNamespace(id="state-id", expires_at=datetime(2026, 11, 6, 12, 0))
        user = SimpleNamespace(id=7)
        with (
            patch.object(callback_service.users_integration, "require_active_user"),
            patch.object(callback_service.users_schema.UserRead, "model_validate", return_value=SimpleNamespace(id=7)),
            patch.object(callback_service.sessions_integration, "create_session") as create_session,
        ):
            service.create_callback_session(user, "10.0.0.1", "agent", MagicMock(), naive, 3, {}, MagicMock())

        assert create_session.call_args.args[6] == datetime(2026, 11, 6, 12, 0, tzinfo=UTC)

    def test_the_sign_in_is_stored_for_the_new_session_before_the_commit(self, service):
        session_id, create_session, order = self._create(service)

        assert create_session.call_args.args[0] == session_id
        service._tokens.store_session_tokens.assert_called_once()
        assert service._tokens.store_session_tokens.call_args.args[:4] == (session_id, 7, 3, {"refresh_token": "rt"})
        assert [call[0] for call in order.mock_calls] == ["create_session", "store", "commit"]

    def test_a_provider_that_issued_no_token_is_still_recorded(self, service):
        session_id, _, _ = self._create(service, token_response={"access_token": "at"})

        assert service._tokens.store_session_tokens.call_args.args[:4] == (session_id, 7, 3, {"access_token": "at"})

    def test_an_inactive_account_gets_no_session_and_stores_nothing(self, service):
        user = SimpleNamespace(id=7, active=False)
        with (
            patch.object(
                callback_service.users_integration,
                "require_active_user",
                side_effect=core_exceptions.PermissionDeniedError("inactive"),
            ),
            patch.object(callback_service, "_record_login_refusal"),
            patch.object(callback_service.sessions_integration, "create_session") as create_session,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            service.create_callback_session(user, "10.0.0.1", "agent", MagicMock(), _STATE, 3, {}, MagicMock())

        create_session.assert_not_called()
        service._tokens.store_session_tokens.assert_not_called()

    def test_the_database_is_not_touched_until_the_identity_provider_has_answered(self, service):
        """The session holds a pooled connection once it is used, so no network call may run after that."""
        idp = MagicMock(
            issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp", provider_type="oauth2"
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        db = MagicMock()
        order = MagicMock()
        order.attach_mock(oauth_client.fetch_token, "token_exchange")
        order.attach_mock(db, "db")

        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "user-1"}) as get_userinfo,
            patch.object(
                callback_service.user_provisioning_service,
                "find_or_create_user",
                return_value=MagicMock(id=1, username="alice"),
            ),
        ):
            order.attach_mock(get_userinfo, "userinfo")
            service.handle_callback(idp, "code", "state", oauth_state, db)

        names = [call[0] for call in order.mock_calls]
        last_network_call = max(names.index("token_exchange"), names.index("userinfo"))
        assert not any(name.startswith("db") for name in names[: last_network_call + 1])


class TestOidcLoginFailsClosed:
    """An OIDC login is identified by a verified ID token; nothing weaker is accepted."""

    def _handle(self, service, *, config, token_response, purpose=_LOGIN, userinfo_error=None):
        idp = MagicMock(
            issuer_url="https://idp.example.com",
            userinfo_endpoint="https://idp.example.com/userinfo",
            slug="idp",
            provider_type="oidc",
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, purpose=purpose, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = token_response
        db = MagicMock()
        forged = MagicMock(return_value={"sub": "forged"})
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_oidc_configuration", return_value=config),
            patch.object(service._oidc, "get_userinfo", forged),
            patch.object(
                callback_service.user_provisioning_service,
                "find_or_create_user",
                return_value=MagicMock(id=1, username="alice"),
            ) as find_or_create,
        ):
            try:
                return service.handle_callback(idp, "code", "state", oauth_state, db)
            finally:
                self.find_or_create = find_or_create
                self.get_userinfo = forged
                self.fetch_token = oauth_client.fetch_token
                self.db = db

    @pytest.mark.parametrize(
        "config",
        [None, {}, {"issuer": "https://idp.example.com"}, {"jwks_uri": "https://idp.example.com/jwks"}],
    )
    def test_discovery_without_issuer_and_keys_refuses_the_login(self, service, config):
        with pytest.raises(core_exceptions.UpstreamError, match="publishes no issuer or signing keys"):
            self._handle(service, config=config, token_response={"access_token": "at"})

        self.fetch_token.assert_not_called()
        self.find_or_create.assert_not_called()
        self.db.commit.assert_not_called()

    def test_a_discovery_failure_is_not_swallowed(self, service):
        idp_error = core_exceptions.UpstreamError("discovery down")
        idp = MagicMock(issuer_url="https://idp.example.com", userinfo_endpoint=None, slug="idp", provider_type="oidc")
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "get_oidc_configuration", side_effect=idp_error),
            pytest.raises(core_exceptions.UpstreamError, match="discovery down"),
        ):
            service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

    @pytest.mark.parametrize("purpose", [_LOGIN, _LINK])
    def test_a_token_response_without_an_id_token_refuses_the_flow(self, service, purpose):
        """A userinfo answer alone, however plausible, must not identify the user."""
        config = {"issuer": "https://idp.example.com", "jwks_uri": "https://idp.example.com/jwks"}
        idp = MagicMock(
            issuer_url="https://idp.example.com",
            userinfo_endpoint="https://idp.example.com/userinfo",
            slug="idp",
            provider_type="oidc",
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=7, purpose=purpose, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        oauth_client.request.return_value.json.return_value = {"sub": "forged"}
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_oidc_configuration", return_value=config),
            patch.object(
                service._oidc,
                "get_userinfo",
                lambda **kw: callback_service.oidc_client_service.OidcClientService.get_userinfo(service._oidc, **kw),
            ),
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(callback_service.user_provisioning_service, "find_or_create_user") as find_or_create,
            patch.object(callback_service.identity_provider_links_integration, "create_user_identity_provider") as link,
            pytest.raises(core_exceptions.UpstreamError, match="no ID token"),
        ):
            service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        find_or_create.assert_not_called()
        link.assert_not_called()

    def test_get_userinfo_is_told_to_require_the_id_token(self, service):
        config = {"issuer": "https://idp.example.com", "jwks_uri": "https://idp.example.com/jwks"}
        self._handle(service, config=config, token_response={"access_token": "at", "id_token": "idt"})

        kwargs = self.get_userinfo.call_args.kwargs
        assert kwargs["require_id_token"] is True
        assert kwargs["jwks_uri"] == "https://idp.example.com/jwks"
        assert kwargs["expected_issuer"] == "https://idp.example.com"
        assert kwargs["expected_nonce"] == "nonce"


class TestOauth2LoginKeepsUserinfo:
    def test_an_oauth2_provider_is_identified_by_userinfo_alone(self, service):
        idp = MagicMock(
            issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp", provider_type="oauth2"
        )
        idp.name = "GitHub"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        oauth_client.request.return_value.json.return_value = {"sub": "user-1"}
        user = MagicMock(id=1, username="alice")
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_oidc_configuration") as discovery,
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "user-1"}) as get_userinfo,
            patch.object(callback_service.user_provisioning_service, "find_or_create_user", return_value=user),
        ):
            result = service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        discovery.assert_not_called()
        assert get_userinfo.call_args.kwargs["require_id_token"] is False
        assert result.user is user

    def test_an_unexpected_discovery_failure_is_not_swallowed(self, service):
        """Discovery returns None for every provider failure, so anything it raises is a bug."""
        idp = MagicMock(
            issuer_url="https://idp.example.com",
            userinfo_endpoint="https://idp.example.com/userinfo",
            slug="idp",
            provider_type="oauth2",
        )
        idp.name = "GitHub"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_oidc_configuration", side_effect=RuntimeError("bug")),
            pytest.raises(core_exceptions.ProcessingError) as exc_info,
        ):
            service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        oauth_client.fetch_token.assert_not_called()


class TestTokenExchangeRefusal:
    def test_a_provider_error_response_is_a_warning_and_an_upstream_error(self, service, caplog):
        from authlib.integrations.base_client import OAuthError

        idp = MagicMock(
            issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp", provider_type="oauth2"
        )
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, purpose=_LOGIN, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.side_effect = OAuthError("invalid_grant", "code expired")

        with (
            caplog.at_level(logging.DEBUG, logger=callback_service.logger.name),
            patch.object(service._oidc, "decrypt_client_id", return_value=AUD),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            pytest.raises(core_exceptions.UpstreamError),
        ):
            service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]


def test_a_claim_is_committed_even_when_another_callback_won(mock_db, service):
    with patch.object(callback_service.oauth_state_integration, "mark_oauth_state_used", return_value=False):
        assert service.claim_oauth_state("s", mock_db) is False

    mock_db.commit.assert_called_once()
