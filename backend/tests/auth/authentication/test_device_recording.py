"""A sign-in records the device it came from, hands the client its device id and announces a device it never saw."""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.config as core_config
import core.hashing as core_hashing
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.models as known_devices_models
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from tests._factories.devices import make_known_device
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
    LOGIN,
    MOBILE,
    WEB,
    Account,
    exchange,
    login,
    make_sso_session,
    verify,
)

_COOKIE = known_devices_dependencies.DEVICE_COOKIE_NAME
_LOGINS = login_audit_actions.LOGIN


def _device_id() -> str:
    return secrets.token_urlsafe(32)


def _devices(sessions, account: Account) -> list[str]:
    with sessions() as db:
        return list(
            db.scalars(
                sa.select(known_devices_models.KnownDevice.device_hash).where(
                    known_devices_models.KnownDevice.user_id == account.user.id
                )
            )
        )


def _session_device_hashes(sessions, account: Account) -> list[str | None]:
    with sessions() as db:
        return list(
            db.scalars(
                sa.select(sessions_models.UsersSessions.device_hash).where(
                    sessions_models.UsersSessions.user_id == account.user.id
                )
            )
        )


def _age(sessions, account: Account, age: timedelta) -> None:
    with sessions() as db:
        db.execute(
            sa.update(users_models.Users)
            .where(users_models.Users.id == account.user.id)
            .values(created_at=datetime.now(UTC) - age)
        )
        db.commit()


def _device_cookie(response) -> str | None:
    matches = [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{_COOKIE}=")]
    assert len(matches) <= 1
    return matches[0] if matches else None


def _cookie_value(cookie: str) -> str:
    return cookie.split("=", 1)[1].split(";", 1)[0]


class TestWebSignIn:
    def test_a_sign_in_records_the_device_under_the_id_it_sets_in_a_cookie_and_ties_the_session_to_it(
        self, client, committed_sessions, account
    ):
        response = login(client, account)

        cookie = _device_cookie(response)
        assert cookie is not None
        device_hash = core_hashing.sha256_hex(_cookie_value(cookie))
        assert _devices(committed_sessions, account) == [device_hash]
        assert _session_device_hashes(committed_sessions, account) == [device_hash]
        assert "device_id" not in response.json()

    def test_the_cookie_is_http_only_strict_host_scoped_and_lasts_the_retention_period(self, client, account):
        cookie = _device_cookie(login(client, account))

        assert cookie is not None
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Max-Age=34560000" in cookie
        assert "Path=/;" in cookie or cookie.endswith("Path=/")
        assert "Domain" not in cookie

    def test_a_deployed_sign_in_sets_a_host_locked_secure_cookie(self, monkeypatch, client, account):
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "production")

        response = login(client, account)

        cookie = next(h for h in response.headers.get_list("set-cookie") if h.startswith("__Host-endurain_device="))
        assert "Secure" in cookie
        assert "Domain" not in cookie

    def test_a_returning_browser_keeps_its_id_and_is_not_flagged_as_new(self, client, committed_sessions, account):
        first = login(client, account)
        device_id = _cookie_value(_device_cookie(first))
        client.cookies.set(_COOKIE, device_id)

        login(client, account)

        assert len(_devices(committed_sessions, account)) == 1
        rows = audit_rows(committed_sessions, _LOGINS)
        assert [row.details["new_device"] for row in rows][-1] is False

    def test_a_malformed_cookie_is_ignored_and_a_new_id_is_minted(self, client, committed_sessions, account):
        client.cookies.set(_COOKIE, "not-a-device-id")

        response = login(client, account)

        issued = _cookie_value(_device_cookie(response))
        assert issued != "not-a-device-id"
        assert _devices(committed_sessions, account) == [core_hashing.sha256_hex(issued)]

    def test_a_password_that_needs_mfa_records_nothing_until_the_code_completes_the_sign_in(
        self, client, committed_sessions, mfa_account
    ):
        challenge = login(client, mfa_account)
        assert _devices(committed_sessions, mfa_account) == []

        completed = verify(client, challenge.json()["mfa_challenge"], mfa_account.backup_code)

        cookie = _device_cookie(completed)
        assert cookie is not None
        assert _devices(committed_sessions, mfa_account) == [core_hashing.sha256_hex(_cookie_value(cookie))]

    def test_a_web_mfa_sign_in_keeps_the_cookie_the_browser_sent(self, client, committed_sessions, mfa_account):
        device_id = _device_id()
        client.cookies.set(_COOKIE, device_id)
        challenge = login(client, mfa_account).json()["mfa_challenge"]

        verify(client, challenge, mfa_account.backup_code)

        assert _devices(committed_sessions, mfa_account) == [core_hashing.sha256_hex(device_id)]


