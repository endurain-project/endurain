"""The Strava routes through the production application: client credentials, OAuth state, link and gear import."""

import io
import threading
import uuid

import jasil.audit.models as audit_models
import pytest
from sqlalchemy import select

import core.config as core_config
import core.cryptography as core_cryptography
import modules.gears.gear.integration_service as gears_integration
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.constants as strava_constants
import modules.strava.link_service as strava_link_service
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.users import PASSWORD, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_SCOPES = ",".join(strava_constants.REQUIRED_OAUTH_SCOPES)
_LINK_AUDIT = strava_audit_actions.ACCOUNT_LINK.id
_CLIENT_AUDIT = strava_audit_actions.CLIENT_UPDATE.id


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def with_client(committed_sessions, user):
    """The user has stored a Strava application, as the link needs."""
    with committed_sessions() as db:
        user_integrations_integration.set_strava_client(
            user.id, strava_factories.CLIENT_ID, strava_factories.CLIENT_SECRET, db, if_match="*"
        )
        db.commit()
    return user


def _integrations(committed_sessions, user_id):
    with committed_sessions() as db:
        return user_integrations_integration.require_user_integrations(user_id, db)


def _audit(committed_sessions, action_id):
    with committed_sessions() as db:
        return list(db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == action_id)))


def _state(client) -> str:
    response = client.post(f"{_API}/strava/state")
    assert response.status_code == 201, response.text
    return response.json()["state"]


def _link_body(state: str, **overrides) -> dict:
    return {"state": state, "code": "authorization-code", "scope": _SCOPES, **overrides}


def _finish_links() -> None:
    """Wait for the links the route queued on the pool."""
    strava_link_service.shutdown_link_pool(wait=True)


class TestOAuthState:
    def test_a_state_is_issued_unguessable_and_different_each_time_and_a_new_one_replaces_the_old(
        self, sign_in, user, with_client, strava
    ):
        client = sign_in(user).client
        first, second = _state(client), _state(client)

        assert first != second
        assert len(first) >= strava_constants.OAUTH_STATE_MIN_LENGTH
        refused = client.post(f"{_API}/strava/link", json=_link_body(first))
        assert refused.status_code == 400, "the replaced state is no longer good"

    def test_another_users_state_is_never_good_for_this_user(self, sign_in, user, with_client, committed_sessions):
        with committed_sessions() as db:
            other = make_user(db)
            db.commit()
        other_state = _state(sign_in(other).client)

        refused = sign_in(user).client.post(f"{_API}/strava/link", json=_link_body(other_state))

        assert refused.status_code == 400, refused.text


