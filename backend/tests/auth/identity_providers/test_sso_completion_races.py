"""Completing an SSO sign-in, once: the token exchange and the MFA step claim the session, and what the callback
staged for the account is applied by whichever request claims it.

Run against real PostgreSQL rows and row locks, with several requests at once.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.sessions.models as sessions_models
from modules.auth.constants import ClientType
from tests._factories.identity_links import make_identity_link
from tests._factories.tokens import make_mfa, totp_code
from tests._factories.users import make_user
from tests.auth.identity_providers.conftest import API, VERIFIER, Browser
from tests.auth.identity_providers.sso_helpers import audit, links_of

NOT_ELIGIBLE = "Session not found or not eligible for token exchange"
WEB = {"X-Client-Type": ClientType.WEB.value}


@pytest.fixture
def idp_id(make_provider):
    return make_provider("acme", link_by_email=True)


def _exchange(app, session_id):
    return TestClient(app).post(
        f"{API}/auth/sessions/{session_id}/tokens", json={"code_verifier": VERIFIER}, headers=WEB
    )


def _verify(app, challenge, code):
    return TestClient(app).post(
        f"{API}/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": code}, headers=WEB
    )


def _together(calls):
    """Run the callables at the same moment on their own threads and return their results in order."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def _linked_user(committed_sessions, idp_id, *, mfa=False):
    with committed_sessions() as db:
        user = make_user(db)
        make_identity_link(db, user.id, idp_id, "provider-subject-1")
        factors = make_mfa(db, user) if mfa else None
        db.commit()
    return user, factors


def _sign_in(browser, user_email="x@example.com", **claims):
    _, finished = browser.sign_in("acme", email=user_email, email_verified=True, **claims)
    assert finished.query["sso"] == "success", finished.location
    return finished.session_id


def _session_state(sessions, session_id):
    with sessions() as db:
        exchanged = db.scalar(
            sa.select(sessions_models.UsersSessions.tokens_exchanged).where(
                sessions_models.UsersSessions.id == session_id
            )
        )
        states = db.scalar(sa.select(sa.func.count()).select_from(oauth_state_models.OAuthState))
    return exchanged, states


class TestExchangeReplay:
    def test_a_second_exchange_finds_the_state_the_first_one_cleared_and_answers_not_found(
        self, app, browser, idp_id, committed_sessions
    ):
        _linked_user(committed_sessions, idp_id)
        session_id = _sign_in(browser)

        first = _exchange(app, session_id)
        replay = _exchange(app, session_id)

        assert first.status_code == 200, first.text
        assert (replay.status_code, replay.json()["detail"]) == (404, NOT_ELIGIBLE)
        assert _session_state(committed_sessions, session_id) == (True, 0)

    def test_two_exchanges_at_once_hand_out_tokens_once(self, app, browser, idp_id, committed_sessions):
        _linked_user(committed_sessions, idp_id)
        session_id = _sign_in(browser)

        results = _together([lambda: _exchange(app, session_id)] * 2)

        assert sorted(response.status_code for response in results) == [200, 404]
        assert _session_state(committed_sessions, session_id)[0] is True


class TestMfaStep:
    def test_the_exchange_of_an_account_with_mfa_asks_for_the_code_and_the_mfa_step_claims_the_session_once(
        self, app, browser, idp_id, committed_sessions
    ):
        _, factors = _linked_user(committed_sessions, idp_id, mfa=True)
        session_id = _sign_in(browser)

        first = _exchange(app, session_id).json()
        second = _exchange(app, session_id).json()

        assert (first["next_step"], second["next_step"]) == ("mfa", "mfa")
        assert first["mfa_challenge"] != second["mfa_challenge"]
        assert _session_state(committed_sessions, session_id) == (False, 1)

        signed_in = _verify(app, first["mfa_challenge"], totp_code(factors.secret))
        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["access_token"]
        assert _session_state(committed_sessions, session_id) == (True, 0)
        late = _verify(app, second["mfa_challenge"], totp_code(factors.secret, steps_ahead=1))
        assert late.status_code == 401
        assert _exchange(app, session_id).status_code == 404

    def test_two_mfa_steps_at_once_for_one_session_sign_in_once(self, app, browser, idp_id, committed_sessions):
        _, factors = _linked_user(committed_sessions, idp_id, mfa=True)
        session_id = _sign_in(browser)
        challenges = [_exchange(app, session_id).json()["mfa_challenge"] for _ in range(2)]

        results = _together(
            [
                lambda: _verify(app, challenges[0], totp_code(factors.secret)),
                lambda: _verify(app, challenges[1], totp_code(factors.secret, steps_ahead=1)),
            ]
        )

        assert sorted(response.status_code for response in results) == [200, 401]
        assert _session_state(committed_sessions, session_id) == (True, 0)


