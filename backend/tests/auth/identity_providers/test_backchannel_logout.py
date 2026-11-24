"""A provider's back-channel logout request ends the sessions its logout token names."""

import time

import pytest

from tests.auth.identity_providers.conftest import API
from tests.auth.identity_providers.sso_helpers import audit

REFUSE = "auth.backchannel_logout.refuse"
REVOKE = "auth.session.revoke"


@pytest.fixture(autouse=True)
def _sign_up(sso_sign_up) -> None:
    """Let the provider create the accounts that sign in."""


def _only(rows):
    assert len(rows) == 1, rows
    return rows[0]


def _sign_in(browser, slug, *, sub, sid=None, **claims) -> str:
    """Sign a user in through the provider; return the access token of the session."""
    browser.provider.sub = sub
    if sid is not None:
        claims["sid"] = sid
    _, finished = browser.sign_in(slug, email=f"{sub}@example.com", email_verified=True, **claims)
    exchanged = browser.exchange(finished.session_id)
    assert exchanged.status_code == 200, exchanged.text
    return exchanged.json()["access_token"]


def _alive(browser, token) -> bool:
    return browser.client.get(f"{API}/profile", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def _logout(browser, slug, token):
    return browser.client.post(f"{API}/public/idp/{slug}/backchannel-logout", data={"logout_token": token})


class TestEndingSessions:
    def test_a_token_naming_a_provider_session_ends_the_sessions_signed_in_under_it(self, browser, make_provider):
        make_provider("acme")
        ended = _sign_in(browser, "acme", sub="alice", sid="sid-a")
        kept = _sign_in(browser, "acme", sub="bob", sid="sid-b")

        response = _logout(browser, "acme", browser.provider.logout_token(sub=None, sid="sid-a"))

        assert response.status_code == 200, response.text
        assert response.content == b""
        assert response.headers["Cache-Control"].startswith("no-store")
        assert (_alive(browser, ended), _alive(browser, kept)) == (False, True)

    def test_a_token_naming_only_a_subject_ends_every_session_the_user_signed_in_to_through_the_provider(
        self, browser, make_provider
    ):
        make_provider("acme")
        first = _sign_in(browser, "acme", sub="alice", sid="s1")
        second = _sign_in(browser, "acme", sub="alice", sid="s2")
        other = _sign_in(browser, "acme", sub="bob", sid="s3")

        response = _logout(browser, "acme", browser.provider.logout_token(sub="alice"))

        assert response.status_code == 200
        assert [_alive(browser, token) for token in (first, second, other)] == [False, False, True]

    def test_a_sid_with_a_subject_ends_only_that_users_sessions(self, browser, make_provider):
        make_provider("acme")
        alice = _sign_in(browser, "acme", sub="alice", sid="shared")
        bob = _sign_in(browser, "acme", sub="bob", sid="shared")

        _logout(browser, "acme", browser.provider.logout_token(sub="alice", sid="shared"))

        assert (_alive(browser, alice), _alive(browser, bob)) == (False, True)

    def test_each_user_whose_sessions_ended_gets_an_audit_row_with_the_count(
        self, browser, make_provider, committed_sessions
    ):
        make_provider("acme")
        _sign_in(browser, "acme", sub="alice", sid="s")
        _sign_in(browser, "acme", sub="bob", sid="s")

        _logout(browser, "acme", browser.provider.logout_token(sub=None, sid="s"))

        rows = audit(committed_sessions, REVOKE)
        assert [row.details for row in rows] == [{"sessions_revoked": 1}, {"sessions_revoked": 1}]

    def test_a_subject_nobody_is_linked_to_ends_nothing_and_succeeds(self, browser, make_provider, committed_sessions):
        make_provider("acme")
        token = _sign_in(browser, "acme", sub="alice", sid="s")

        response = _logout(browser, "acme", browser.provider.logout_token(sub="stranger"))

        assert response.status_code == 200
        assert _alive(browser, token)
        assert audit(committed_sessions, REVOKE) == []

    def test_a_user_who_is_already_signed_out_is_a_success(self, browser, make_provider):
        make_provider("acme")
        _sign_in(browser, "acme", sub="alice", sid="s")
        assert _logout(browser, "acme", browser.provider.logout_token(sid="s")).status_code == 200

        assert _logout(browser, "acme", browser.provider.logout_token(sid="s")).status_code == 200

    def test_a_disabled_provider_still_ends_the_sessions_it_signed_in(self, browser, make_provider, committed_sessions):
        import modules.auth.identity_providers.models as idp_models

        idp_id = make_provider("acme")
        token = _sign_in(browser, "acme", sub="alice", sid="s")
        with committed_sessions() as db:
            db.get(idp_models.IdentityProvider, idp_id).enabled = False
            db.commit()

        response = _logout(browser, "acme", browser.provider.logout_token(sid="s"))

        assert response.status_code == 200
        assert not _alive(browser, token)


class TestRefusals:
    def test_a_token_is_accepted_once(self, browser, make_provider, committed_sessions):
        idp_id = make_provider("acme")
        token = browser.provider.logout_token(sid="s")
        assert _logout(browser, "acme", token).status_code == 200

        replay = _logout(browser, "acme", token)

        assert replay.status_code == 400
        row = _only(audit(committed_sessions, REFUSE))
        assert row.details == {"idp_id": str(idp_id), "reason": "replayed"}
        assert row.target_id == str(idp_id)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"aud": "another-client"},
            {"iss": "https://evil.example"},
            {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
            {"jti": None},
            {"events": None},
            {"events": {"http://other/event": {}}},
            {"nonce": "an-id-token-is-not-a-logout-token"},
            {"sub": None, "sid": None},
            {"sub": ""},
            {"sid": 7},
            {"sub": "x" * 501},
        ],
        ids=[
            "wrong-audience",
            "wrong-issuer",
            "expired",
            "no-jti",
            "no-events",
            "other-event",
            "has-nonce",
            "names-nothing",
            "empty-sub",
            "non-string-sid",
            "long-sub",
        ],
    )
    def test_a_token_that_is_not_a_valid_logout_token_is_refused_and_ends_nothing(
        self, overrides, browser, make_provider, committed_sessions
    ):
        make_provider("acme")
        alive = _sign_in(browser, "acme", sub="alice", sid="s")

        response = _logout(browser, "acme", browser.provider.logout_token(**overrides))

        assert response.status_code == 400, response.text
        assert _alive(browser, alive)
        assert _only(audit(committed_sessions, REFUSE)).details["reason"] == "invalid_token"

    def test_a_token_signed_with_another_key_is_refused(self, browser, make_provider, committed_sessions):
        from joserfc.jwk import RSAKey

        make_provider("acme")
        token = browser.provider.sign(
            {
                "iss": browser.provider.issuer,
                "aud": "endurain-client",
                "iat": int(time.time()),
                "exp": int(time.time()) + 60,
                "jti": "j",
                "sub": "alice",
                "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            },
            key=RSAKey.generate_key(2048, parameters={"kid": "test-key-1"}),
        )

        response = _logout(browser, "acme", token)

        assert response.status_code == 400
        assert _only(audit(committed_sessions, REFUSE)).details["reason"] == "invalid_token"

    def test_a_token_typed_as_something_else_is_refused(self, browser, make_provider):
        make_provider("acme")
        token = browser.provider.sign(
            {
                "iss": browser.provider.issuer,
                "aud": "endurain-client",
                "iat": int(time.time()),
                "exp": int(time.time()) + 60,
                "jti": "j",
                "sub": "alice",
                "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            },
            header={"typ": "at+jwt"},
        )

        assert _logout(browser, "acme", token).status_code == 400

    @pytest.mark.parametrize("broken", ["discovery", "jwks", "no-keys"])
    def test_a_provider_whose_signing_keys_cannot_be_read_gets_a_refusal_it_can_retry(
        self, broken, browser, make_provider, provider, committed_sessions
    ):
        make_provider("acme")
        token = provider.logout_token(sub="alice")
        if broken == "discovery":
            provider.discovery_status = 500
        elif broken == "jwks":
            provider.discovery = {"jwks_uri": f"{provider.issuer}/missing"}
        else:
            provider.discovery = {"jwks_uri": None}

        response = _logout(browser, "acme", token)

        assert response.status_code == 400
        assert _only(audit(committed_sessions, REFUSE)).details["reason"] == "signing_keys_unavailable"

    def test_a_token_refused_for_unreadable_keys_is_not_spent(self, browser, make_provider, provider):
        make_provider("acme")
        token = provider.logout_token(sub="alice")
        provider.discovery_status = 500
        assert _logout(browser, "acme", token).status_code == 400
        provider.discovery_status = 200

        assert _logout(browser, "acme", token).status_code == 200

    def test_an_unknown_provider_has_no_logout_endpoint(self, browser):
        assert _logout(browser, "nobody", "x.y.z").status_code == 404

    def test_a_provider_that_issues_no_id_token_has_no_logout_endpoint(self, browser, make_provider, provider):
        make_provider(
            "plain",
            provider_type="oauth2",
            issuer_url=None,
            scopes="profile",
            authorization_endpoint=provider.authorization_endpoint,
            token_endpoint=provider.token_endpoint,
        )

        assert _logout(browser, "plain", "x.y.z").status_code == 404

    def test_the_token_is_a_required_form_field_without_control_characters(self, browser, make_provider):
        make_provider("acme")

        missing = browser.client.post(f"{API}/public/idp/acme/backchannel-logout", data={})
        nul = _logout(browser, "acme", "abc\x00def")
        empty = _logout(browser, "acme", "")

        multipart_nul = browser.client.post(
            f"{API}/public/idp/acme/backchannel-logout", files={"logout_token": (None, "abc\x00def")}
        )

        assert (missing.status_code, nul.status_code, empty.status_code, multipart_nul.status_code) == (
            422,
            422,
            422,
            422,
        )

    def test_garbage_is_refused_without_fetching_the_signing_keys_each_time(self, browser, make_provider, provider):
        make_provider("acme")

        for _ in range(3):
            assert _logout(browser, "acme", "not-a-jwt").status_code == 400

        assert provider.requests_to("/jwks") == []


class TestADatabaseFailureWhileEndingSessions:
    def test_the_token_is_not_spent_so_the_providers_retry_ends_the_sessions(
        self, app, browser, make_provider, failing_table
    ):
        from fastapi.testclient import TestClient

        make_provider("acme")
        token = _sign_in(browser, "acme", sub="alice", sid="s")
        logout_token = browser.provider.logout_token(sid="s")
        failing_table.fail("users_sessions", "DELETE")
        lenient = TestClient(app, raise_server_exceptions=False)

        failed = lenient.post(f"{API}/public/idp/acme/backchannel-logout", data={"logout_token": logout_token})
        failing_table.heal("users_sessions", "DELETE")
        retried = _logout(browser, "acme", logout_token)

        assert failed.status_code == 500
        assert retried.status_code == 200
        assert not _alive(browser, token)
