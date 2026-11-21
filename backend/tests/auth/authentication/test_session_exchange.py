"""A session that holds no tokens yet is exchanged once, for its client type, against its PKCE verifier."""

from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from modules.auth.access_tokens.contracts import TokenType
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
    MOBILE,
    PKCE,
    VERIFIER,
    WEB,
    exchange,
    exchange_path,
    login,
    make_sso_session,
)

_SESSION_NOT_ELIGIBLE = "Session not found or not eligible for token exchange"


def _mobile_session(client, account) -> str:
    return login(client, account, MOBILE).json()["session_id"]


def _login_rows(committed_sessions):
    return audit_rows(committed_sessions, login_audit_actions.LOGIN)


def _unstamp(committed_sessions, session_id) -> None:
    """Remove the security generation the callback stamped on the session's OAuth state."""
    with committed_sessions() as db:
        db.execute(
            sa.update(oauth_state_models.OAuthState)
            .where(
                oauth_state_models.OAuthState.id
                == sa.select(sessions_models.UsersSessions.oauth_state_id)
                .where(sessions_models.UsersSessions.id == session_id)
                .scalar_subquery()
            )
            .values(security_generation=None)
        )
        db.commit()


class TestMobileExchange:
    def test_the_verifier_of_the_sign_in_gives_the_mobile_token_body(self, client, account):
        session_id = _mobile_session(client, account)

        response = exchange(client, session_id)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert body["token_type"] == "bearer"
        assert body["session_id"] == session_id
        assert "refresh_token" in body
        assert "csrf_token" not in body

    def test_the_issued_tokens_name_the_mobile_client_type(self, client, account):
        body = exchange(client, _mobile_session(client, account)).json()

        manager = access_tokens_integration.get_token_manager()
        for token, token_type in ((body["access_token"], TokenType.ACCESS), (body["refresh_token"], TokenType.REFRESH)):
            manager.validate_token_expiration(token, token_type)
            assert manager.get_token_claim(token, "client_type", token_type) == "mobile"

    def test_the_issued_access_token_is_accepted(self, client, account):
        token = exchange(client, _mobile_session(client, account)).json()["access_token"]

        profile = client.get("/api/v1/profile", headers={**MOBILE, "Authorization": f"Bearer {token}"})

        assert profile.status_code == 200

    def test_a_session_is_exchanged_once(self, client, account):
        session_id = _mobile_session(client, account)
        exchange(client, session_id)

        again = exchange(client, session_id)

        assert again.status_code == 404
        assert again.json()["detail"] == _SESSION_NOT_ELIGIBLE

    def test_a_wrong_verifier_is_refused_without_tokens_and_the_session_survives(self, client, account):
        session_id = _mobile_session(client, account)

        wrong = exchange(client, session_id, "w" * 43)

        assert wrong.status_code == 400
        assert "refresh_token" not in wrong.text
        assert exchange(client, session_id).status_code == 200

    def test_a_header_that_differs_from_the_stored_client_type_is_refused_like_a_wrong_verifier(self, client, account):
        session_id = _mobile_session(client, account)

        mismatch = exchange(client, session_id, headers=WEB)
        wrong = exchange(client, session_id, "w" * 43)

        assert mismatch.status_code == wrong.status_code == 400
        assert mismatch.json()["detail"] == wrong.json()["detail"]
        assert "set-cookie" not in mismatch.headers
        assert exchange(client, session_id).status_code == 200

    def test_the_client_type_header_is_required(self, client, account):
        session_id = _mobile_session(client, account)

        response = client.post(exchange_path(session_id), json={"code_verifier": VERIFIER})

        assert response.status_code == 422

    def test_a_session_id_that_is_not_a_uuid_is_refused(self, client):
        assert exchange(client, "not-a-uuid").status_code == 422

    def test_an_unknown_session_is_not_found(self, client):
        response = exchange(client, "00000000-0000-4000-8000-000000000000")

        assert response.status_code == 404
        assert response.json()["detail"] == _SESSION_NOT_ELIGIBLE

    def test_the_path_the_exchange_moved_from_is_gone(self, client, account):
        session_id = _mobile_session(client, account)

        response = client.post(
            f"/api/v1/public/idp/session/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=MOBILE
        )

        assert response.status_code == 404

    def test_the_two_exchanges_of_one_session_have_one_winner(self, app, client, account):
        session_id = _mobile_session(client, account)

        def attempt(_: int) -> int:
            return exchange(TestClient(app), session_id).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(attempt, range(2)))

        assert statuses == [200, 404]


class TestWebExchangeOfAnIdentityProviderSession:
    def test_it_answers_the_web_token_body_and_a_refresh_cookie(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)

        response = exchange(client, session_id, headers=WEB)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert "refresh_token" not in body
        assert "csrf_token" not in body
        assert "endurain_refresh_token" in response.headers["set-cookie"]

    def test_a_mobile_header_cannot_redeem_a_web_session(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)

        response = exchange(client, session_id, headers=MOBILE)

        assert response.status_code == 400
        assert "set-cookie" not in response.headers

    def test_a_mobile_session_is_redeemed_by_the_mobile_client_for_every_token(
        self, client, committed_sessions, account
    ):
        session_id = make_sso_session(committed_sessions, account.user, client_type="mobile")

        body = exchange(client, session_id, headers=MOBILE).json()

        assert {"access_token", "refresh_token", "device_id"} <= set(body)


