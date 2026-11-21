"""Linking a provider to a signed-in account: the start, the provider callback and the link's own rules."""

import uuid

import pytest

import core.config as core_config
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.models as users_models
from tests._factories.identity_links import make_identity_link
from tests._factories.users import make_user
from tests.auth.identity_providers.conftest import API
from tests.auth.identity_providers.sso_helpers import audit, links_of

LINK = "auth.identity_link.link"
REVOKE = "auth.session.revoke"
NATIVE = "com.endurain.endurain:/auth/sso/callback"


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, email="linker@example.com")
        db.commit()
    return created


def _only(rows):
    assert len(rows) == 1, rows
    return rows[0]


def _profile_status(signed_in) -> int:
    return signed_in.client.get(f"{API}/profile").status_code


class TestLinking:
    def test_a_completed_link_ties_the_provider_account_to_the_user_and_returns_to_settings(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)

        start = mine.start_link(idp_id)
        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert start.response.status_code == 200, start.response.text
        assert finished.location.endswith("/settings/security?idp_link=success&idp_name=Provider+acme")
        link = _only(links_of(committed_sessions, idp_id))
        assert (link.user_id, link.idp_subject) == (user.id, "provider-subject-1")
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.target_id, row.actor_id) == ("success", str(user.id), str(user.id))
        listed = mine.signed_in.client.get(f"{API}/profile/identity-providers")
        assert [item["idp_id"] for item in listed.json()["items"]] == [str(idp_id)]

    def test_the_users_other_sessions_end_unless_the_client_asks_to_keep_them(
        self, user, link_browser, make_provider, sign_in
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        other = sign_in(user)

        start = mine.start_link(idp_id, revoke_other_sessions=True)
        mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert _profile_status(mine.signed_in) == 200
        assert _profile_status(other) == 401

    def test_the_other_sessions_survive_a_link_that_keeps_them(self, user, link_browser, make_provider, sign_in):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        other = sign_in(user)

        start = mine.start_link(idp_id, revoke_other_sessions=False)
        mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert _profile_status(other) == 200

    def test_ending_the_other_sessions_is_audited_next_to_the_link(
        self, user, link_browser, make_provider, sign_in, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        sign_in(user)

        start = mine.start_link(idp_id)
        mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert _only(audit(committed_sessions, REVOKE)).details == {"sessions_revoked": 1}

    def test_the_provider_profile_is_synced_onto_the_account_by_a_link(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme", sync_user_info=True)
        mine = link_browser(user)

        start = mine.start_link(idp_id)
        mine.finish("acme", start.started, name="Provider Name", email="p@example.com", email_verified=True)

        with committed_sessions() as db:
            assert db.get(users_models.Users, user.id).name == "Provider Name"

    def test_a_native_app_gets_a_single_use_ticket_that_binds_the_system_browser(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)

        start = mine.start_link(idp_id, redirect=NATIVE)

        assert start.response.status_code == 200, start.response.text
        ticket_url = start.response.json()["authorization_url"]
        assert ticket_url.startswith(f"{core_config.settings.ENDURAIN_HOST}/api/v1/public/idp/link?ticket=")
        assert start.response.cookies.get("endurain_idp_binding") is None
        path = ticket_url.removeprefix(core_config.settings.ENDURAIN_HOST)
        opened = mine.client.get(path, follow_redirects=False)
        assert opened.status_code == 307
        assert opened.headers["location"].startswith(mine.provider.authorization_endpoint)
        replay = mine.client.get(path, follow_redirects=False)
        assert replay.status_code == 400
        started = mine.started(opened)
        finished = mine.finish("acme", started, email="p@example.com", email_verified=True)
        assert finished.location.startswith(NATIVE)
        assert finished.query["idp_link"] == "success"
        assert len(links_of(committed_sessions, idp_id)) == 1

    def test_an_unknown_or_missing_ticket_is_refused_without_setting_a_cookie(self, link_browser, user):
        mine = link_browser(user)

        unknown = mine.client.get(f"{API}/public/idp/link", params={"ticket": "unknown"}, follow_redirects=False)
        missing = mine.client.get(f"{API}/public/idp/link", follow_redirects=False)

        assert unknown.status_code == 400
        assert "set-cookie" not in unknown.headers
        assert missing.status_code == 422


class TestStartRefusals:
    def test_a_wrong_password_starts_nothing(self, user, link_browser, make_provider, provider):
        idp_id = make_provider("acme")
        mine = link_browser(user)

        start = mine.start_link(idp_id, current_password="wrong")

        assert start.response.status_code == 403
        assert provider.requests == []

    def test_a_provider_the_account_already_has_is_a_conflict(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            make_identity_link(db, user.id, idp_id, "existing")
            db.commit()

        start = link_browser(user).start_link(idp_id)

        assert start.response.status_code == 409

    @pytest.mark.parametrize("enabled", [False, None])
    def test_a_disabled_or_unknown_provider_is_not_found(self, enabled, user, link_browser, make_provider):
        idp_id = make_provider("acme", enabled=False) if enabled is False else uuid.uuid4()

        assert link_browser(user).start_link(idp_id).response.status_code == 404

    @pytest.mark.parametrize("redirect", ["https://evil.example/x", "//evil.example", "http://x/y", "/a/../b"])
    def test_a_foreign_redirect_is_refused(self, redirect, user, link_browser, make_provider):
        idp_id = make_provider("acme")

        assert link_browser(user).start_link(idp_id, redirect=redirect).response.status_code == 400


class TestCallbackRefusals:
    def test_a_subject_linked_to_another_account_is_refused_and_audited(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            owner = make_user(db)
            make_identity_link(db, owner.id, idp_id, "provider-subject-1")
            db.commit()
        mine = link_browser(user)

        start = mine.start_link(idp_id)
        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        assert [link.user_id for link in links_of(committed_sessions, idp_id)] == [owner.id]
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.details["reason"]) == ("denied", "linked_to_another_account")

    def test_a_subject_the_account_linked_meanwhile_is_a_refused_repeat(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        with committed_sessions() as db:
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        row = _only(audit(committed_sessions, LINK))
        assert row.details["reason"] == "already_linked_to_this_account"

    def test_a_provider_that_answers_with_an_error_links_nothing(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)

        finished = mine.callback(
            "acme", state=start.started.state, error="access_denied", binding=start.started.binding
        )

        assert finished.query["idp_link"] == "error"
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.details["reason"], row.actor_id) == ("failure", "provider_error", str(user.id))

    def test_a_refused_code_exchange_links_nothing(
        self, user, link_browser, make_provider, provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        provider.token_status = 500
        mine = link_browser(user)
        start = mine.start_link(idp_id)

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        assert links_of(committed_sessions, idp_id) == []
        assert _only(audit(committed_sessions, LINK)).details["reason"] == "token_exchange_failed"

    def test_an_id_token_that_does_not_verify_links_nothing(
        self, user, link_browser, make_provider, provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        code, state = provider.authorize(start.started.authorization_url, email="p@example.com", email_verified=True)
        claims = provider.id_token_claims_for(client_id="endurain-client", nonce="not-the-nonce", access_token=None)
        provider.id_token_override = provider.sign(claims)

        finished = mine.callback("acme", state=state, code=code, binding=start.started.binding)

        assert finished.query["idp_link"] == "error"
        assert links_of(committed_sessions, idp_id) == []

    def test_a_link_state_used_at_another_provider_is_refused_and_audited(
        self, user, link_browser, make_provider, committed_sessions, provider
    ):
        idp_id = make_provider("acme")
        make_provider(
            "other", provider_type="oauth2", issuer_url=None, scopes="profile", token_endpoint=provider.token_endpoint
        )
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        code, state = provider.authorize(start.started.authorization_url)

        finished = mine.callback("other", state=state, code=code, binding=start.started.binding)

        assert finished.response.status_code == 400
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.details["reason"]) == ("failure", "invalid_state")

    def test_a_callback_from_another_browser_is_refused_and_audited_with_the_user_as_target_only(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        code, state = mine.provider.authorize(start.started.authorization_url)

        finished = mine.callback("acme", state=state, code=code, binding="victims-browser")

        assert finished.response.status_code == 400
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.details["reason"], row.target_id) == ("denied", "browser_mismatch", str(user.id))
        assert row.actor_id != str(user.id)

    def test_a_link_started_before_a_security_change_cannot_complete(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(user.id, db)
            db.commit()

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        assert links_of(committed_sessions, idp_id) == []
        assert _only(audit(committed_sessions, LINK)).details["reason"] == "security_changed"

    def test_a_link_whose_session_has_ended_cannot_complete(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        with committed_sessions() as db:
            sessions_integration.delete_session(mine.signed_in.session_id, user.id, db)
            db.commit()

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        assert links_of(committed_sessions, idp_id) == []
        assert _only(audit(committed_sessions, LINK)).details["reason"] == "session_ended"

    def test_a_link_for_an_account_deactivated_meanwhile_cannot_complete(
        self, user, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        with committed_sessions() as db:
            db.get(users_models.Users, user.id).active = False
            db.commit()

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.query["idp_link"] == "error"
        assert _only(audit(committed_sessions, LINK)).details["reason"] == "user_inactive"

    def test_a_link_for_an_account_deleted_meanwhile_cannot_complete(
        self, user, link_browser, make_provider, committed_sessions
    ):
        import sqlalchemy as sa

        idp_id = make_provider("acme")
        mine = link_browser(user)
        start = mine.start_link(idp_id)
        with committed_sessions() as db:
            db.execute(sa.delete(users_models.Users).where(users_models.Users.id == user.id))
            db.commit()

        finished = mine.finish("acme", start.started, email="p@example.com", email_verified=True)

        assert finished.response.status_code == 400
        assert links_of(committed_sessions, idp_id) == []


class TestUnlinking:
    def test_unlinking_removes_the_link_and_ends_the_sessions_that_signed_in_through_it(
        self, browser, link_browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            member = make_user(db, email="member@example.com")
            make_identity_link(db, member.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"email": "member@example.com", "email_verified": True}
        _, finished = browser.sign_in("acme")
        via_provider = browser.exchange(finished.session_id).json()["access_token"]
        mine = link_browser(member)
        from tests._factories.users import PASSWORD

        response = mine.signed_in.client.post(
            f"{API}/profile/identity-providers/{idp_id}/unlink", json={"step_up": {"current_password": PASSWORD}}
        )

        assert response.status_code == 204, response.text
        assert links_of(committed_sessions, idp_id) == []
        assert _profile_status(mine.signed_in) == 200
        ended = browser.client.get(f"{API}/profile", headers={"Authorization": f"Bearer {via_provider}"})
        assert ended.status_code == 401
        assert _only(audit(committed_sessions, "auth.identity_link.unlink")).target_id == str(member.id)

    def test_an_account_without_a_password_keeps_its_only_provider(
        self, browser, make_provider, committed_sessions, sign_in, sso_sign_up
    ):
        idp_id = make_provider("acme")
        browser.provider.claims = {"email": "only@example.com", "email_verified": True}
        _, finished = browser.sign_in("acme")
        tokens = browser.exchange(finished.session_id).json()

        response = browser.client.post(
            f"{API}/profile/identity-providers/{idp_id}/unlink",
            json={"step_up": {}},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 409, response.text
        assert len(links_of(committed_sessions, idp_id)) == 1

    def test_a_provider_the_account_is_not_linked_to_is_not_found(self, user, link_browser, make_provider):
        from tests._factories.users import PASSWORD

        idp_id = make_provider("acme")

        response = link_browser(user).signed_in.client.post(
            f"{API}/profile/identity-providers/{idp_id}/unlink", json={"step_up": {"current_password": PASSWORD}}
        )

        assert response.status_code == 404