class TestClientCredentials:
    def _put(self, client, **body):
        etag = client.get(f"{_API}/profile").headers["ETag"]
        payload = {"client_id": 4242, "client_secret": "the-secret", **_STEP_UP, **body}
        return client.put(f"{_API}/strava/client", json=payload, headers={"If-Match": etag})

    def test_the_client_is_stored_encrypted_and_the_new_version_returned(self, sign_in, user, committed_sessions):
        client = sign_in(user).client
        before = client.get(f"{_API}/profile").headers["ETag"]

        response = self._put(client)

        assert response.status_code == 204, response.text
        assert response.headers["ETag"] != before
        stored = _integrations(committed_sessions, user.id)
        assert stored.strava_client_id != "4242"
        assert core_cryptography.decrypt_token_fernet(stored.strava_client_id) == "4242"
        assert core_cryptography.decrypt_token_fernet(stored.strava_client_secret) == "the-secret"
        assert "the-secret" not in response.text

    def test_storing_the_client_is_audited_without_the_id_or_secret(self, sign_in, user, committed_sessions):
        self._put(sign_in(user).client)

        (row,) = _audit(committed_sessions, _CLIENT_AUDIT)
        assert (row.actor_id, row.target_owner_id, row.details) == (str(user.id), str(user.id), None)

    def test_a_wrong_step_up_stores_nothing_and_audits_nothing(self, sign_in, user, committed_sessions):
        response = self._put(sign_in(user).client, step_up={"current_password": "wrong"})

        assert response.status_code in (401, 403), response.text
        assert _integrations(committed_sessions, user.id).strava_client_id is None
        assert _audit(committed_sessions, _CLIENT_AUDIT) == []

    def test_a_stale_version_is_refused_and_not_audited(self, sign_in, user, committed_sessions):
        client = sign_in(user).client
        stale = client.get(f"{_API}/profile").headers["ETag"]
        assert self._put(client).status_code == 204

        response = client.put(
            f"{_API}/strava/client",
            json={"client_id": 1, "client_secret": "other", **_STEP_UP},
            headers={"If-Match": stale},
        )

        assert response.status_code == 412, response.text
        assert len(_audit(committed_sessions, _CLIENT_AUDIT)) == 1
        stored = _integrations(committed_sessions, user.id)
        assert core_cryptography.decrypt_token_fernet(stored.strava_client_id) == "4242"

    @pytest.mark.parametrize(
        "body",
        [{"client_id": 0}, {"client_id": -5}, {"client_secret": ""}, {"client_secret": "x" * 256}, {"extra": 1}],
        ids=["zero-id", "negative-id", "empty-secret", "long-secret", "unknown-field"],
    )
    def test_invalid_credentials_are_refused_without_echoing_the_secret(self, sign_in, user, body):
        response = self._put(sign_in(user).client, **body)

        assert response.status_code == 422, response.text
        assert "the-secret" not in response.text


class TestLinkRefusals:
    def test_a_grant_missing_a_required_scope_is_refused_audited_and_leaves_the_state_for_a_retry(
        self, sign_in, user, with_client, committed_sessions, strava
    ):
        client = sign_in(user).client
        state = _state(client)

        refused = client.post(f"{_API}/strava/link", json=_link_body(state, scope="read,activity:read_all"))

        assert refused.status_code == 400, refused.text
        assert refused.json()["type"] == "urn:endurain:error:provider-scope-insufficient"
        assert "profile:read_all" in refused.json()["detail"]
        (row,) = _audit(committed_sessions, _LINK_AUDIT)
        assert (row.outcome, row.details) == ("failure", {"reason": "insufficient_scope"})
        strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("a", "r")))
        retried = client.post(f"{_API}/strava/link", json=_link_body(state))
        _finish_links()
        assert retried.status_code == 202, retried.text

    def test_a_grant_with_extra_scopes_is_accepted(self, sign_in, user, with_client, strava):
        strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("a", "r")))
        client = sign_in(user).client

        response = client.post(
            f"{_API}/strava/link", json=_link_body(_state(client), scope=f"{_SCOPES},activity:write")
        )
        _finish_links()

        assert response.status_code == 202, response.text

    def test_a_state_is_good_for_one_link_only(self, sign_in, user, with_client, strava):
        strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("a", "r")))
        client = sign_in(user).client
        state = _state(client)
        first = client.post(f"{_API}/strava/link", json=_link_body(state))
        _finish_links()

        replay = client.post(f"{_API}/strava/link", json=_link_body(state))

        assert (first.status_code, replay.status_code) == (202, 400)

    def test_a_wrong_state_is_refused_and_uses_up_the_stored_one(self, sign_in, user, with_client):
        client = sign_in(user).client
        state = _state(client)

        wrong = client.post(f"{_API}/strava/link", json=_link_body("w" * len(state)))
        right = client.post(f"{_API}/strava/link", json=_link_body(state))

        assert (wrong.status_code, right.status_code) == (400, 400)

    def test_a_user_without_a_stored_client_is_refused_and_no_link_is_recorded(self, sign_in, user, committed_sessions):
        client = sign_in(user).client

        refused = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))

        assert refused.status_code == 400, refused.text
        assert _audit(committed_sessions, _LINK_AUDIT) == []

    def test_a_state_shorter_than_the_server_issues_is_not_a_valid_request(self, sign_in, user):
        response = sign_in(user).client.post(f"{_API}/strava/link", json=_link_body("abc"))

        assert response.status_code == 422, response.text

    def test_a_link_already_running_is_a_conflict(self, sign_in, user, with_client, strava):
        in_exchange, release = threading.Event(), threading.Event()

        def hold_the_exchange(_call):
            in_exchange.set()
            release.wait(timeout=30)
            return strava_factories.ok(strava_factories.token_payload("a", "r"))

        strava.on("POST", "/oauth/token", hold_the_exchange)
        client = sign_in(user).client
        first = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        try:
            assert in_exchange.wait(timeout=30)
            second = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        finally:
            release.set()
            _finish_links()

        assert (first.status_code, second.status_code) == (202, 409)

    def test_a_full_pool_refuses_the_link_and_leaves_the_state_unused(self, sign_in, user, with_client, strava):
        release = threading.Event()
        for _ in range(strava_link_service.core_sync_runner.MAX_CONCURRENT_LINKS):
            strava_link_service._link_pool.submit(release.wait)
        client = sign_in(user).client
        state = _state(client)
        try:
            full = client.post(f"{_API}/strava/link", json=_link_body(state))
        finally:
            release.set()
            _finish_links()
        strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("a", "r")))

        retried = client.post(f"{_API}/strava/link", json=_link_body(state))
        _finish_links()

        assert (full.status_code, retried.status_code) == (503, 202)


