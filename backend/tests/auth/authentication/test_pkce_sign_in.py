"""A mobile password sign-in always carries a PKCE challenge and ends in an exchange; the MFA step carries none."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jasil.testing as jasil_testing
import pytest

import core.timezone as core_timezone
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration
from modules.auth.access_tokens.contracts import TokenType
from modules.auth.constants import ClientType
from tests.auth.authentication.conftest import BACKUP_CODE, MOBILE, PASSWORD, USER_ID, USERNAME, WEB

VERIFIER = "v" * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
PKCE = {"code_challenge": CHALLENGE, "code_challenge_method": "S256"}
CREDENTIALS = {"username": USERNAME, "password": PASSWORD}


@pytest.fixture(autouse=True)
def _timezone_aware_session_expiry():
    """SQLite hands back naive datetimes, which the session expiry cap of PostgreSQL's aware ones never meets."""
    with patch(
        "modules.auth.authentication.sso_exchange_service.sessions_integration.claim_session_for_token_exchange",
        return_value=datetime.now(UTC) + timedelta(days=7),
    ):
        yield


def _login(stack, headers, **fields):
    return stack.client.post("/auth/login", data={**CREDENTIALS, **fields}, headers=headers)


def _fields(response) -> set[str]:
    return {".".join(error["loc"]) for error in response.json()["detail"]}


class TestLoginForm:
    def test_a_mobile_login_without_pkce_is_refused(self, plain_signin):
        response = _login(plain_signin, MOBILE)

        assert response.status_code == 422
        assert "body.code_challenge" in _fields(response)

    @pytest.mark.parametrize("missing", ["code_challenge", "code_challenge_method"])
    def test_a_mobile_login_needs_both_pkce_fields(self, plain_signin, missing):
        response = _login(plain_signin, MOBILE, **{k: v for k, v in PKCE.items() if k != missing})

        assert response.status_code == 422
        assert f"body.{missing}" in _fields(response)

    def test_a_mobile_login_needs_the_s256_method(self, plain_signin):
        response = _login(plain_signin, MOBILE, code_challenge=CHALLENGE, code_challenge_method="plain")

        assert response.status_code == 422
        assert "body.code_challenge_method" in _fields(response)

    @pytest.mark.parametrize("challenge", ["short", "!" * 43])
    def test_a_malformed_challenge_is_refused_alike(self, plain_signin, challenge):
        response = _login(plain_signin, MOBILE, code_challenge=challenge, code_challenge_method="S256")

        assert response.status_code == 422
        assert "body.code_challenge" in _fields(response)

    def test_a_web_login_with_pkce_is_refused(self, plain_signin):
        response = _login(plain_signin, WEB, **PKCE)

        assert response.status_code == 422
        assert _fields(response) == {"body.code_challenge", "body.code_challenge_method"}

    def test_a_web_login_without_pkce_answers_tokens(self, plain_signin):
        body = _login(plain_signin, WEB).json()

        assert body["next_step"] == "tokens"

    def test_a_mobile_login_with_pkce_answers_exchange_and_never_tokens(self, plain_signin):
        body = _login(plain_signin, MOBILE, **PKCE).json()

        assert body["next_step"] == "exchange"
        assert set(body) == {"next_step", "session_id", "device_id"}

    def test_the_pkce_fields_are_form_fields_not_query_parameters(self, plain_signin):
        operation = plain_signin.app.openapi()["paths"]["/auth/login"]["post"]
        form = plain_signin.app.openapi()["components"]["schemas"][
            operation["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]["$ref"].rsplit("/", 1)[
                -1
            ]
        ]

        assert {"code_challenge", "code_challenge_method"} <= set(form["properties"])
        assert {p["name"] for p in operation["parameters"]} <= {"X-Client-Type", "X-Device-Id"}