class TestStagedLink:
    def _two_accounts(self, committed_sessions):
        with committed_sessions() as db:
            first = make_user(db, email="first@example.com", email_verified=True)
            second = make_user(db, email="second@example.com", email_verified=True)
            db.commit()
        return first, second

    def test_the_link_an_email_match_staged_is_made_by_the_exchange_that_claims_the_session(
        self, app, browser, idp_id, committed_sessions
    ):
        first, _ = self._two_accounts(committed_sessions)
        session_id = _sign_in(browser, "first@example.com")
        assert links_of(committed_sessions, idp_id) == []

        assert _exchange(app, session_id).status_code == 200

        (link,) = links_of(committed_sessions, idp_id)
        assert link.user_id == first.id
        assert len(audit(committed_sessions, "auth.identity_link.link")) == 1

    def test_two_sessions_linking_one_subject_to_two_accounts_sign_in_only_the_first_to_commit(
        self, app, browser, idp_id, committed_sessions
    ):
        first, second = self._two_accounts(committed_sessions)
        sessions = [_sign_in(browser, "first@example.com"), _sign_in(browser, "second@example.com")]

        results = _together([lambda sid=sid: _exchange(app, sid) for sid in sessions])

        statuses = sorted(response.status_code for response in results)
        assert statuses[0] == 200 and statuses[1] in (401, 404), [r.text for r in results]
        winner = 0 if results[0].status_code == 200 else 1
        (link,) = links_of(committed_sessions, idp_id)
        assert link.user_id == (first.id, second.id)[winner]
        assert _session_state(committed_sessions, sessions[winner])[0] is True
        assert _session_state(committed_sessions, sessions[1 - winner])[0] is False
        rows = audit(committed_sessions, "auth.identity_link.link")
        assert sorted(row.outcome for row in rows) == ["denied", "success"]
        assert sorted(row.details.get("reason") or "" for row in rows) == ["", "linked_to_another_account"]

    def test_two_mfa_steps_for_one_session_apply_its_staged_link_once(self, app, browser, idp_id, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, email="first@example.com", email_verified=True)
            factors = make_mfa(db, user)
            db.commit()
        session_id = _sign_in(browser, "first@example.com")
        challenges = [_exchange(app, session_id).json()["mfa_challenge"] for _ in range(2)]
        assert links_of(committed_sessions, idp_id) == []

        results = _together(
            [
                lambda: _verify(app, challenges[0], totp_code(factors.secret)),
                lambda: _verify(app, challenges[1], totp_code(factors.secret, steps_ahead=1)),
            ]
        )

        assert sorted(response.status_code for response in results) == [200, 401]
        (link,) = links_of(committed_sessions, idp_id)
        assert link.user_id == user.id
        assert len(audit(committed_sessions, "auth.identity_link.link")) == 1


def test_of_two_callbacks_with_one_state_only_the_one_that_claims_it_signs_in(
    app, provider, idp_id, committed_sessions, sso_sign_up
):
    """Both callbacks pass the unused check; the claim, an UPDATE that waits for the first, decides."""
    from tests.auth.identity_providers.sso_helpers import wait_until_a_session_waits_for_a_lock

    first_browser = Browser(TestClient(app), provider)
    second_browser = Browser(TestClient(app), provider)
    provider.claims = {"email": "race@example.com", "email_verified": True}
    started = first_browser.start_login("acme")
    code, state = provider.authorize(started.authorization_url)
    outcomes = []

    def callback(browser):
        outcomes.append(browser.callback("acme", state=state, code=code, binding=started.binding))

    with committed_sessions() as holder:
        holder.execute(
            sa.select(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.id == state).with_for_update()
        )
        threads = [threading.Thread(target=callback, args=(b,)) for b in (first_browser, second_browser)]
        for thread in threads:
            thread.start()
        wait_until_a_session_waits_for_a_lock(committed_sessions)
        holder.rollback()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcome.response.status_code for outcome in outcomes) == [307, 400]
    signed_in = [outcome for outcome in outcomes if outcome.response.status_code == 307]
    assert signed_in[0].query["sso"] == "success"
    assert len(links_of(committed_sessions)) == 1