class TestLinkExchange:
    def test_a_successful_exchange_stores_the_tokens_audits_the_link_and_completes_the_job(
        self, sign_in, user, with_client, committed_sessions, strava
    ):
        strava.on(
            "POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("linked", "linked-refresh"))
        )
        client = sign_in(user).client

        response = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        _finish_links()

        assert response.status_code == 202, response.text
        assert (response.json()["kind"], response.json()["status"]) == ("strava_link", "queued")
        (call,) = strava.made("POST", "/oauth/token")
        assert call.form == {
            "client_id": strava_factories.CLIENT_ID,
            "client_secret": strava_factories.CLIENT_SECRET,
            "code": "authorization-code",
            "grant_type": "authorization_code",
        }
        stored = _integrations(committed_sessions, user.id)
        assert core_cryptography.decrypt_token_fernet(stored.strava_token) == "linked"
        assert core_cryptography.decrypt_token_fernet(stored.strava_refresh_token) == "linked-refresh"
        (row,) = _audit(committed_sessions, _LINK_AUDIT)
        assert (row.outcome, row.actor_id, (row.details or {}).get("reason")) == ("success", None, None)
        job = client.get(response.headers["Content-Location"])
        assert job.json()["status"] == "succeeded"

    @pytest.mark.parametrize(
        ("reply", "reason"),
        [
            (strava_factories.refused(400), "rejected"),
            (strava_factories.refused(401), "unauthorized"),
            (strava_factories.rate_limited(), "too_many_requests"),
        ],
        ids=["rejected", "unauthorized", "rate-limited"],
    )
    def test_a_code_strava_refuses_fails_the_job_audits_the_reason_and_keeps_the_client(
        self, sign_in, user, with_client, committed_sessions, strava, reply, reason
    ):
        strava.on("POST", "/oauth/token", reply)
        client = sign_in(user).client

        response = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        _finish_links()

        stored = _integrations(committed_sessions, user.id)
        assert (stored.strava_token, stored.strava_client_id is not None) == (None, True)
        (row,) = _audit(committed_sessions, _LINK_AUDIT)
        assert (row.outcome, row.details) == ("failure", {"reason": reason})
        assert client.get(response.headers["Content-Location"]).json()["status"] == "failed"

    def test_a_failure_that_is_not_a_refusal_fails_the_job_and_leaves_no_row(
        self, sign_in, user, with_client, committed_sessions, strava
    ):
        strava.on("POST", "/oauth/token", strava_factories.refused(500))
        client = sign_in(user).client

        response = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        _finish_links()

        assert client.get(response.headers["Content-Location"]).json()["status"] == "failed"
        assert _audit(committed_sessions, _LINK_AUDIT) == []

    def test_no_database_session_is_open_while_strava_exchanges_the_code(self, sign_in, user, with_client, strava):
        import core.database as core_database

        open_connections = []

        def answer(_call):
            open_connections.append(core_database.engine.pool.checkedout())
            return strava_factories.ok(strava_factories.token_payload("a", "r"))

        strava.on("POST", "/oauth/token", answer)
        client = sign_in(user).client

        client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
        _finish_links()

        assert open_connections == [0]


