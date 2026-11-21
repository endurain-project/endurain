"""Signing in through a provider over HTTP: the login redirect, the callback, account matching and provisioning."""

import time
import uuid

import pytest
from sqlalchemy import select

import modules.users.users.models as users_models
from tests._factories.identity_links import make_identity_link
from tests._factories.users import make_user
from tests.auth.identity_providers.conftest import API, VERIFIER, Browser
from tests.auth.identity_providers.fake_provider import CLIENT_ID
from tests.auth.identity_providers.sso_helpers import audit, links_of, users_by_email

LOGIN = "auth.session.login"
LINK = "auth.identity_link.link"
NATIVE = "com.endurain.endurain:/auth/sso/callback"

pytestmark = pytest.mark.usefixtures("sso_sign_up")


def provider_endpoint(browser) -> str:
    return browser.provider.token_endpoint


def _only(rows):
    assert len(rows) == 1, rows
    return rows[0]


def _error(finished) -> str:
    assert finished.response.status_code == 307, finished.response.text
    assert finished.location.startswith("http"), finished.location
    return finished.query.get("error", "")


class TestFirstSignIn:
    def test_the_account_is_created_from_the_claims_and_the_exchange_hands_out_tokens(
        self, browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme")
        browser.provider.claims = {
            "email": "new@example.com",
            "email_verified": True,
            "name": "New Person",
            "preferred_username": "newbie",
        }

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success", finished.location
        user = _only(users_by_email(committed_sessions, "new@example.com"))
        assert (user.username, user.name, user.email_verified, user.active) == ("newbie", "New Person", True, True)
        assert _only(links_of(committed_sessions, idp_id)).idp_subject == "provider-subject-1"
        exchanged = browser.exchange(finished.session_id)
        assert exchanged.status_code == 200, exchanged.text
        assert exchanged.json()["access_token"]
        assert exchanged.headers["Cache-Control"].startswith("no-store")
        link_row = _only(audit(committed_sessions, LINK))
        assert link_row.outcome == "success"
        assert link_row.target_id == str(user.id)

    def test_the_provider_receives_the_clients_credentials_and_the_pkce_verifier(self, browser, make_provider):
        make_provider("acme")
        browser.provider.claims = {"email": "pkce@example.com", "email_verified": True}

        browser.sign_in("acme")

        (_, _, form, headers) = browser.provider.requests_to("/token")[0]
        assert form["grant_type"] == "authorization_code"
        assert form["code_verifier"]
        assert headers["authorization"].startswith("Basic ")

    def test_a_second_sign_in_reaches_the_same_account(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        browser.provider.claims = {"email": "twice@example.com", "email_verified": True}
        first = browser.sign_in("acme")[1]
        assert browser.exchange(first.session_id).status_code == 200

        second = browser.sign_in("acme")[1]

        assert second.query["sso"] == "success"
        assert browser.exchange(second.session_id).status_code == 200
        assert len(users_by_email(committed_sessions, "twice@example.com")) == 1
        link = _only(links_of(committed_sessions, idp_id))
        assert link.last_login is not None

    def test_a_username_another_account_holds_gets_a_numeric_suffix(self, browser, make_provider, committed_sessions):
        make_provider("acme")
        with committed_sessions() as db:
            make_user(db, username="taken")
            db.commit()
        browser.provider.claims = {"email": "dup@example.com", "email_verified": True, "preferred_username": "taken"}

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success"
        user = _only(users_by_email(committed_sessions, "dup@example.com"))
        assert user.username.startswith("taken_")
        assert user.username != "taken"

    def test_an_email_claim_is_never_used_as_the_username(self, browser, make_provider, committed_sessions):
        make_provider("acme")
        browser.provider.claims = {"email": "private.person@example.com", "email_verified": True}

        browser.sign_in("acme")

        user = _only(users_by_email(committed_sessions, "private.person@example.com"))
        assert "@" not in user.username
        assert "private" not in user.username

    def test_a_native_redirect_starts_a_mobile_sign_in_that_only_a_mobile_client_redeems(self, browser, make_provider):
        make_provider("acme")
        browser.provider.claims = {"email": "app@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme", redirect=NATIVE)

        assert finished.query["external_redirect"] == "true"
        assert finished.query["redirect"] == NATIVE
        assert browser.exchange(finished.session_id).status_code == 400
        from modules.auth.constants import ClientType

        mobile = browser.exchange(finished.session_id, client_type=ClientType.MOBILE)
        assert mobile.status_code == 200, mobile.text
        assert mobile.json()["refresh_token"]

    def test_a_relative_redirect_comes_back_encoded_to_the_frontend(self, browser, make_provider):
        make_provider("acme")
        browser.provider.claims = {"email": "back@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme", redirect="/activities?x=1&y=2")

        assert finished.query["redirect"] == "/activities?x=1&y=2"
        assert "external_redirect" not in finished.query


class TestAccountMatching:
    def test_an_account_with_the_same_verified_email_is_linked_when_the_sign_in_completes(
        self, browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme", link_by_email=True)
        with committed_sessions() as db:
            existing = make_user(db, email="match@example.com", email_verified=True)
            db.commit()
        browser.provider.claims = {"email": "match@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success"
        assert links_of(committed_sessions, idp_id) == []
        assert browser.exchange(finished.session_id).status_code == 200
        link = _only(links_of(committed_sessions, idp_id))
        assert link.user_id == existing.id
        assert _only(audit(committed_sessions, LINK)).target_id == str(existing.id)

    def test_a_provider_that_does_not_link_by_email_refuses_the_match_and_changes_nothing(
        self, browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme", link_by_email=False)
        with committed_sessions() as db:
            make_user(db, email="match@example.com", email_verified=True)
            db.commit()
        browser.provider.claims = {"email": "match@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_link_by_email_disabled"
        assert links_of(committed_sessions, idp_id) == []
        row = _only(audit(committed_sessions, LINK))
        assert (row.outcome, row.details["reason"]) == ("denied", "link_by_email_disabled")

    def test_an_email_the_provider_did_not_verify_is_refused_whether_or_not_an_account_has_it(
        self, browser, make_provider, committed_sessions
    ):
        make_provider("acme", link_by_email=True)
        with committed_sessions() as db:
            make_user(db, email="held@example.com", email_verified=True)
            db.commit()
        errors = []
        for email in ("held@example.com", "free@example.com"):
            browser.provider.claims = {"email": email, "email_verified": False}
            errors.append(_error(browser.sign_in("acme")[1]))

        assert errors == ["sso_email_unverified", "sso_email_unverified"]
        assert users_by_email(committed_sessions, "free@example.com") == []
        assert len(audit(committed_sessions, LOGIN)) == 0 or all(
            row.outcome != "success" for row in audit(committed_sessions, LOGIN)
        )

    def test_a_local_account_whose_email_is_unverified_is_not_taken_over(
        self, browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme", link_by_email=True)
        with committed_sessions() as db:
            make_user(db, email="claimed@example.com", email_verified=False)
            db.commit()
        browser.provider.claims = {"email": "claimed@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_failed"
        assert links_of(committed_sessions, idp_id) == []
        assert _only(audit(committed_sessions, LINK)).details["reason"] == "account_email_unverified"

    def test_a_linked_account_signs_in_whatever_its_email_now_is(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            user = make_user(db, email="old@example.com")
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"email": "changed@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success"
        assert browser.exchange(finished.session_id).status_code == 200
        assert users_by_email(committed_sessions, "changed@example.com") == []

    def test_the_provider_without_an_email_cannot_create_an_account(self, browser, make_provider, committed_sessions):
        make_provider("acme")
        browser.provider.claims = {"name": "No Mail"}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_email_missing"
        assert links_of(committed_sessions) == []

    @pytest.mark.parametrize("where", ["server", "provider"])
    def test_account_creation_needs_both_the_server_and_the_provider(
        self, where, browser, make_provider, committed_sessions
    ):
        from tests._factories.server_settings import edit_server_settings

        make_provider("acme", auto_create_users=where != "provider")
        if where == "server":
            with committed_sessions() as db:
                edit_server_settings(db, signup_sso_enabled=False)
                db.commit()
        browser.provider.claims = {"email": "nobody@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_auto_create_disabled"
        assert users_by_email(committed_sessions, "nobody@example.com") == []


class TestNewAccountsThatAreNotActiveYet:
    def test_an_email_the_provider_verified_satisfies_the_verification_the_server_requires(
        self, browser, make_provider, committed_sessions
    ):
        from tests._factories.server_settings import edit_server_settings

        make_provider("acme")
        with committed_sessions() as db:
            edit_server_settings(db, signup_require_email_verification=True)
            db.commit()
        browser.provider.claims = {"email": "verified@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success"
        assert _only(users_by_email(committed_sessions, "verified@example.com")).active is True

    def test_an_account_that_awaits_administrator_approval_is_created_but_not_signed_in(
        self, browser, make_provider, committed_sessions
    ):
        from tests._factories.server_settings import edit_server_settings

        make_provider("acme")
        with committed_sessions() as db:
            edit_server_settings(db, signup_require_admin_approval=True)
            db.commit()
        browser.provider.claims = {"email": "waiting@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_approval_pending"
        user = _only(users_by_email(committed_sessions, "waiting@example.com"))
        assert user.active is False
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"]) == ("denied", "inactive")


class TestMalformedProviderAnswers:
    def test_a_claim_of_the_wrong_type_ends_in_a_login_error_and_creates_nobody(
        self, browser, make_provider, committed_sessions
    ):
        make_provider("acme")

        _, finished = browser.sign_in("acme", email=12345, email_verified=True)

        assert _error(finished) == "sso_failed"
        assert links_of(committed_sessions) == []

    @pytest.mark.parametrize("sid", [7, "x" * 300, ""])
    def test_a_provider_session_id_that_is_unusable_is_not_stored(
        self, sid, browser, make_provider, committed_sessions
    ):
        import sqlalchemy as sa

        import modules.auth.identity_provider_links.models as links_models

        make_provider("acme")

        _, finished = browser.sign_in("acme", email="sid@example.com", email_verified=True, sid=sid)

        assert finished.query["sso"] == "success"
        with committed_sessions() as db:
            assert db.scalar(sa.select(links_models.IdpSessionToken.idp_sid)) is None

    def test_a_provider_with_an_issuer_but_no_id_token_still_discovers_its_endpoints(
        self, browser, make_provider, provider, committed_sessions
    ):
        idp_id = make_provider("gh", provider_type="oauth2", scopes="read:user user:email")

        _, finished = browser.sign_in("gh", sub="42", email="disc@example.com", email_verified=True)

        assert finished.query["sso"] == "success", finished.location
        assert _only(links_of(committed_sessions, idp_id)).idp_subject == "42"


class TestUserinfoThatFails:
    @pytest.mark.parametrize(
        "break_it",
        [
            lambda provider: setattr(provider, "userinfo_body", b"<html>not json</html>"),
            lambda provider: setattr(provider, "discovery", {"userinfo_endpoint": "http://127.0.0.1:9/userinfo"}),
        ],
        ids=["not-json", "unreachable"],
    )
    def test_an_unreadable_or_unreachable_userinfo_leaves_the_verified_id_token_in_charge(
        self, break_it, browser, make_provider, provider, committed_sessions
    ):
        make_provider("acme")
        break_it(provider)

        _, finished = browser.sign_in("acme", email="info@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        assert len(users_by_email(committed_sessions, "info@example.com")) == 1

    def test_a_userinfo_endpoint_that_answers_too_slowly_leaves_the_verified_id_token_in_charge(
        self, browser, make_provider, provider, committed_sessions, monkeypatch
    ):
        import modules.auth.identity_providers.oidc_client_service as oidc_client_service

        make_provider("acme")
        provider.delays = {"/userinfo": 0.6}
        original = oidc_client_service.OidcClientService.create_oauth_client

        def impatient(self, *args, **kwargs):
            oauth_client = original(self, *args, **kwargs)
            oauth_client.timeout = 0.2
            return oauth_client

        monkeypatch.setattr(oidc_client_service.OidcClientService, "create_oauth_client", impatient)

        _, finished = browser.sign_in("acme", email="slow@example.com", email_verified=True)

        assert finished.query["sso"] == "success"

    def test_a_userinfo_endpoint_on_a_private_address_the_guard_refuses_ends_the_login_in_error(
        self, browser, make_provider, provider, monkeypatch
    ):
        import core.config as core_config

        make_provider("acme")
        provider.discovery = {"userinfo_endpoint": "http://127.0.0.2:1/userinfo"}
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.1"])

        _, finished = browser.sign_in("acme", email="guard@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"

    def test_a_manually_configured_userinfo_endpoint_wins_over_the_discovered_one(
        self, browser, make_provider, provider
    ):
        make_provider("acme", userinfo_endpoint=provider.userinfo_endpoint)
        provider.discovery = {"userinfo_endpoint": "http://127.0.0.1:9/userinfo"}

        _, finished = browser.sign_in("acme", email="own@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        assert len(provider.requests_to("/userinfo")) == 1


class TestADatabaseFailureAfterTheStateWasClaimed:
    def test_a_session_that_cannot_be_stored_ends_in_a_login_error_and_the_state_cannot_be_replayed(
        self, browser, make_provider, failing_table, committed_sessions
    ):
        make_provider("acme")
        failing_table.fail("users_sessions", "INSERT")
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url, email="db@example.com", email_verified=True)

        failed = browser.callback("acme", state=state, code=code, binding=started.binding)
        replay = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert _error(failed) == "sso_failed"
        assert replay.response.status_code == 400

    def test_the_sign_in_works_once_the_database_does(self, browser, make_provider, failing_table):
        make_provider("acme")
        failing_table.fail("users_sessions", "INSERT")
        browser.provider.claims = {"email": "db@example.com", "email_verified": True}
        assert _error(browser.sign_in("acme")[1]) == "sso_failed"
        failing_table.heal("users_sessions", "INSERT")

        _, finished = browser.sign_in("acme")

        assert finished.query["sso"] == "success"


class TestInactiveAccounts:
    def test_a_deactivated_account_cannot_sign_in(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            user = make_user(db, active=False)
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"email": "x@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_account_disabled"
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"], row.target_id) == ("denied", "inactive", str(user.id))

    def test_an_account_awaiting_approval_is_told_to_wait(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        with committed_sessions() as db:
            user = make_user(db, active=False, pending_admin_approval=True, deactivated_at=None)
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_approval_pending"


class TestProfileSync:
    def test_the_name_is_synced_when_the_sign_in_completes_not_before(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme", sync_user_info=True)
        with committed_sessions() as db:
            user = make_user(db, name="Old Name")
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"name": "Provider Name", "email": "x@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        with committed_sessions() as db:
            assert db.scalar(select(users_models.Users.name).where(users_models.Users.id == user.id)) == "Old Name"
        assert browser.exchange(finished.session_id).status_code == 200
        with committed_sessions() as db:
            assert db.scalar(select(users_models.Users.name).where(users_models.Users.id == user.id)) == "Provider Name"

    def test_nothing_is_synced_when_the_provider_has_sync_off(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme", sync_user_info=False, sync_email=False)
        with committed_sessions() as db:
            user = make_user(db, name="Old Name", email="old@example.com")
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"name": "Provider Name", "email": "new@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")
        assert browser.exchange(finished.session_id).status_code == 200

        with committed_sessions() as db:
            row = db.get(users_models.Users, user.id)
            assert (row.name, row.email) == ("Old Name", "old@example.com")

    def test_a_verified_email_is_synced_and_an_address_another_account_holds_is_not(
        self, browser, make_provider, committed_sessions
    ):
        idp_id = make_provider("acme", sync_user_info=False, sync_email=True)
        with committed_sessions() as db:
            user = make_user(db, email="old@example.com")
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            make_user(db, email="held@example.com")
            db.commit()
        for email in ("held@example.com", "new@example.com"):
            browser.provider.claims = {"email": email, "email_verified": True}
            _, finished = browser.sign_in("acme")
            assert browser.exchange(finished.session_id).status_code == 200
            with committed_sessions() as db:
                current = db.get(users_models.Users, user.id).email
            assert current == ("old@example.com" if email == "held@example.com" else "new@example.com")

    def test_an_unverified_email_is_not_synced(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme", sync_user_info=False, sync_email=True)
        with committed_sessions() as db:
            user = make_user(db, email="old@example.com")
            make_identity_link(db, user.id, idp_id, "provider-subject-1")
            db.commit()
        browser.provider.claims = {"email": "new@example.com", "email_verified": False}

        _, finished = browser.sign_in("acme")
        # an unverified email is refused for a new subject only; a linked subject signs in and keeps its address
        assert browser.exchange(finished.session_id).status_code == 200
        with committed_sessions() as db:
            assert db.get(users_models.Users, user.id).email == "old@example.com"


class TestStateAndBrowserBinding:
    def test_an_unknown_state_is_refused_and_audited_as_a_failed_sign_in(
        self, browser, make_provider, committed_sessions
    ):
        make_provider("acme")

        finished = browser.callback("acme", state="nope", code="c", binding="b")

        assert finished.response.status_code == 400
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"]) == ("failure", "invalid_state")

    def test_a_state_is_used_once(self, browser, make_provider):
        make_provider("acme")
        browser.provider.claims = {"email": "once@example.com", "email_verified": True}
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url)
        first = browser.callback("acme", state=state, code=code, binding=started.binding)

        replay = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert first.query["sso"] == "success"
        assert replay.response.status_code == 400
        assert replay.response.json()["detail"] == "Invalid or expired OAuth state"

    @pytest.mark.parametrize("binding", [None, "", "another-browser"])
    def test_a_callback_from_another_browser_is_refused_and_the_state_stays_usable(
        self, binding, browser, make_provider, committed_sessions
    ):
        make_provider("acme")
        browser.provider.claims = {"email": "bound@example.com", "email_verified": True}
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url)

        refused = browser.callback("acme", state=state, code=code, binding=binding)
        accepted = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert refused.response.status_code == 400
        assert accepted.query["sso"] == "success"
        reasons = [row.details["reason"] for row in audit(committed_sessions, LOGIN)]
        assert reasons == ["browser_mismatch"]

    def test_a_state_started_for_another_provider_is_refused(self, browser, make_provider):
        make_provider("acme")
        make_provider(
            "other",
            provider_type="oauth2",
            issuer_url=None,
            scopes="profile",
            token_endpoint=provider_endpoint(browser),
        )
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url)

        finished = browser.callback("other", state=state, code=code, binding=started.binding)

        assert finished.response.status_code == 400

    def test_a_disabled_or_unknown_provider_has_no_login_and_no_callback(self, browser, make_provider):
        make_provider("off", enabled=False)

        for slug in ("off", "missing"):
            login = browser.client.get(
                f"{API}/public/idp/login/{slug}",
                params={"code_challenge": "c" * 43, "code_challenge_method": "S256"},
                follow_redirects=False,
            )
            callback = browser.callback(slug, state="s", code="c", binding="b")
            assert login.status_code == 404
            assert callback.response.status_code == 404

    def test_a_state_that_expired_is_refused(self, browser, make_provider, committed_sessions):
        import sqlalchemy as sa

        import modules.auth.oauth_state.models as oauth_state_models

        make_provider("acme")
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url)
        with committed_sessions() as db:
            db.execute(
                sa.update(oauth_state_models.OAuthState).values(expires_at=sa.text("now() - interval '1 minute'"))
            )
            db.commit()

        finished = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert finished.response.status_code == 400


class TestLoginStart:
    def _login(self, browser, slug="acme", **params):
        return browser.client.get(f"{API}/public/idp/login/{slug}", params=params, follow_redirects=False)

    def test_the_authorization_request_carries_pkce_state_nonce_and_the_callback_address(self, browser, make_provider):
        make_provider("acme")

        started = browser.start_login("acme")

        from urllib.parse import parse_qs, urlsplit

        url = urlsplit(started.authorization_url)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        assert url.path == "/authorize"
        assert query["client_id"] == CLIENT_ID
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        assert query["redirect_uri"].endswith("/api/v1/public/idp/callback/acme")
        assert {"state", "nonce", "code_challenge", "scope"} <= query.keys()
        assert started.binding

    def test_the_binding_cookie_is_http_only_and_lax(self, browser, make_provider):
        make_provider("acme")
        response = self._login(browser, code_challenge="c" * 43, code_challenge_method="S256")

        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie

    @pytest.mark.parametrize(
        "params",
        [
            {"code_challenge": "short", "code_challenge_method": "S256"},
            {"code_challenge": "c" * 43, "code_challenge_method": "plain"},
            {"code_challenge": "c" * 43, "code_challenge_method": "S256", "redirect": "https://evil.example/x"},
            {"code_challenge": "c" * 43, "code_challenge_method": "S256", "redirect": "//evil.example"},
            {"code_challenge": "c" * 43, "code_challenge_method": "S256", "redirect": "http://app/x"},
            {"code_challenge": "c" * 43, "code_challenge_method": "S256", "redirect": "javascript:alert(1)"},
        ],
    )
    def test_a_malformed_challenge_or_a_foreign_redirect_is_refused_before_anything_is_stored(
        self, params, browser, make_provider
    ):
        make_provider("acme")

        response = self._login(browser, **params)

        assert response.status_code == 400, response.text
        assert browser.provider.requests == []

    def test_an_empty_challenge_is_refused(self, browser, make_provider):
        make_provider("acme")

        response = self._login(browser, code_challenge="", code_challenge_method="S256")

        assert response.status_code == 400
        assert "code_challenge" in response.json()["detail"]

    def test_the_challenge_is_required(self, browser, make_provider):
        make_provider("acme")

        assert self._login(browser).status_code == 422

    def test_a_provider_with_configured_endpoints_needs_no_discovery(self, browser, make_provider, provider):
        make_provider("acme", authorization_endpoint=provider.authorization_endpoint)

        started = browser.start_login("acme")

        assert started.authorization_url.startswith(provider.authorization_endpoint)
        assert provider.requests_to("/.well-known/openid-configuration") == []

    def test_discovery_is_fetched_once_and_cached(self, browser, make_provider, provider):
        make_provider("acme")

        browser.start_login("acme")
        browser.start_login("acme")

        assert len(provider.requests_to("/.well-known/openid-configuration")) == 1

    @pytest.mark.parametrize("missing", ["authorization_endpoint", None])
    def test_a_provider_whose_authorization_endpoint_cannot_be_found_is_a_bad_gateway(
        self, missing, browser, make_provider, provider
    ):
        make_provider("acme")
        if missing:
            provider.discovery = {missing: None}
        else:
            provider.discovery_status = 500

        response = self._login(browser, code_challenge="c" * 43, code_challenge_method="S256")

        assert response.status_code == 502, response.text

    def test_an_authorization_endpoint_on_a_private_address_is_refused_unless_allowed(
        self, browser, make_provider, monkeypatch
    ):
        import core.config as core_config

        make_provider("acme")
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        response = self._login(browser, code_challenge="c" * 43, code_challenge_method="S256")

        assert response.status_code in (400, 502), response.text


class TestTokenExchangeWithTheProvider:
    @pytest.mark.parametrize("status", [400, 401, 500, 503])
    def test_a_provider_that_refuses_or_fails_the_code_exchange_ends_in_a_login_error_and_a_failure_row(
        self, status, browser, make_provider, committed_sessions
    ):
        make_provider("acme")
        browser.provider.token_status = status
        browser.provider.claims = {"email": "x@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_failed"
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"]) == ("failure", "token_exchange_failed")

    def test_a_token_response_that_is_not_json_is_a_login_error(self, browser, make_provider):
        make_provider("acme")
        browser.provider.token_body = b"<html>not json</html>"

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"

    def test_the_provider_answering_with_an_error_instead_of_a_code_ends_in_a_login_error(
        self, browser, make_provider, committed_sessions
    ):
        make_provider("acme")
        started = browser.start_login("acme")

        finished = browser.callback("acme", state=started.state, error="access_denied", binding=started.binding)

        assert _error(finished) == "sso_failed"
        assert browser.provider.requests_to("/token") == []
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"]) == ("failure", "provider_error")

    def test_a_code_the_provider_does_not_know_is_refused(self, browser, make_provider):
        make_provider("acme")
        started = browser.start_login("acme")

        finished = browser.callback("acme", state=started.state, code="forged", binding=started.binding)

        assert _error(finished) == "sso_failed"

    def test_a_provider_that_cannot_be_reached_is_a_login_error(self, browser, make_provider, provider):
        make_provider("acme", token_endpoint="http://127.0.0.1:9/token")
        browser.provider.claims = {"email": "x@example.com", "email_verified": True}

        _, finished = browser.sign_in("acme")

        assert _error(finished) == "sso_failed"

    def test_a_provider_that_answers_slowly_is_a_login_error(self, browser, make_provider, provider, monkeypatch):
        import modules.auth.identity_providers.oidc_client_service as oidc_client_service

        make_provider("acme")
        browser.provider.claims = {"email": "slow@example.com", "email_verified": True}
        started = browser.start_login("acme")
        code, state = browser.provider.authorize(started.authorization_url)
        original = oidc_client_service.OidcClientService.create_oauth_client

        def impatient(self, *args, **kwargs):
            client = original(self, *args, **kwargs)
            client.timeout = 0.2
            return client

        monkeypatch.setattr(oidc_client_service.OidcClientService, "create_oauth_client", impatient)
        provider.delays = {"/token": 0.6}

        finished = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert _error(finished) == "sso_failed"


class TestIdToken:
    @pytest.mark.parametrize(
        "scenario",
        ["wrong_nonce", "wrong_audience", "wrong_issuer", "expired", "foreign_key", "unknown_kid", "none_alg", "hs256"],
    )
    def test_an_id_token_that_does_not_verify_signs_nobody_in(
        self, scenario, browser, make_provider, provider, committed_sessions
    ):
        import base64
        import hashlib
        import hmac as hmaclib
        import json

        from joserfc.jwk import RSAKey

        make_provider("acme")
        started = browser.start_login("acme")
        code, state = provider.authorize(started.authorization_url, email="x@example.com", email_verified=True)
        now = int(time.time())
        claims = provider.id_token_claims_for(client_id=CLIENT_ID, nonce=started.nonce, access_token=None)
        claims.update({"email": "x@example.com", "email_verified": True})
        header = None
        key = None
        if scenario == "wrong_nonce":
            claims["nonce"] = "someone-elses"
        elif scenario == "wrong_audience":
            claims["aud"] = "another-client"
        elif scenario == "wrong_issuer":
            claims["iss"] = "https://evil.example"
        elif scenario == "expired":
            claims.update({"iat": now - 7200, "exp": now - 3600})
        elif scenario == "foreign_key":
            key = RSAKey.generate_key(2048, parameters={"kid": "test-key-1"})
        elif scenario == "unknown_kid":
            header = {"kid": "rotated-away"}
        if scenario in {"none_alg", "hs256"}:
            alg = "none" if scenario == "none_alg" else "HS256"

            def b64(data: bytes) -> str:
                return base64.urlsafe_b64encode(data).decode().rstrip("=")

            signing_input = (
                f"{b64(json.dumps({'alg': alg, 'kid': 'test-key-1'}).encode())}.{b64(json.dumps(claims).encode())}"
            )
            signature = (
                b"" if alg == "none" else hmaclib.new(b"secret", signing_input.encode(), hashlib.sha256).digest()
            )
            provider.id_token_override = f"{signing_input}.{b64(signature)}"
        else:
            provider.id_token_override = provider.sign(claims, header=header, key=key)

        finished = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert _error(finished) == "sso_failed"
        assert users_by_email(committed_sessions, "x@example.com") == []
        row = _only(audit(committed_sessions, LOGIN))
        assert (row.outcome, row.details["reason"]) == ("failure", "invalid_id_token")

    def test_an_oidc_provider_that_returns_no_id_token_is_refused(self, browser, make_provider, provider):
        make_provider("acme")
        provider.issue_id_token = False

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"

    def test_an_issuer_without_signing_keys_cannot_sign_anyone_in(self, browser, make_provider, provider):
        make_provider("acme")
        provider.discovery = {"jwks_uri": None}

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"

    def test_userinfo_for_another_subject_than_the_id_token_is_refused(self, browser, make_provider, provider):
        make_provider("acme")
        provider.userinfo_body = {"sub": "someone-else", "email": "x@example.com"}

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"

    def test_a_userinfo_endpoint_that_fails_leaves_the_id_token_claims_in_charge(
        self, browser, make_provider, provider, committed_sessions
    ):
        make_provider("acme")
        provider.userinfo_status = 500

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        assert len(users_by_email(committed_sessions, "x@example.com")) == 1

    def test_userinfo_supplements_the_id_token_and_the_id_token_wins(
        self, browser, make_provider, provider, committed_sessions
    ):
        make_provider("acme")
        provider.userinfo_body = {"sub": provider.sub, "name": "From Userinfo", "email": "ignored@example.com"}

        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        user = users_by_email(committed_sessions, "x@example.com")[0]
        assert user.email == "x@example.com"
        assert user.name == "From Userinfo"

    def test_a_subject_longer_than_one_hundred_characters_is_kept(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        browser.provider.sub = "s" * 200

        _, finished = browser.sign_in("acme", email="long@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        assert _only(links_of(committed_sessions, idp_id)).idp_subject == "s" * 200


class TestIssuerParameter:
    def test_a_callback_naming_the_providers_issuer_is_accepted(self, browser, make_provider):
        make_provider("acme")
        started = browser.start_login("acme")

        finished = browser.finish("acme", started, with_iss=True, email="x@example.com", email_verified=True)

        assert finished.query["sso"] == "success"

    def test_a_callback_naming_another_issuer_is_refused_before_the_code_is_redeemed(
        self, browser, make_provider, provider
    ):
        make_provider("acme")
        started = browser.start_login("acme")
        code, state = provider.authorize(started.authorization_url, email="x@example.com", email_verified=True)

        finished = browser.callback("acme", state=state, code=code, binding=started.binding, iss="https://evil.example")

        assert _error(finished) == "sso_failed"
        assert provider.requests_to("/token") == []

    def test_a_provider_that_advertises_the_parameter_must_send_it(self, browser, make_provider, provider):
        make_provider("acme")
        provider.discovery = {"authorization_response_iss_parameter_supported": True}

        _, without = browser.sign_in("acme", email="x@example.com", email_verified=True)
        started = browser.start_login("acme")
        with_iss = browser.finish("acme", started, with_iss=True, email="y@example.com", email_verified=True)

        assert _error(without) == "sso_failed"
        assert with_iss.query["sso"] == "success"


class TestOAuth2Provider:
    def test_a_provider_with_an_issuer_and_its_own_userinfo_endpoint_uses_both(
        self, browser, make_provider, provider, committed_sessions
    ):
        make_provider("gh", provider_type="oauth2", scopes="read:user", userinfo_endpoint=provider.userinfo_endpoint)

        _, finished = browser.sign_in("gh", sub="7", email="both@example.com", email_verified=True)

        assert finished.query["sso"] == "success", finished.location

    def _oauth2(self, make_provider, provider, **fields):
        return make_provider(
            "gh",
            provider_type="oauth2",
            issuer_url=None,
            scopes="read:user user:email",
            authorization_endpoint=provider.authorization_endpoint,
            token_endpoint=provider.token_endpoint,
            userinfo_endpoint=provider.userinfo_endpoint,
            **fields,
        )

    def test_a_provider_without_an_id_token_identifies_users_by_the_userinfo_claims(
        self, browser, make_provider, provider, committed_sessions
    ):
        idp_id = self._oauth2(make_provider, provider)

        _, finished = browser.sign_in("gh", sub="12345", email="gh@example.com", email_verified=True)

        assert finished.query["sso"] == "success"
        assert _only(links_of(committed_sessions, idp_id)).idp_subject == "12345"

    def test_an_integer_id_is_the_subject_when_there_is_no_sub(
        self, browser, make_provider, provider, committed_sessions
    ):
        idp_id = self._oauth2(make_provider, provider)
        provider.userinfo_body = {"id": 987, "email": "int@example.com", "email_verified": True}

        _, finished = browser.sign_in("gh")

        assert finished.query["sso"] == "success"
        assert _only(links_of(committed_sessions, idp_id)).idp_subject == "987"

    @pytest.mark.parametrize("claims", [{}, {"id": True}, {"id": "  "}])
    def test_userinfo_that_names_no_subject_signs_nobody_in(
        self, claims, browser, make_provider, provider, committed_sessions
    ):
        self._oauth2(make_provider, provider)
        provider.userinfo_body = {"email": "x@example.com", "email_verified": True, **claims}

        _, finished = browser.sign_in("gh")

        assert _error(finished) == "sso_failed"
        assert _only(audit(committed_sessions, LOGIN)).details["reason"] == "no_subject"

    def test_a_provider_whose_userinfo_fails_and_that_issues_no_id_token_signs_nobody_in(
        self, browser, make_provider, provider
    ):
        self._oauth2(make_provider, provider)
        provider.userinfo_status = 500

        _, finished = browser.sign_in("gh", sub="1", email="x@example.com", email_verified=True)

        assert _error(finished) == "sso_failed"


def test_two_providers_with_the_same_subject_are_two_identities(
    browser, other_provider, make_provider, committed_sessions
):
    first = make_provider("one")
    second = make_provider("two", issuer_url=other_provider.issuer)
    browser.provider.claims = {"email": "same@example.com", "email_verified": True}
    browser.provider.sub = "shared-subject"
    a = browser.sign_in("one")[1]
    assert browser.exchange(a.session_id).status_code == 200
    other_provider.claims = {"email": "other@example.com", "email_verified": True}
    other_provider.sub = "shared-subject"
    other_browser = Browser(browser.client, other_provider)

    b = other_browser.sign_in("two")[1]

    assert browser.exchange(b.session_id).status_code == 200
    first_link, second_link = links_of(committed_sessions, first)[0], links_of(committed_sessions, second)[0]
    assert first_link.user_id != second_link.user_id


class TestTokenExchangeOfTheSession:
    def test_a_wrong_verifier_is_refused_and_the_right_one_still_works(self, browser, make_provider):
        make_provider("acme")
        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)

        wrong = browser.exchange(finished.session_id, verifier="w" * 43)
        right = browser.exchange(finished.session_id)

        assert wrong.status_code == 400
        assert right.status_code == 200, right.text

    def test_a_session_is_exchanged_once(self, browser, make_provider):
        make_provider("acme")
        _, finished = browser.sign_in("acme", email="x@example.com", email_verified=True)
        assert browser.exchange(finished.session_id).status_code == 200

        assert browser.exchange(finished.session_id).status_code == 404

    def test_an_unknown_session_is_not_found(self, browser):
        assert browser.exchange(uuid.uuid4()).status_code == 404

    def test_the_verifier_the_login_started_with_is_the_one_in_the_challenge(self, browser, make_provider):
        make_provider("acme")
        assert VERIFIER == "v" * 43


class TestInitiatingALoginThroughTheService:
    """The service that builds the provider URL from a stored OAuth state, on the real database."""

    @pytest.fixture
    def service(self):
        from jasil.backends.state_memory import MemoryState

        import modules.auth.identity_providers.authorization_service as authorization_service
        import modules.auth.identity_providers.oidc_client_service as oidc_client_service

        return authorization_service.AuthorizationService(
            oidc_client_service.OidcClientService(MemoryState(), "test"), "https://app.example.com"
        )

    def _idp(self, db, provider):
        from modules.auth.identity_providers import crud as idp_crud
        from tests._factories.identity_links import make_oidc_provider

        return idp_crud.get_identity_provider(make_oidc_provider(db, "acme", provider.issuer), db)

    def test_a_login_without_a_state_id_is_refused(self, db, service, provider):
        import core.exceptions as core_exceptions

        with pytest.raises(core_exceptions.ProcessingError, match="OAuth state ID is required"):
            service.initiate_login(self._idp(db, provider), db)

    def test_a_login_with_an_unknown_state_id_is_refused(self, db, service, provider):
        import core.exceptions as core_exceptions

        with pytest.raises(core_exceptions.ProcessingError, match="OAuth state not found"):
            service.initiate_login(self._idp(db, provider), db, oauth_state_id="unknown")
