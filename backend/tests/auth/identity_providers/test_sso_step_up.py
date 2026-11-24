"""An account without a password confirms a sensitive change by signing in again at its provider."""

import pytest

import modules.auth.security_generation.integration_service as security_generation_integration
import modules.users.users.models as users_models
from tests.auth.identity_providers.conftest import VERIFIER
from tests.auth.identity_providers.fake_provider import pkce_challenge
from tests.auth.identity_providers.sso_helpers import audit

STEP_UP_VERIFY = "auth.step_up.verify"
KEY = {"name": "ci", "scopes": ["activities:read"]}


def _only(rows):
    assert len(rows) == 1, rows
    return rows[0]


def _start(account, *, action="api_key_create", redirect="/settings/security", challenge=None):
    from tests.auth.identity_providers.conftest import Started

    response = account.post(
        f"/profile/identity-providers/{account.idp_id}/step-up",
        {"code_challenge": challenge or pkce_challenge(VERIFIER), "action": action, "redirect": redirect},
    )
    if response.status_code != 200:
        return response, None
    started = account.browser.started(response, VERIFIER)
    assert isinstance(started, Started)
    return response, started


def _create_key(account, ticket=None, verifier=VERIFIER, **overrides):
    body = {**KEY, "step_up": {"idp_reauth": {"ticket": ticket, "code_verifier": verifier}} if ticket else {}}
    body.update(overrides)
    return account.post("/profile/api-keys", body)


@pytest.fixture
def started(sso_account):
    response, flow = _start(sso_account)
    assert response.status_code == 200, response.text
    return flow


class TestFreshSignIn:
    def test_the_sensitive_request_without_proof_is_a_reauthentication_challenge(self, sso_account):
        response = _create_key(sso_account)

        assert response.status_code == 401
        assert response.json()["type"].endswith("idp-reauth-required")
        assert "insufficient_user_authentication" in response.headers["www-authenticate"]

    def test_the_authorization_request_asks_for_a_new_sign_in_no_older_than_a_minute(self, started):
        from urllib.parse import parse_qs, urlsplit

        query = parse_qs(urlsplit(started.authorization_url).query)

        assert query["prompt"] == ["login"]
        assert query["max_age"] == ["60"]

    def test_a_fresh_sign_in_of_the_linked_account_pays_for_one_request(self, sso_account, started):
        finished = sso_account.browser.finish(
            sso_account.slug, started, with_iss=True, email="sso-user@example.com", email_verified=True
        )

        ticket = finished.fragment["step_up_ticket"]
        assert finished.location.startswith("http") and "/settings/security#step_up_ticket=" in finished.location
        first = _create_key(sso_account, ticket)
        second = _create_key(sso_account, ticket)
        assert first.status_code == 201, first.text
        assert second.status_code == 403
        assert second.json()["type"].endswith("step-up-failed")

    def test_the_ticket_is_useless_without_the_verifier_of_its_challenge(self, sso_account, started):
        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)
        ticket = finished.fragment["step_up_ticket"]

        wrong = _create_key(sso_account, ticket, verifier="w" * 43)
        right = _create_key(sso_account, ticket)

        assert wrong.status_code == 403
        assert right.status_code == 201, right.text

    def test_a_ticket_pays_only_for_the_action_it_was_started_for(self, sso_account):
        response, flow = _start(sso_account, action="profile_export")
        finished = sso_account.browser.finish(sso_account.slug, flow, email="x@example.com", email_verified=True)

        refused = _create_key(sso_account, finished.fragment["step_up_ticket"])

        assert refused.status_code == 403
        assert response.status_code == 200

    def test_the_return_path_keeps_its_query_and_gets_the_ticket_in_the_fragment(self, sso_account):
        _, flow = _start(sso_account, redirect="/settings/security?tab=keys")

        finished = sso_account.browser.finish(sso_account.slug, flow, email="x@example.com", email_verified=True)

        assert "/settings/security?tab=keys#step_up_ticket=" in finished.location

    def test_userinfo_is_not_consulted(self, sso_account, started):
        provider = sso_account.browser.provider
        before = len(provider.requests_to("/userinfo"))

        sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert len(provider.requests_to("/userinfo")) == before