class TestGearImport:
    def _upload(self, client, content: bytes, gear_type: str = "bike"):
        return client.post(
            f"{_API}/strava/import/gear",
            params={"gear_type": gear_type},
            files={"file": ("bikes.csv", io.BytesIO(content), "text/csv")},
        )

    def test_the_bikes_in_the_file_are_created_for_the_caller_and_counted(self, sign_in, user, committed_sessions):
        content = b"Bike Name,Bike Brand,Bike Model\nCommuter,Trek,Domane\nGravel,Canyon,Grail\n"

        response = self._upload(sign_in(user).client, content)

        assert (response.status_code, response.json()) == (200, {"imported": 2})
        with committed_sessions() as db:
            assert {g.nickname for g in gears_integration.get_gear_user(user.id, db)} == {"Commuter", "Gravel"}

    def test_the_shoes_in_the_file_are_created_when_the_type_says_shoes(self, sign_in, user, committed_sessions):
        response = self._upload(
            sign_in(user).client, b"Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Peg 40\n", gear_type="shoes"
        )

        assert response.json() == {"imported": 1}
        with committed_sessions() as db:
            (shoe,) = gears_integration.get_gear_user(user.id, db)
        assert (shoe.nickname, shoe.gear_type.value) == ("Pegasus", "shoes")

    def test_gear_is_never_created_for_another_user(self, sign_in, user, committed_sessions):
        with committed_sessions() as db:
            other = make_user(db)
            db.commit()

        self._upload(sign_in(user).client, b"Bike Name,Bike Brand,Bike Model\nMine,,\n")

        with committed_sessions() as db:
            assert gears_integration.get_gear_user(other.id, db) == []

    def test_a_file_without_the_columns_is_refused(self, sign_in, user):
        response = self._upload(sign_in(user).client, b"Name,Brand\nx,y\n")

        assert response.status_code == 400, response.text

    @pytest.mark.parametrize("gear_type", ["wetsuit", "ski", "1", ""])
    def test_only_bikes_and_shoes_can_be_imported(self, sign_in, user, gear_type):
        response = self._upload(sign_in(user).client, b"x", gear_type=gear_type)

        assert response.status_code == 422, response.text

    def test_an_oversized_file_is_refused(self, sign_in, user):
        big = b"Bike Name,Bike Brand,Bike Model\n" + b"x," * strava_constants.GEAR_CSV_MAX_BYTES

        response = self._upload(sign_in(user).client, big)

        assert response.status_code == 413, response.text

    def test_a_missing_file_is_refused(self, sign_in, user):
        response = sign_in(user).client.post(f"{_API}/strava/import/gear", params={"gear_type": "bike"})

        assert response.status_code == 422, response.text


def test_the_job_a_link_queued_is_only_readable_by_its_owner(sign_in, user, with_client, committed_sessions, strava):
    strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("a", "r")))
    client = sign_in(user).client
    response = client.post(f"{_API}/strava/link", json=_link_body(_state(client)))
    _finish_links()
    with committed_sessions() as db:
        stranger = make_user(db)
        db.commit()

    seen_by_stranger = sign_in(stranger).client.get(response.headers["Content-Location"])

    assert seen_by_stranger.status_code == 404, seen_by_stranger.text
    assert uuid.UUID(response.json()["id"])
