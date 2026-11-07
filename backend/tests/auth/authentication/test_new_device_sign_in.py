"""Every successful sign-in is recorded against the device it came from, in the sign-in's own transaction."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.public_router as auth_public_router
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.authentication.sso_exchange_service as authentication_service_sso_exchange_service
import modules.auth.authentication.sso_public_router as sso_public_router
import modules.auth.credentials.password_hasher as auth_password_hasher
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.known_devices.events as known_devices_events
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.oauth_state.constants as oauth_state_constants
from tests._helpers.auth import pending_login

_SERVICE = "modules.auth.authentication.service"
_CLAIMED_EXPIRY = datetime(2999, 1, 1, tzinfo=UTC)
_RECORD = f"{_SERVICE}.known_devices_integration.record_sign_in"
_USER = SimpleNamespace(id=5, username="alice", active=True, access_type="regular")
_TOKENS = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
_DEVICE_ID = "d" * 43
_ISSUED = "n" * 43
_LOGIN = login_audit_actions.LOGIN.id
_PASSWORD = known_devices_events.SignInMethod.PASSWORD
_IDENTITY_PROVIDER = known_devices_events.SignInMethod.IDENTITY_PROVIDER


def _signed(device_id, new_device=False):
    """Return what recording a sign-in answers."""
    return known_devices_contracts.SignInRecord(device_id=device_id, new_device=new_device)


@pytest.fixture
def password_sign_in():
    """Let a password sign-in through to session creation, with no MFA."""
    with (
        patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
        patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
        patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
        patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=_TOKENS),
        patch(
            f"{_SERVICE}.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ),
    ):
        yield


def _login(db, *, client_type="web", device_id=_DEVICE_ID, **kwargs):
    if client_type == "mobile":
        kwargs = {"code_challenge": "a" * 43, "code_challenge_method": "S256", **kwargs}
    else:
        kwargs = {"code_challenge": None, "code_challenge_method": None, **kwargs}
    return authentication_service.login_for_access_token(
        "203.0.113.7",
        "agent",
        "alice",
        "secret",
        client_type,
        MagicMock(is_locked_out=MagicMock(return_value=False)),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        db,
        password_change_store=MagicMock(),
        device_id=device_id,
        **kwargs,
    )


class TestPasswordSignIn:
    def test_a_web_sign_in_records_the_device_before_the_audit_row_and_the_commit(self, mock_db, password_sign_in):
        steps = []
        mock_db.commit.side_effect = lambda: steps.append("commit")
        with jasil_testing.capture_audit() as audit, patch(_RECORD) as record:
            record.side_effect = lambda *args: (
                steps.append(("record", bool(audit.matching(_LOGIN)))) or _signed(_ISSUED, True)
            )
            outcome = _login(mock_db)

        record.assert_called_once_with(5, _DEVICE_ID, "203.0.113.7", "agent", _PASSWORD, mock_db)
        assert steps == [("record", False), "commit"]
        assert audit.matching(_LOGIN)
        assert outcome.device_id == _ISSUED
        assert audit.assert_audited(_LOGIN, outcome="success").details["new_device"] is True

    def test_a_sign_in_from_a_known_device_is_not_flagged_as_new(self, mock_db, password_sign_in):
        with jasil_testing.capture_audit() as audit, patch(_RECORD, return_value=_signed(_DEVICE_ID)):
            _login(mock_db)

        assert audit.assert_audited(_LOGIN, outcome="success").details == {
            "method": "password",
            "mfa": False,
            "reason": None,
            "new_device": False,
        }

    def test_a_mobile_pkce_sign_in_hands_the_app_its_device_id_in_the_session_body(self, mock_db, password_sign_in):
        session = auth_schema.MobileSessionRead(next_step="exchange", session_id="sid")
        with (
            patch(f"{_SERVICE}.create_mobile_pkce_session_response", return_value=session) as pkce,
            patch(_RECORD, return_value=_signed(_ISSUED)) as record,
        ):
            outcome = _login(mock_db, client_type="mobile", device_id=None)

        pkce.assert_called_once()
        record.assert_called_once_with(5, None, "203.0.113.7", "agent", _PASSWORD, mock_db)
        assert outcome.body.device_id == _ISSUED
        assert outcome.device_id is None

    def test_a_mobile_sign_in_is_recorded_under_the_header_id_and_returns_it_in_the_body_only(
        self, mock_db, password_sign_in
    ):
        session = auth_schema.MobileSessionRead(next_step="exchange", session_id="sid")
        with (
            patch(f"{_SERVICE}.create_mobile_pkce_session_response", return_value=session),
            patch(_RECORD, return_value=_signed(_DEVICE_ID)) as record,
        ):
            outcome = _login(mock_db, client_type="mobile")

        record.assert_called_once_with(5, _DEVICE_ID, "203.0.113.7", "agent", _PASSWORD, mock_db)
        assert isinstance(outcome.body, auth_schema.MobileSessionRead)
        assert outcome.body.device_id == _DEVICE_ID
        assert outcome.device_id is None

    def test_a_mobile_sign_in_without_an_id_is_given_a_new_one(self, mock_db, password_sign_in):
        session = auth_schema.MobileSessionRead(next_step="exchange", session_id="sid")
        with (
            patch(f"{_SERVICE}.create_mobile_pkce_session_response", return_value=session),
            patch(_RECORD, return_value=_signed(_ISSUED, True)),
        ):
            outcome = _login(mock_db, client_type="mobile", device_id=None)

        assert outcome.body.device_id == _ISSUED

    def test_a_web_sign_in_body_has_no_device_id_field(self, mock_db, password_sign_in):
        with patch(_RECORD, return_value=_signed(_ISSUED)):
            outcome = _login(mock_db)

        assert isinstance(outcome.body, auth_schema.TokenWebRead)
        assert not hasattr(outcome.body, "device_id")
        assert outcome.device_id == _ISSUED

    def test_a_password_that_needs_mfa_records_nothing(self, mock_db, password_sign_in):
        store = MagicMock(add_pending_login=MagicMock(return_value="challenge"))
        with (
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(_RECORD) as record,
        ):
            outcome = authentication_service.login_for_access_token(
                "203.0.113.7",
                "agent",
                "alice",
                "secret",
                "web",
                MagicMock(is_locked_out=MagicMock(return_value=False)),
                store,
                MagicMock(),
                MagicMock(),
                mock_db,
                code_challenge=None,
                code_challenge_method=None,
                password_change_store=MagicMock(),
                device_id=_DEVICE_ID,
            )

        record.assert_not_called()
        assert outcome.device_id is None

    def test_a_completed_mfa_sign_in_records_the_device(self, mock_db):
        store = MagicMock()
        store.get_pending_login.return_value = pending_login(5)
        store.claim_pending_login.return_value = pending_login(5)
        store.is_locked_out.return_value = False
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch("modules.auth.authentication.token_service.create_tokens", return_value=_TOKENS),
            patch(
                f"{_SERVICE}.sessions_integration.create_session",
                return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
            ),
            patch(_RECORD, return_value=_signed(_ISSUED)) as record,
        ):
            outcome = authentication_service.verify_mfa_and_login(
                "203.0.113.7",
                "agent",
                SimpleNamespace(mfa_challenge="challenge", mfa_code="123456"),
                "web",
                MagicMock(),
                store,
                MagicMock(),
                MagicMock(),
                mock_db,
                password_change_store=MagicMock(),
                device_id=None,
            )

        record.assert_called_once_with(5, None, "203.0.113.7", "agent", _PASSWORD, mock_db)
        assert outcome.device_id == _ISSUED


class TestSsoSignIn:
    def _exchange(self, db, *, idp_id, client_type="web", record_returns=_ISSUED):
        oauth_state = SimpleNamespace(
            id="state",
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
            code_challenge="c",
            code_challenge_method="S256",
            client_type=client_type,
            idp_id=idp_id,
        )
        session = SimpleNamespace(user_id=5, tokens_exchanged=False, expires_at=datetime(2027, 1, 1, tzinfo=UTC))
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state", return_value=(session, oauth_state)),
            patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier"),
            patch(f"{_SERVICE}.users_integration.require_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch("modules.auth.authentication.token_service.create_tokens", return_value=_TOKENS),
            patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=_CLAIMED_EXPIRY),
            patch(_RECORD) as record,
        ):
            if callable(record_returns):
                record.side_effect = record_returns
            else:
                record.return_value = _signed(record_returns)
            outcome = authentication_service_sso_exchange_service.exchange_tokens_for_session(
                "sid",
                "verifier",
                None,
                client_type,
                "203.0.113.7",
                "agent",
                MagicMock(),
                MagicMock(),
                MagicMock(),
                db,
                device_id=_DEVICE_ID,
            )
        return outcome, record

    def test_an_sso_sign_in_records_the_device_before_the_audit_row_and_the_commit(self, mock_db):
        steps = []
        mock_db.commit.side_effect = lambda: steps.append("commit")
        with jasil_testing.capture_audit() as audit:
            outcome, record = self._exchange(
                mock_db,
                idp_id=3,
                record_returns=lambda *args: (
                    steps.append(("record", bool(audit.matching(_LOGIN)))) or _signed(_ISSUED, True)
                ),
            )

        record.assert_called_once_with(5, _DEVICE_ID, "203.0.113.7", "agent", _IDENTITY_PROVIDER, mock_db)
        assert steps == [("record", False), "commit"]
        assert audit.matching(_LOGIN)
        assert outcome.device_id == _ISSUED
        assert audit.assert_audited(_LOGIN, outcome="success").details["new_device"] is True

    def test_an_sso_sign_in_from_a_known_device_is_not_flagged_as_new(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._exchange(mock_db, idp_id=3)

        assert audit.assert_audited(_LOGIN, outcome="success").details["new_device"] is False

    def test_a_mobile_sso_sign_in_hands_the_app_its_device_id_in_the_body(self, mock_db):
        outcome, record = self._exchange(mock_db, idp_id=3, client_type="mobile")

        assert record.call_args.args[1] == _DEVICE_ID
        assert outcome.body.device_id == _ISSUED
        assert outcome.device_id is None

    def test_the_exchange_of_a_password_pkce_session_records_nothing(self, mock_db):
        """A mobile password sign-in was recorded when its session was created."""
        outcome, record = self._exchange(mock_db, idp_id=None, client_type="mobile", record_returns=None)

        record.assert_not_called()
        assert outcome.device_id is None
        assert outcome.body.device_id is None


# --------------------------------------------------------------------------------------------------------------------
# Routes: the cookie is read and set at the HTTP boundary.
# --------------------------------------------------------------------------------------------------------------------


def _login_app(mock_db, client_type: str) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.include_router(auth_public_router.router, prefix="/api/v1/auth")
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: MagicMock()
    app.dependency_overrides[auth_token_manager.get_token_manager] = lambda: MagicMock()
    app.dependency_overrides[auth_public_router.authentication_dependencies.get_client_type] = lambda: client_type
    app.dependency_overrides[failed_login_store.get_failed_login_attempts] = lambda: MagicMock(
        is_locked_out=MagicMock(return_value=False)
    )
    app.dependency_overrides[mfa_dependencies.get_pending_mfa_store] = lambda: MagicMock()
    return TestClient(app)


@pytest.fixture
def web_login_body():
    body = {
        "next_step": "tokens",
        "session_id": "sid",
        "access_token": "at",
        "csrf_token": "csrf",
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_token_expires_in": 604800,
    }
    refresh = auth_schema.RefreshCookie("rt", datetime.now(UTC) + timedelta(days=7))
    with patch(f"{_SERVICE}.complete_login", return_value=auth_schema.AuthOutcome(body, refresh)):
        yield


def _device_cookie(response) -> str | None:
    headers = response.headers.get_list("set-cookie")
    matches = [header for header in headers if header.startswith(f"{known_devices_dependencies.DEVICE_COOKIE_NAME}=")]
    assert len(matches) <= 1
    return matches[0] if matches else None


class TestLoginRoute:
    def _post(self, client):
        return client.post("/api/v1/auth/login", data={"username": "alice", "password": "secret"})

    def test_a_web_sign_in_sets_the_device_cookie(self, mock_db, password_sign_in, web_login_body):
        with patch(_RECORD, return_value=_signed(_ISSUED)):
            response = self._post(_login_app(mock_db, "web"))

        assert response.status_code == 200, response.text
        cookie = _device_cookie(response)
        assert cookie is not None
        assert cookie.startswith(f"{known_devices_dependencies.DEVICE_COOKIE_NAME}={_ISSUED};")
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Max-Age=34560000" in cookie
        assert "Path=/api/v1" in cookie

    def test_the_cookie_the_browser_sent_reaches_the_service(self, mock_db, password_sign_in, web_login_body):
        client = _login_app(mock_db, "web")
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, _DEVICE_ID)
        with patch(_RECORD, return_value=_signed(_DEVICE_ID)) as record:
            self._post(client)

        assert record.call_args.args[1] == _DEVICE_ID

    def test_a_malformed_cookie_is_ignored(self, mock_db, password_sign_in, web_login_body):
        client = _login_app(mock_db, "web")
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, "not-a-device-id")
        with patch(_RECORD, return_value=_signed(_ISSUED)) as record:
            self._post(client)

        assert record.call_args.args[1] is None

    def test_a_mobile_sign_in_reads_the_header_returns_the_id_in_the_body_and_sets_no_cookie(
        self, mock_db, password_sign_in
    ):
        session = auth_schema.MobileSessionRead(next_step="exchange", session_id="sid")
        with (
            patch(f"{_SERVICE}.create_mobile_pkce_session_response", return_value=session),
            patch(_RECORD, return_value=_signed(_DEVICE_ID)) as record,
        ):
            response = _login_app(mock_db, "mobile").post(
                "/api/v1/auth/login",
                data={
                    "username": "alice",
                    "password": "secret",
                    "code_challenge": "a" * 43,
                    "code_challenge_method": "S256",
                },
                headers={"X-Device-Id": _DEVICE_ID},
            )

        assert response.status_code == 200, response.text
        assert record.call_args.args[1] == _DEVICE_ID
        assert response.json()["device_id"] == _DEVICE_ID
        assert _device_cookie(response) is None
        assert response.headers["cache-control"] == "no-store"

    def test_a_web_sign_in_response_has_no_device_id_in_its_body(self, mock_db, password_sign_in):
        with patch(_RECORD, return_value=_signed(_ISSUED)):
            response = self._post(_login_app(mock_db, "web"))

        assert "device_id" not in response.json()


class TestMfaVerifyRoute:
    def test_a_web_mfa_sign_in_sets_the_device_cookie_from_the_cookie_sent(self, mock_db, web_login_body):
        client = _login_app(mock_db, "web")
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, _DEVICE_ID)
        with patch(f"{_SERVICE}.verify_mfa_and_login") as verify:
            verify.return_value = auth_schema.AuthOutcome(
                {
                    "next_step": "tokens",
                    "session_id": "sid",
                    "access_token": "at",
                    "csrf_token": "csrf",
                    "token_type": "bearer",
                    "expires_in": 900,
                    "refresh_token_expires_in": 604800,
                },
                device_id=_DEVICE_ID,
            )
            response = client.post("/api/v1/auth/mfa/verify", json={"mfa_challenge": "c" * 43, "mfa_code": "123456"})

        assert response.status_code == 200, response.text
        assert verify.call_args.kwargs["device_id"] == _DEVICE_ID
        assert _device_cookie(response).startswith(f"{known_devices_dependencies.DEVICE_COOKIE_NAME}={_DEVICE_ID};")


class TestTokenExchangeRoute:
    def _client(self, mock_db):
        app = FastAPI()
        app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
        app.include_router(sso_public_router.router, prefix="/api/v1/auth")
        app.dependency_overrides[core_database.get_db] = lambda: mock_db
        app.dependency_overrides[mfa_dependencies.get_pending_mfa_store] = lambda: MagicMock()
        return TestClient(app)

    def _outcome(self, device_id):
        body = auth_schema.TokenWebRead(
            next_step="tokens",
            session_id="sid",
            access_token="at",
            csrf_token="csrf",
            expires_in=900,
            refresh_token_expires_in=604800,
        )
        return auth_schema.AuthOutcome(body, device_id=device_id)

    def test_a_web_exchange_passes_the_request_and_sets_the_device_cookie(self, mock_db):
        client = self._client(mock_db)
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, _DEVICE_ID)
        with patch(
            "modules.auth.authentication.sso_exchange_service.exchange_tokens_for_session",
            return_value=self._outcome(_DEVICE_ID),
        ) as exchange:
            response = client.post(
                "/api/v1/auth/sessions/sid/tokens",
                json={"code_verifier": "v" * 43},
                headers={"X-Client-Type": "web", "User-Agent": "agent"},
            )

        assert response.status_code == 200, response.text
        assert exchange.call_args.kwargs["device_id"] == _DEVICE_ID
        assert exchange.call_args.args[5] == "agent"
        assert _device_cookie(response).startswith(f"{known_devices_dependencies.DEVICE_COOKIE_NAME}={_DEVICE_ID};")

    def test_a_mobile_exchange_reads_the_header_returns_the_id_in_the_body_and_sets_no_cookie(self, mock_db):
        body = auth_schema.TokenMobileRead(
            next_step="tokens",
            session_id="sid",
            access_token="at",
            refresh_token="rt",
            expires_in=900,
            refresh_token_expires_in=604800,
            device_id=_ISSUED,
        )
        with patch(
            "modules.auth.authentication.sso_exchange_service.exchange_tokens_for_session",
            return_value=auth_schema.AuthOutcome(body),
        ) as exchange:
            response = self._client(mock_db).post(
                "/api/v1/auth/sessions/sid/tokens",
                json={"code_verifier": "v" * 43},
                headers={"X-Client-Type": "mobile", "X-Device-Id": _DEVICE_ID},
            )

        assert response.status_code == 200, response.text
        assert exchange.call_args.kwargs["device_id"] == _DEVICE_ID
        assert response.json()["device_id"] == _ISSUED
        assert _device_cookie(response) is None
        assert response.headers["cache-control"] == "no-store"
