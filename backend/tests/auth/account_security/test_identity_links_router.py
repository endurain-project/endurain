"""The signed-in user's identity-provider links: list, link, unlink and the step-up of an account without a password."""

import uuid

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.dependencies as identity_providers_dependencies
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.sessions.audit_actions as sessions_audit_actions
from tests._factories.account_security import (
    deliver_notices,
    make_oidc_provider,
    sent_to,
    session_ids,
    step_up_proof,
)
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.tokens import audit_rows, make_mfa, totp_code
from tests._factories.users import PASSWORD, make_user
from tests.auth.authentication.conftest import make_sso_session

_PROVIDERS = f"{core_config.ROOT_PATH}/profile/identity-providers"
_STEP_UP = {"current_password": PASSWORD}
_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _provider(committed_sessions, *, enabled: bool = True) -> uuid.UUID:
    with committed_sessions() as db:
        idp_id = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:10]}")
        if not enabled:
            db.execute(sa.text("UPDATE identity_providers SET enabled = false WHERE id = :id"), {"id": idp_id})
        db.commit()
    return idp_id


def _states(committed_sessions, user_id: uuid.UUID) -> list[oauth_state_models.OAuthState]:
    with committed_sessions() as db:
        return list(
            db.scalars(sa.select(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.user_id == user_id))
        )


def _user(committed_sessions, sign_in, **options):
    with committed_sessions() as db:
        user = make_user(db, **options)
        db.commit()
    return sign_in(user)


class TestList:
    def test_a_users_links_are_listed_with_their_provider(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)
        idp_id = _provider(committed_sessions)
        with committed_sessions() as db:
            make_identity_link(db, owner.user.id, idp_id, "subject-1")
            db.commit()

        body = owner.client.get(_PROVIDERS).json()

        assert body["total"] == 1
        (item,) = body["items"]
        assert (item["idp_id"], item["idp_slug"].startswith("idp-")) == (str(idp_id), True)

    def test_another_users_links_are_not_listed(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)
        stranger = _user(committed_sessions, sign_in)
        with committed_sessions() as db:
            make_identity_link(db, stranger.user.id, _provider(committed_sessions), "subject-2")
            db.commit()

        assert owner.client.get(_PROVIDERS).json()["items"] == []