class TestMfaStep:
    def _start(self, stack, headers, **fields):
        return _login(stack, headers, **fields).json()["mfa_challenge"]

    def _verify(self, stack, challenge, headers):
        return stack.client.post(
            "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": BACKUP_CODE}, headers=headers
        )

    def test_the_mfa_step_takes_no_pkce_parameters(self, mfa_plain_signin):
        operation = mfa_plain_signin.app.openapi()["paths"]["/auth/mfa/verify"]["post"]

        assert {p["name"] for p in operation["parameters"]} <= {"X-Client-Type", "X-Device-Id"}

    def test_a_mobile_mfa_login_continues_to_exchange_with_the_challenge_of_the_password_step(self, mfa_plain_signin):
        challenge = self._start(mfa_plain_signin, MOBILE, **PKCE)

        body = self._verify(mfa_plain_signin, challenge, MOBILE).json()

        assert body["next_step"] == "exchange"
        exchanged = mfa_plain_signin.client.post(
            f"/auth/sessions/{body['session_id']}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )
        assert exchanged.status_code == 200
        assert exchanged.json()["next_step"] == "tokens"

    def test_a_web_mfa_login_answers_tokens(self, mfa_plain_signin):
        challenge = self._start(mfa_plain_signin, WEB)

        assert self._verify(mfa_plain_signin, challenge, WEB).json()["next_step"] == "tokens"

    @pytest.mark.parametrize(("started", "verified"), [(WEB, MOBILE), (MOBILE, WEB)])
    def test_a_challenge_used_by_the_other_client_type_is_refused_like_an_unknown_one(
        self, mfa_plain_signin, started, verified
    ):
        fields = PKCE if started is MOBILE else {}
        challenge = self._start(mfa_plain_signin, started, **fields)

        wrong_kind = self._verify(mfa_plain_signin, challenge, verified)
        unknown = self._verify(mfa_plain_signin, "x" * 43, verified)

        assert wrong_kind.status_code == unknown.status_code
        assert wrong_kind.json() == unknown.json()

    def test_a_refused_challenge_of_the_other_client_type_stays_usable_by_its_own_client(self, mfa_plain_signin):
        challenge = self._start(mfa_plain_signin, MOBILE, **PKCE)
        self._verify(mfa_plain_signin, challenge, WEB)

        assert self._verify(mfa_plain_signin, challenge, MOBILE).json()["next_step"] == "exchange"


class TestExchangeRoute:
    def _exchange_session(self, stack) -> str:
        return _login(stack, MOBILE, **PKCE).json()["session_id"]

    def test_the_old_path_is_gone(self, plain_signin):
        session_id = self._exchange_session(plain_signin)

        response = plain_signin.client.post(
            f"/public/idp/session/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )

        assert response.status_code == 404

    def test_a_mobile_exchange_answers_the_mobile_token_body(self, plain_signin):
        session_id = self._exchange_session(plain_signin)

        body = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        ).json()

        assert body["next_step"] == "tokens"
        assert body["token_type"] == "bearer"
        assert "refresh_token" in body
        assert "csrf_token" not in body

    def test_the_header_is_required(self, plain_signin):
        session_id = self._exchange_session(plain_signin)

        response = plain_signin.client.post(f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER})

        assert response.status_code == 422

    def test_a_header_that_differs_from_the_stored_client_type_is_refused_like_a_wrong_verifier(self, plain_signin):
        session_id = self._exchange_session(plain_signin)

        mismatch = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=WEB
        )
        wrong = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": "w" * 43}, headers=MOBILE
        )

        assert mismatch.status_code == wrong.status_code == 400
        assert "refresh_token" not in mismatch.text

    def test_the_session_survives_a_refused_exchange(self, plain_signin):
        session_id = self._exchange_session(plain_signin)
        plain_signin.client.post(f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=WEB)

        response = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )

        assert response.status_code == 200