class TestMobileSignIn:
    def test_a_sign_in_under_the_header_id_returns_it_in_the_body_only_and_sets_no_cookie(
        self, client, committed_sessions, account
    ):
        device_id = _device_id()

        response = client.post(
            LOGIN,
            data={
                "username": account.username,
                "password": account.password,
                "code_challenge": "a" * 43,
                "code_challenge_method": "S256",
            },
            headers={**MOBILE, "X-Device-Id": device_id},
        )

        assert response.status_code == 200
        assert response.json()["device_id"] == device_id
        assert _device_cookie(response) is None
        assert response.headers["cache-control"] == "no-store"
        assert _devices(committed_sessions, account) == [core_hashing.sha256_hex(device_id)]
        assert _session_device_hashes(committed_sessions, account) == [core_hashing.sha256_hex(device_id)]

    def test_a_sign_in_without_an_id_is_given_a_new_one(self, client, committed_sessions, account):
        issued = login(client, account, MOBILE).json()["device_id"]

        assert _devices(committed_sessions, account) == [core_hashing.sha256_hex(issued)]

    def test_a_completed_mfa_sign_in_returns_the_device_id_in_the_body(self, client, mfa_account):
        challenge = login(client, mfa_account, MOBILE).json()["mfa_challenge"]

        body = verify(client, challenge, mfa_account.backup_code, MOBILE).json()

        assert body["next_step"] == "exchange"
        assert body["device_id"]


class TestFirstDeviceAnnouncement:
    @pytest.mark.parametrize(("age", "announced"), [(timedelta(hours=1), False), (timedelta(days=30), True)])
    def test_a_password_sign_in_announces_the_first_device_only_of_an_older_account(
        self, client, committed_sessions, account, published, age, announced
    ):
        events = published(known_devices_events.NEW_DEVICE_SIGN_IN)
        _age(committed_sessions, account, age)

        login(client, account)

        assert [e.payload["user_id"] for e in events] == ([str(account.user.id)] if announced else [])
        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert row.details["new_device"] is announced

    @pytest.mark.parametrize(("age", "announced"), [(timedelta(hours=1), False), (timedelta(days=30), True)])
    def test_a_mobile_sign_in_announces_the_first_device_only_of_an_older_account(
        self, client, committed_sessions, account, published, age, announced
    ):
        events = published(known_devices_events.NEW_DEVICE_SIGN_IN)
        _age(committed_sessions, account, age)

        login(client, account, MOBILE)

        assert len(events) == int(announced)

    def test_a_second_device_is_announced_even_for_a_new_account(self, client, committed_sessions, account, published):
        with committed_sessions() as db:
            make_known_device(db, account.user.id, core_hashing.sha256_hex(_device_id()))
            db.commit()
        events = published(known_devices_events.NEW_DEVICE_SIGN_IN)

        login(client, account)

        assert len(events) == 1
        assert events[0].payload["method"] == "password"

    @pytest.mark.parametrize(("age", "announced"), [(timedelta(hours=1), False), (timedelta(days=30), True)])
    def test_an_identity_provider_sign_in_announces_the_first_device_only_of_an_older_account(
        self, client, committed_sessions, account, published, age, announced
    ):
        events = published(known_devices_events.NEW_DEVICE_SIGN_IN)
        _age(committed_sessions, account, age)
        session_id = make_sso_session(committed_sessions, account.user)

        exchange(client, session_id, headers=WEB)

        assert len(events) == int(announced)
        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert row.details["new_device"] is announced
        if announced:
            assert events[0].payload["method"] == "identity_provider"


class TestIdentityProviderSignIn:
    def test_a_web_exchange_records_the_device_sets_the_cookie_and_ties_the_session_to_it(
        self, client, committed_sessions, account
    ):
        session_id = make_sso_session(committed_sessions, account.user)

        response = exchange(client, session_id, headers=WEB)

        cookie = _device_cookie(response)
        assert cookie is not None
        device_hash = core_hashing.sha256_hex(_cookie_value(cookie))
        assert _devices(committed_sessions, account) == [device_hash]
        assert _session_device_hashes(committed_sessions, account) == [device_hash]

    def test_a_returning_browser_is_not_flagged_as_new(self, client, committed_sessions, account):
        device_id = _device_id()
        with committed_sessions() as db:
            make_known_device(db, account.user.id, core_hashing.sha256_hex(device_id))
            db.commit()
        client.cookies.set(_COOKIE, device_id)
        session_id = make_sso_session(committed_sessions, account.user)

        exchange(client, session_id, headers=WEB)

        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert row.details["new_device"] is False

    def test_a_mobile_exchange_returns_the_device_id_in_the_body_and_sets_no_cookie(
        self, client, committed_sessions, account
    ):
        device_id = _device_id()
        session_id = make_sso_session(committed_sessions, account.user, client_type="mobile")

        response = client.post(
            f"{core_config.ROOT_PATH}/auth/sessions/{session_id}/tokens",
            json={"code_verifier": "v" * 43},
            headers={**MOBILE, "X-Device-Id": device_id},
        )

        assert response.json()["device_id"] == device_id
        assert _device_cookie(response) is None

    def test_the_exchange_of_a_password_pkce_session_records_nothing_more(self, client, committed_sessions, account):
        session_id = login(client, account, MOBILE).json()["session_id"]
        before = _devices(committed_sessions, account)

        response = exchange(client, session_id)

        assert response.status_code == 200
        assert _devices(committed_sessions, account) == before
        assert "device_id" not in response.json() or response.json()["device_id"] is None