class TestRefusals:
    def test_a_sign_in_that_predates_the_step_up_is_not_fresh(self, sso_account, started, committed_sessions):
        sso_account.browser.provider.auth_time_age = 3600

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "not_fresh"}
        row = _only(audit(committed_sessions, STEP_UP_VERIFY))
        assert (row.outcome, row.details["reason"]) == ("failure", "not_fresh")

    def test_an_id_token_without_auth_time_is_not_fresh(self, sso_account, started):
        sso_account.browser.provider.id_token_claims = {"auth_time": None}
        provider = sso_account.browser.provider
        code, state = provider.authorize(started.authorization_url, email="x@example.com", email_verified=True)
        claims = provider.id_token_claims_for(client_id="endurain-client", nonce=started.nonce, access_token=None)
        del claims["auth_time"]
        provider.id_token_override = provider.sign(claims)

        finished = sso_account.browser.callback(sso_account.slug, state=state, code=code, binding=started.binding)

        assert finished.fragment == {"step_up_error": "not_fresh"}

    def test_an_id_token_whose_subject_is_blank_is_refused(self, sso_account, started):
        sso_account.browser.provider.sub = "  "

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "failed"}

    def test_a_sign_in_dated_in_the_future_is_not_fresh(self, sso_account, started):
        sso_account.browser.provider.auth_time_age = -3600

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "not_fresh"}

    def test_a_state_started_for_another_provider_is_refused_and_audited(
        self, sso_account, started, make_provider, committed_sessions, provider
    ):
        make_provider(
            "other",
            provider_type="oauth2",
            issuer_url=None,
            scopes="profile",
            token_endpoint=provider.token_endpoint,
        )
        code, state = provider.authorize(started.authorization_url, email="x@example.com", email_verified=True)

        finished = sso_account.browser.callback("other", state=state, code=code, binding=started.binding)

        assert finished.response.status_code == 400
        row = _only(audit(committed_sessions, STEP_UP_VERIFY))
        assert (row.outcome, row.details["reason"]) == ("failure", "invalid_state")

    def test_a_sign_in_of_another_provider_account_is_refused(self, sso_account, started, committed_sessions):
        sso_account.browser.provider.sub = "someone-else"

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "failed"}
        assert _only(audit(committed_sessions, STEP_UP_VERIFY)).details["reason"] == "not_linked"

    def test_a_provider_error_ends_in_a_failed_step_up(self, sso_account, started, committed_sessions):
        finished = sso_account.browser.callback(
            sso_account.slug, state=started.state, error="login_required", binding=started.binding
        )

        assert finished.fragment == {"step_up_error": "failed"}
        assert _only(audit(committed_sessions, STEP_UP_VERIFY)).details["reason"] == "provider_failure"

    def test_a_provider_that_refuses_the_code_ends_in_a_failed_step_up(self, sso_account, started):
        sso_account.browser.provider.token_status = 500

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "failed"}

    def test_a_provider_that_returns_no_id_token_ends_in_a_failed_step_up(self, sso_account, started):
        sso_account.browser.provider.issue_id_token = False

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "failed"}

    def test_the_callback_naming_another_issuer_is_refused(self, sso_account, started):
        provider = sso_account.browser.provider
        code, state = provider.authorize(started.authorization_url, email="x@example.com", email_verified=True)

        finished = sso_account.browser.callback(
            sso_account.slug, state=state, code=code, binding=started.binding, iss="https://evil.example"
        )

        assert finished.fragment == {"step_up_error": "failed"}

    def test_a_callback_from_another_browser_is_refused_without_naming_the_user_as_actor(
        self, sso_account, started, committed_sessions
    ):
        provider = sso_account.browser.provider
        code, state = provider.authorize(started.authorization_url)

        finished = sso_account.browser.callback(sso_account.slug, state=state, code=code, binding="elsewhere")

        assert finished.response.status_code == 400
        row = _only(audit(committed_sessions, STEP_UP_VERIFY))
        assert (row.outcome, row.details["reason"]) == ("denied", "browser_mismatch")

    def test_a_security_change_after_the_start_ends_the_step_up(self, sso_account, started, committed_sessions):
        import sqlalchemy as sa

        with committed_sessions() as db:
            user_id = db.scalar(
                sa.select(users_models.Users.id).where(users_models.Users.email == "sso-user@example.com")
            )
            security_generation_integration.stage_bump(user_id, db)
            db.commit()

        finished = sso_account.browser.finish(sso_account.slug, started, email="x@example.com", email_verified=True)

        assert finished.fragment == {"step_up_error": "failed"}
        assert _only(audit(committed_sessions, STEP_UP_VERIFY)).details["reason"] == "security_changed"


