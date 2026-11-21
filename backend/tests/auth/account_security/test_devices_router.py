"""The signed-in user's known devices: listing, and forgetting them after a step-up that ends their sessions."""

import uuid

import sqlalchemy as sa

import core.config as core_config
import core.hashing as core_hashing
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.known_devices.models as known_devices_models
from tests._factories.account_security import device_id_of, session_ids, sign_in_from_device
from tests._factories.devices import make_known_device
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_user

_DEVICES = f"{core_config.ROOT_PATH}/profile/devices"
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_STEP_UP_FAILED = "urn:endurain:error:step-up-failed"


def _device_hash(device_id: str) -> str:
    return core_hashing.sha256_hex(device_id)


class _Account:
    """A user with two devices, each with a session, and a second user's device that must stay untouched."""

    def __init__(self, app, committed_sessions) -> None:
        self.here, self.there = device_id_of("here"), device_id_of("there")
        with committed_sessions() as db:
            self.user = make_user(db)
            self.other_user = make_user(db)
            self.here_device = make_known_device(db, self.user.id, _device_hash(self.here))
            self.there_device = make_known_device(db, self.user.id, _device_hash(self.there))
            self.stranger_device = make_known_device(db, self.other_user.id, _device_hash(device_id_of("stranger")))
            db.commit()
            self.here_session = sign_in_from_device(app, db, self.user, self.here)
            self.there_session = sign_in_from_device(app, db, self.user, self.there)


def _devices_of(committed_sessions, user_id: uuid.UUID) -> set[uuid.UUID]:
    with committed_sessions() as db:
        return set(
            db.scalars(
                sa.select(known_devices_models.KnownDevice.id).where(
                    known_devices_models.KnownDevice.user_id == user_id
                )
            )
        )


class TestList:
    def test_the_device_the_request_comes_from_is_marked_current(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.get(_DEVICES)

        assert response.status_code == 200
        current = {item["id"]: item["is_current"] for item in response.json()["items"]}
        assert current == {str(account.here_device): True, str(account.there_device): False}

    def test_a_request_without_a_device_id_marks_none_current(self, app, committed_sessions, sign_in):
        account = _Account(app, committed_sessions)

        response = sign_in(account.user).client.get(_DEVICES)

        assert [item["is_current"] for item in response.json()["items"]] == [False, False]

    def test_a_malformed_device_id_counts_as_none(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.get(_DEVICES, headers={"X-Device-Id": "short"})

        assert [item["is_current"] for item in response.json()["items"]] == [False, False]


class TestForgetOne:
    def test_another_device_is_forgotten_with_its_sessions_and_audited(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/{account.there_device}/delete", json=_STEP_UP)

        assert response.status_code == 204
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device}
        assert session_ids(committed_sessions, account.user.id) == {account.here_session.session_id}
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.DEVICE_FORGET)
        assert (row.outcome, row.target_id, row.target_owner_id, row.details["sessions_revoked"]) == (
            "success",
            str(account.there_device),
            str(account.user.id),
            1,
        )

    def test_the_device_the_request_comes_from_is_a_conflict(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/{account.here_device}/delete", json=_STEP_UP)

        assert response.status_code == 409
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device, account.there_device}

    def test_another_users_device_is_not_found_and_stays(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/{account.stranger_device}/delete", json=_STEP_UP)

        assert response.status_code == 404
        assert _devices_of(committed_sessions, account.other_user.id) == {account.stranger_device}
        assert audit_rows(committed_sessions, account_security_audit_actions.DEVICE_FORGET) == []

    def test_a_wrong_password_forgets_nothing_and_audits_nothing(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(
            f"{_DEVICES}/{account.there_device}/delete", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert response.json()["type"] == _STEP_UP_FAILED
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device, account.there_device}
        assert len(session_ids(committed_sessions, account.user.id)) == 2
        assert audit_rows(committed_sessions, account_security_audit_actions.DEVICE_FORGET) == []

    def test_a_body_without_step_up_is_refused(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/{account.there_device}/delete", json={})

        assert response.status_code == 422
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device, account.there_device}


class TestForgetOthers:
    def test_every_device_but_the_current_one_goes_with_its_sessions(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/delete-others", json=_STEP_UP)

        assert response.status_code == 204
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device}
        assert _devices_of(committed_sessions, account.other_user.id) == {account.stranger_device}
        assert session_ids(committed_sessions, account.user.id) == {account.here_session.session_id}
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.DEVICES_FORGET_OTHERS)
        assert (row.target_id, row.details["sessions_revoked"]) == (str(account.user.id), 1)

    def test_a_request_without_a_device_id_forgets_every_device(self, app, committed_sessions, sign_in):
        account = _Account(app, committed_sessions)

        response = sign_in(account.user).client.post(f"{_DEVICES}/delete-others", json=_STEP_UP)

        assert response.status_code == 204
        assert _devices_of(committed_sessions, account.user.id) == set()

    def test_a_wrong_password_forgets_nothing(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(
            f"{_DEVICES}/delete-others", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert _devices_of(committed_sessions, account.user.id) == {account.here_device, account.there_device}
        assert audit_rows(committed_sessions, account_security_audit_actions.DEVICES_FORGET_OTHERS) == []


class TestForgetAll:
    def test_every_device_and_session_goes_and_the_cookie_is_cleared(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(f"{_DEVICES}/delete-all", json=_STEP_UP)

        assert response.status_code == 204
        assert _devices_of(committed_sessions, account.user.id) == set()
        assert session_ids(committed_sessions, account.user.id) == set()
        assert _devices_of(committed_sessions, account.other_user.id) == {account.stranger_device}
        assert "max-age=0" in response.headers["set-cookie"].lower()
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.DEVICES_FORGET_ALL)
        assert row.details["sessions_revoked"] == 2
        assert account.here_session.client.get(_DEVICES).status_code == 401

    def test_a_wrong_password_forgets_nothing(self, app, committed_sessions):
        account = _Account(app, committed_sessions)

        response = account.here_session.client.post(
            f"{_DEVICES}/delete-all", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert len(session_ids(committed_sessions, account.user.id)) == 2