class TestExchangeAudit:
    def test_a_wrong_verifier_is_audited_as_a_pkce_mismatch_of_the_provider_sign_in(
        self, client, committed_sessions, account
    ):
        session_id = make_sso_session(committed_sessions, account.user)

        exchange(client, session_id, "w" * 43, headers=WEB)

        (row,) = _login_rows(committed_sessions)
        assert (row.outcome, row.target_id, row.target_owner_id) == (
            "failure",
            str(account.user.id),
            str(account.user.id),
        )
        assert row.details == {
            "method": "identity_provider",
            "mfa": False,
            "reason": "pkce_mismatch",
            "new_device": False,
        }

    def test_a_header_other_than_the_stored_client_type_is_audited_like_a_pkce_mismatch(
        self, client, committed_sessions, account
    ):
        session_id = make_sso_session(committed_sessions, account.user)

        exchange(client, session_id, headers=MOBILE)

        (row,) = _login_rows(committed_sessions)
        assert (row.outcome, row.details["reason"]) == ("failure", "pkce_mismatch")

    def test_a_successful_exchange_writes_only_its_success_row(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)

        exchange(client, session_id, headers=WEB)

        (row,) = _login_rows(committed_sessions)
        assert row.outcome == "success"
        assert row.details["method"] == "identity_provider"
        assert row.details["reason"] is None

    def test_an_account_deactivated_after_the_callback_is_refused_and_audited_as_denied(
        self, client, committed_sessions, account
    ):
        session_id = make_sso_session(committed_sessions, account.user)
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == account.user.id).values(active=False)
            )
            db.commit()

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 403
        (row,) = _login_rows(committed_sessions)
        assert (row.outcome, row.details["reason"]) == ("denied", "inactive")

    def test_a_password_session_is_not_audited_by_its_exchange(self, client, committed_sessions, account):
        session_id = _mobile_session(client, account)
        before = len(_login_rows(committed_sessions))

        exchange(client, session_id)

        assert len(_login_rows(committed_sessions)) == before == 1


class TestSecurityGeneration:
    """A pending exchange is redeemed only while the account's security is as it was when it was created."""

    def test_the_owner_changing_the_password_after_the_sign_in_refuses_the_exchange(
        self, client, committed_sessions, account
    ):
        session_id = _mobile_session(client, account)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(account.user.id, db)
            db.commit()

        response = exchange(client, session_id)

        assert response.status_code == 404
        assert "refresh_token" not in response.text
        (row,) = _login_rows(committed_sessions)[1:]
        assert (row.outcome, row.details["reason"]) == ("failure", "security_changed")

    def test_the_same_change_refuses_an_identity_provider_session(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(account.user.id, db)
            db.commit()

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 404
        assert "set-cookie" not in response.headers
        (row,) = _login_rows(committed_sessions)
        assert (row.outcome, row.details["reason"]) == ("failure", "security_changed")

    def test_a_session_whose_state_has_no_stamp_is_refused(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)
        _unstamp(committed_sessions, session_id)

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 404
        (row,) = _login_rows(committed_sessions)
        assert row.details["reason"] == "security_changed"

    def test_a_change_made_before_the_sign_in_does_not_outdate_it(self, client, committed_sessions, account):
        with committed_sessions() as db:
            security_generation_integration.stage_bump(account.user.id, db)
            db.commit()

        assert exchange(client, _mobile_session(client, account)).status_code == 200

    def test_the_sign_in_stamps_the_state_with_the_generation_it_read(self, client, committed_sessions, account):
        with committed_sessions() as db:
            security_generation_integration.stage_bump(account.user.id, db)
            security_generation_integration.stage_bump(account.user.id, db)
            expected = security_generation_integration.current_generation(account.user.id, db)
            db.commit()

        session_id = _mobile_session(client, account)

        with committed_sessions() as db:
            stamp = db.scalar(
                sa.select(oauth_state_models.OAuthState.security_generation)
                .join(
                    sessions_models.UsersSessions,
                    sessions_models.UsersSessions.oauth_state_id == oauth_state_models.OAuthState.id,
                )
                .where(sessions_models.UsersSessions.id == session_id)
            )
        assert stamp == expected >= 2


@pytest.mark.parametrize("field", ["code_challenge", "code_challenge_method"])
def test_a_mobile_login_needs_both_pkce_fields(client, account, field):
    response = login(client, account, MOBILE, **{k: v for k, v in PKCE.items() if k != field})

    assert response.status_code == 422
    assert f"body.{field}" in {error["field"] for error in response.json()["errors"]}