class TestStartLink:
    def test_a_web_link_returns_the_provider_url_binds_the_browser_and_stages_the_state(
        self, committed_sessions, sign_in
    ):
        owner = _user(committed_sessions, sign_in)
        idp_id = _provider(committed_sessions)

        response = owner.client.post(
            f"{_PROVIDERS}/{idp_id}/link", json={"step_up": _STEP_UP, "redirect": "/settings/security"}
        )

        assert response.status_code == 200
        assert response.json()["authorization_url"].startswith("https://idp.example.com/authorize?")
        assert response.cookies.get(identity_providers_dependencies.BINDING_COOKIE_NAME)
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        (state,) = _states(committed_sessions, owner.user.id)
        assert (state.idp_id, state.session_id, state.ends_other_sessions, state.redirect_path) == (
            idp_id,
            owner.session_id,
            True,
            "/settings/security",
        )
        assert owner.client.get(_PROVIDERS).json()["items"] == []

    def test_the_choice_to_keep_the_other_sessions_is_stored_with_the_state(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)

        owner.client.post(
            f"{_PROVIDERS}/{_provider(committed_sessions)}/link",
            json={"step_up": _STEP_UP, "revoke_other_sessions": False},
        )

        (state,) = _states(committed_sessions, owner.user.id)
        assert state.ends_other_sessions is False

    def test_a_native_app_redirect_gets_a_single_use_ticket_url_and_no_cookie(
        self, committed_sessions, sign_in, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "ALLOWED_REDIRECT_URIS", {"com.example.app:/callback"})
        owner = _user(committed_sessions, sign_in)

        response = owner.client.post(
            f"{_PROVIDERS}/{_provider(committed_sessions)}/link",
            json={"step_up": _STEP_UP, "redirect": "com.example.app:/callback"},
        )

        assert response.status_code == 200
        url = response.json()["authorization_url"]
        assert url.startswith(f"{core_config.settings.ENDURAIN_HOST}{core_config.ROOT_PATH}/public/idp/link?ticket=")
        assert "set-cookie" not in response.headers

    def test_a_redirect_to_another_site_is_refused(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)

        response = owner.client.post(
            f"{_PROVIDERS}/{_provider(committed_sessions)}/link",
            json={"step_up": _STEP_UP, "redirect": "https://evil.example.com/"},
        )

        assert response.status_code == 422 or response.status_code == 400
        assert _states(committed_sessions, owner.user.id) == []

    def test_an_already_linked_provider_is_a_conflict_that_costs_no_step_up_attempt(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)
        idp_id = _provider(committed_sessions)
        with committed_sessions() as db:
            make_identity_link(db, owner.user.id, idp_id, "subject")
            db.commit()

        response = owner.client.post(f"{_PROVIDERS}/{idp_id}/link", json={"step_up": {"current_password": "wrong"}})

        assert response.status_code == 409
        assert _states(committed_sessions, owner.user.id) == []

    @pytest.mark.parametrize("known", [False, True], ids=["unknown", "disabled"])
    def test_an_unknown_or_disabled_provider_is_not_found(self, committed_sessions, sign_in, known):
        owner = _user(committed_sessions, sign_in)
        idp_id = _provider(committed_sessions, enabled=False) if known else uuid.uuid4()

        response = owner.client.post(f"{_PROVIDERS}/{idp_id}/link", json={"step_up": _STEP_UP})

        assert response.status_code == 404

    def test_a_wrong_password_stages_nothing(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)

        response = owner.client.post(
            f"{_PROVIDERS}/{_provider(committed_sessions)}/link", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert _states(committed_sessions, owner.user.id) == []

    @pytest.mark.parametrize(
        "body",
        [{"redirect": ""}, {"link_token": "x"}, {"unexpected": 1}],
        ids=["empty-redirect", "old-token-field", "unknown-field"],
    )
    def test_a_malformed_request_is_refused(self, committed_sessions, sign_in, body):
        owner = _user(committed_sessions, sign_in)

        response = owner.client.post(
            f"{_PROVIDERS}/{_provider(committed_sessions)}/link", json={"step_up": _STEP_UP, **body}
        )

        assert response.status_code == 422

    def test_a_malformed_provider_id_is_refused(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)

        assert owner.client.post(f"{_PROVIDERS}/3/link", json={"step_up": _STEP_UP}).status_code == 422
        assert owner.client.post(f"{_PROVIDERS}/3/unlink", json={"step_up": _STEP_UP}).status_code == 422

    def test_the_old_token_route_and_an_unauthenticated_get_are_gone(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)
        url = f"{_PROVIDERS}/{uuid.uuid4()}/link"

        assert owner.client.post(f"{url}/token", json={"current_password": "pw"}).status_code == 404
        assert owner.client.get(url, params={"link_token": "x"}).status_code in (404, 405)


class TestStartStepUp:
    def _passwordless(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db, with_password=False)
            idp_id = make_oidc_provider(db, f"idp-{uuid.uuid4().hex[:10]}")
            make_identity_link(db, user.id, idp_id, "subject")
            db.commit()
        return sign_in(user), idp_id

    def _start(self, owner, idp_id, **overrides):
        body = {
            "code_challenge": _CHALLENGE,
            "action": identity_providers_constants.StepUpAction.MFA_DISABLE.value,
            "redirect": "/settings/security",
        } | overrides
        return owner.client.post(f"{_PROVIDERS}/{idp_id}/step-up", json=body)

    def test_the_url_is_returned_the_browser_is_bound_and_the_state_names_session_and_action(
        self, committed_sessions, sign_in
    ):
        owner, idp_id = self._passwordless(committed_sessions, sign_in)

        response = self._start(owner, idp_id)

        assert response.status_code == 200
        assert "prompt=login" in response.json()["authorization_url"]
        assert response.cookies.get(identity_providers_dependencies.BINDING_COOKIE_NAME)
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        (state,) = _states(committed_sessions, owner.user.id)
        assert (state.session_id, state.action, state.code_challenge, state.idp_id) == (
            owner.session_id,
            "mfa_disable",
            _CHALLENGE,
            idp_id,
        )

    def test_an_account_with_a_password_steps_up_with_it_instead(self, committed_sessions, sign_in):
        owner = _user(committed_sessions, sign_in)

        response = self._start(owner, _provider(committed_sessions))

        assert response.status_code == 409
        assert response.json()["detail"] == "This account confirms sensitive changes with its password"
        assert _states(committed_sessions, owner.user.id) == []

    def test_a_provider_the_user_is_not_linked_to_stages_nothing(self, committed_sessions, sign_in):
        owner, _ = self._passwordless(committed_sessions, sign_in)

        response = self._start(owner, _provider(committed_sessions))

        assert response.status_code in (404, 409)
        assert _states(committed_sessions, owner.user.id) == []

    @pytest.mark.parametrize(
        "body",
        [
            {"code_challenge": "short"},
            {"action": "password_change"},
            {"redirect": None},
            {"extra": 1},
        ],
        ids=["short-challenge", "unknown-action", "no-redirect", "unknown-field"],
    )
    def test_a_malformed_request_is_refused(self, committed_sessions, sign_in, body):
        owner, idp_id = self._passwordless(committed_sessions, sign_in)
        request = {"code_challenge": _CHALLENGE, "action": "mfa_disable", "redirect": "/"} | body
        request = {key: value for key, value in request.items() if value is not None}

        response = owner.client.post(f"{_PROVIDERS}/{idp_id}/step-up", json=request)

        assert response.status_code == 422

    def test_a_locked_out_session_cannot_start_another_sign_in(self, committed_sessions, sign_in):
        owner, idp_id = self._passwordless(committed_sessions, sign_in)
        for _ in range(5):
            owner.client.post(
                f"{core_config.ROOT_PATH}/profile/api-keys",
                json={
                    "name": "k",
                    "scopes": ["account"],
                    "step_up": {"idp_reauth": {"ticket": "t" * 43, "code_verifier": "v" * 43}},
                },
            )

        response = self._start(owner, idp_id)

        assert response.status_code == 429
        assert _states(committed_sessions, owner.user.id) == []

    @pytest.mark.parametrize(
        "action",
        [
            "admin_credential_reset",
            "admin_mfa_reset",
            "admin_credential_change_require",
            "admin_user_edit",
            "admin_user_delete",
            "admin_idp_unlink",
            "admin_user_create",
            "admin_idp_create",
            "admin_idp_edit",
        ],
    )
    def test_an_administrator_action_can_be_started_by_an_account_without_a_password(
        self, committed_sessions, sign_in, action
    ):
        owner, idp_id = self._passwordless(committed_sessions, sign_in)

        assert self._start(owner, idp_id, action=action).status_code == 200


class TestUnlink:
    def _linked(self, committed_sessions, sign_in, *, with_password: bool = True, mfa: bool = False):
        with committed_sessions() as db:
            user = make_user(db, with_password=with_password)
            factors = make_mfa(db, user) if mfa else None
            idp_id = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:10]}")
            make_identity_link(db, user.id, idp_id, "subject")
            db.commit()
        return sign_in(user), sign_in(user), idp_id, factors

    def test_the_link_goes_with_the_sessions_signed_in_through_it_and_the_owner_is_told(
        self, committed_sessions, sign_in
    ):
        deliver_notices()
        here, _there, idp_id, _ = self._linked(committed_sessions, sign_in)

        response = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert here.client.get(_PROVIDERS).json()["items"] == []
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.IDENTITY_LINK_UNLINK)
        assert (row.outcome, row.target_id, row.details["idp_id"]) == ("success", str(here.user.id), str(idp_id))
        assert len(sent_to(here.user.email)) == 1
        assert session_ids(committed_sessions, here.user.id) >= {here.session_id}

    def test_the_account_keeps_a_way_to_sign_in_a_second_provider_counts(self, committed_sessions, sign_in):
        here, _, idp_id, _ = self._linked(committed_sessions, sign_in, with_password=False)
        with committed_sessions() as db:
            other = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:10]}")
            make_identity_link(db, here.user.id, other, "subject-b")
            db.commit()
            proof = step_up_proof(
                db, here.user, here.session_id, idp_id, action=identity_providers_constants.StepUpAction.IDP_UNLINK
            )

        response = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": {"idp_reauth": proof}})

        assert response.status_code == 204
        assert [item["idp_id"] for item in here.client.get(_PROVIDERS).json()["items"]] == [str(other)]

    def test_the_last_sign_in_method_cannot_be_unlinked_and_no_step_up_is_spent(self, committed_sessions, sign_in):
        here, _, idp_id, _ = self._linked(committed_sessions, sign_in, with_password=False)
        with committed_sessions() as db:
            proof = step_up_proof(
                db, here.user, here.session_id, idp_id, action=identity_providers_constants.StepUpAction.IDP_UNLINK
            )

        refused = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": {"idp_reauth": proof}})

        assert refused.status_code == 409
        assert refused.json()["type"] == "urn:endurain:error:last-sign-in-method"
        assert len(here.client.get(_PROVIDERS).json()["items"]) == 1

    def test_a_link_to_a_disabled_provider_does_not_count_as_a_way_to_sign_in(self, committed_sessions, sign_in):
        here, _, idp_id, _ = self._linked(committed_sessions, sign_in, with_password=False)
        disabled = _provider(committed_sessions, enabled=False)
        with committed_sessions() as db:
            make_identity_link(db, here.user.id, disabled, "subject-c")
            db.commit()

        response = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": {}})

        assert response.status_code == 409

    def test_an_unknown_provider_and_an_unlinked_one_are_not_found(self, committed_sessions, sign_in):
        here, _, _, _ = self._linked(committed_sessions, sign_in)

        unknown = here.client.post(f"{_PROVIDERS}/{uuid.uuid4()}/unlink", json={"step_up": _STEP_UP})
        unlinked = here.client.post(f"{_PROVIDERS}/{_provider(committed_sessions)}/unlink", json={"step_up": _STEP_UP})

        assert (unknown.status_code, unlinked.status_code) == (404, 404)

    def test_a_wrong_password_keeps_the_link(self, committed_sessions, sign_in):
        here, _, idp_id, _ = self._linked(committed_sessions, sign_in)

        response = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": {"current_password": "wrong"}})

        assert response.status_code == 403
        assert len(here.client.get(_PROVIDERS).json()["items"]) == 1

    def test_an_account_with_mfa_also_needs_a_code(self, committed_sessions, sign_in):
        here, _, idp_id, factors = self._linked(committed_sessions, sign_in, mfa=True)

        refused = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": _STEP_UP})
        accepted = here.client.post(
            f"{_PROVIDERS}/{idp_id}/unlink",
            json={"step_up": {**_STEP_UP, "mfa_code": totp_code(factors.secret, steps_ahead=1)}},
        )

        assert (refused.status_code, accepted.status_code) == (403, 204)