class TestSecurityGeneration:
    """A pending exchange is redeemed only while the account's security is as it was when it was created."""

    @staticmethod
    def _state(stack, session_id):
        with stack.factory() as db:
            return sessions_integration.get_session_with_oauth_state(uuid.UUID(session_id), db)[1]

    @staticmethod
    def _exchange(stack, session_id):
        return stack.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )

    def test_the_sign_in_stamps_the_state_with_the_current_generation(self, plain_signin, security_generations):
        security_generations.generations[USER_ID] = 8

        session_id = _login(plain_signin, MOBILE, **PKCE).json()["session_id"]

        assert self._state(plain_signin, session_id).security_generation == 8

    def test_an_unchanged_account_exchanges(self, plain_signin, security_generations):
        security_generations.generations[USER_ID] = 8
        session_id = _login(plain_signin, MOBILE, **PKCE).json()["session_id"]

        assert self._exchange(plain_signin, session_id).status_code == 200

    def test_an_mfa_sign_in_stamps_the_state_with_the_generation_it_verified_under(
        self, mfa_plain_signin, security_generations
    ):
        security_generations.generations[USER_ID] = 8
        challenge = _login(mfa_plain_signin, MOBILE, **PKCE).json()["mfa_challenge"]

        session_id = mfa_plain_signin.client.post(
            "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": BACKUP_CODE}, headers=MOBILE
        ).json()["session_id"]

        assert self._state(mfa_plain_signin, session_id).security_generation == 8

    def test_the_owner_changing_the_password_without_revoking_other_sessions_refuses_the_exchange(self, plain_signin):
        session_id = _login(plain_signin, MOBILE, **PKCE).json()["session_id"]
        with (
            plain_signin.factory() as db,
            patch.object(account_security_service.step_up_service, "verify_step_up_credentials"),
        ):
            account_security_service.stage_change_own_password(
                USER_ID,
                PASSWORD,
                "a brand new passphrase 42",
                None,
                MagicMock(),
                db,
                revoke_other_sessions=False,
                current_session_id=uuid.UUID("00000000-0000-4000-8000-0000000000a3"),
            )
            db.commit()

        with jasil_testing.capture_audit() as audit:
            response = self._exchange(plain_signin, session_id)

        assert response.status_code == 404
        assert "refresh_token" not in response.text
        entry = audit.assert_audited("auth.session.login", outcome="failure")
        assert entry.details["reason"] == "security_changed"

    def test_a_session_whose_state_has_no_stamp_is_refused(self, plain_signin):
        session_id = TestWebExchange()._web_session(plain_signin, ClientType.MOBILE, security_generation=None)

        assert self._exchange(plain_signin, session_id).status_code == 404


class TestWebExchange:
    def _web_session(self, stack, client_type=ClientType.WEB, security_generation=0) -> uuid.UUID:
        """Create the session an identity-provider callback leaves for a client, stamped as the callback stamps it."""
        session_id = uuid4()
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        with stack.factory() as db:
            state = oauth_state_integration.create_oauth_state(
                db=db,
                state_id=state_id,
                nonce=nonce,
                client_type=client_type.value,
                ip_address="127.0.0.1",
                redirect_path=None,
                code_challenge=CHALLENGE,
                code_challenge_method="S256",
                purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
                security_generation=security_generation,
            )
            sessions_integration.create_session(
                session_id,
                users_integration.require_user(USER_ID, db),
                client_type,
                "127.0.0.1",
                "agent",
                None,
                credentials_integration.get_password_hasher(),
                core_timezone.to_utc_aware(state.expires_at),
                db,
                oauth_state_id=state_id,
                amr=["pwd"],
                device_hash=None,
            )
            db.commit()
        return session_id

    def test_a_web_exchange_answers_the_web_token_body_and_a_cookie(self, plain_signin):
        session_id = self._web_session(plain_signin)

        response = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=WEB
        )

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert body["token_type"] == "bearer"
        assert "csrf_token" in body
        assert "refresh_token" not in body
        assert "endurain_refresh_token" in response.headers["set-cookie"]

    def test_a_mobile_header_cannot_redeem_a_web_session(self, plain_signin):
        session_id = self._web_session(plain_signin)

        response = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )

        assert response.status_code == 400
        assert "set-cookie" not in response.headers


class TestClientIdClaim:
    """Every token names the client type of the session it belongs to."""

    @staticmethod
    def _client_id(token: str, token_type) -> str:
        manager = access_tokens_integration.get_token_manager()
        manager.validate_token_expiration(token, token_type)
        return manager.get_token_claim(token, "client_id", token_type)

    def test_a_web_password_sign_in_issues_web_tokens(self, plain_signin):
        response = _login(plain_signin, WEB)

        assert self._client_id(response.json()["access_token"], TokenType.ACCESS) == "web"
        cookies = (cookie.split(";", 1)[0] for cookie in response.headers.get_list("set-cookie"))
        refresh_token = next(
            value
            for name, value in (c.split("=", 1) for c in cookies)
            if name.endswith("endurain_refresh_token") and value != '""'
        )
        assert self._client_id(refresh_token, TokenType.REFRESH) == "web"

    def test_a_mobile_exchange_issues_mobile_tokens(self, plain_signin):
        session_id = _login(plain_signin, MOBILE, **PKCE).json()["session_id"]

        body = plain_signin.client.post(
            f"/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        ).json()

        assert self._client_id(body["access_token"], TokenType.ACCESS) == "mobile"
        assert self._client_id(body["refresh_token"], TokenType.REFRESH) == "mobile"