class TestStart:
    @pytest.mark.parametrize("redirect", ["https://evil.example", "//evil.example", "evil", "/a/../b", ""])
    def test_only_a_relative_path_is_accepted_as_the_return_path(self, redirect, sso_account):
        response, _ = _start(sso_account, redirect=redirect)

        assert response.status_code in (400, 422), response.text

    def test_a_malformed_challenge_is_refused(self, sso_account):
        response, _ = _start(sso_account, challenge="short")

        assert response.status_code == 422

    def test_an_unknown_action_is_refused(self, sso_account):
        response, _ = _start(sso_account, action="nonsense")

        assert response.status_code == 422

    def test_an_account_with_a_password_steps_up_with_it(self, sign_in, committed_sessions, make_provider):
        from tests._factories.identity_links import make_identity_link
        from tests._factories.users import make_user

        idp_id = make_provider("acme")
        with committed_sessions() as db:
            user = make_user(db)
            make_identity_link(db, user.id, idp_id, "s")
            db.commit()

        response = sign_in(user).client.post(
            f"/api/v1/profile/identity-providers/{idp_id}/step-up",
            json={"code_challenge": pkce_challenge(VERIFIER), "action": "api_key_create", "redirect": "/x"},
        )

        assert response.status_code == 409

    def test_a_provider_the_account_is_not_linked_to_is_not_found(self, sso_account, make_provider):
        import uuid

        sso_account.idp_id = uuid.uuid4()

        response, _ = _start(sso_account)

        assert response.status_code == 404

    def test_a_blank_return_path_is_refused(self, sso_account):
        response, _ = _start(sso_account, redirect=" ")

        assert response.status_code == 400

    def test_a_provider_the_account_has_not_linked_is_not_found(self, sso_account, make_provider, other_provider):
        unlinked = make_provider("unlinked", issuer_url=other_provider.issuer)
        sso_account.idp_id = unlinked

        response, _ = _start(sso_account)

        assert response.status_code == 404
        assert "not linked" in response.json()["detail"]

    def test_a_provider_without_an_issuer_cannot_confirm_a_sign_in(
        self, sso_account, make_provider, committed_sessions, provider
    ):
        import sqlalchemy as sa

        from tests._factories.identity_links import make_identity_link

        oauth2 = make_provider(
            "plain",
            provider_type="oauth2",
            issuer_url=None,
            scopes="profile",
            authorization_endpoint=provider.authorization_endpoint,
            token_endpoint=provider.token_endpoint,
            userinfo_endpoint=provider.userinfo_endpoint,
        )
        with committed_sessions() as db:
            user_id = db.scalar(
                sa.select(users_models.Users.id).where(users_models.Users.email == "sso-user@example.com")
            )
            make_identity_link(db, user_id, oauth2, "plain-subject")
            db.commit()
        sso_account.idp_id = oauth2

        response, _ = _start(sso_account)

        assert response.status_code == 400
        assert "issuer" in response.json()["detail"]