class TestUnlinkEndsProviderSessions:
    def test_the_sessions_signed_in_through_the_provider_end_and_are_audited_as_a_revocation(
        self, committed_sessions, sign_in
    ):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        # The callback's own step links the user to a new provider and signs them in through it.
        through_idp = make_sso_session(committed_sessions, user)
        with committed_sessions() as db:
            idp_id = db.scalars(sa.select(identity_link_models.IdentityLink.idp_id)).first()
            make_identity_link(db, user.id, make_identity_provider(db, f"idp-{uuid.uuid4().hex[:10]}"), "other")
            db.commit()
        here = sign_in(user)

        response = here.client.post(f"{_PROVIDERS}/{idp_id}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert session_ids(committed_sessions, user.id) == {here.session_id}
        assert through_idp not in session_ids(committed_sessions, user.id)
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_id, row.details["sessions_revoked"]) == (str(user.id), 1)


class TestIdentityLinkCounts:
    def test_users_are_counted_by_their_links_and_those_without_any_are_absent(self, db):
        linked, unlinked = make_user(db), make_user(db)
        for index in range(2):
            make_identity_link(db, linked.id, make_identity_provider(db, f"count-{uuid.uuid4().hex[:8]}"), f"s{index}")

        counts = identity_link_service.get_identity_link_counts_for_users([linked.id, unlinked.id], db)

        assert counts == {linked.id: 2}
