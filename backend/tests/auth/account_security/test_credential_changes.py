"""Changes to an account's credentials: its owner's password, and an administrator's reset, MFA reset and forced change.

The owner's change runs on ``/profile/password/change``; the administrator's on ``/users/{user_id}/...``.
"""

import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.security_generation.integration_service as security_generation_integration
from tests._factories.account_security import deliver_notices, sent_to, session_ids
from tests._factories.api_keys import make_api_key
from tests._factories.breach import fake_range_api
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import audit_rows, make_mfa, make_reset_token
from tests._factories.users import PASSWORD, make_admin, make_user

_NEW_PASSWORD = "A-brand-new-Passphrase-93!"
_PROFILE_PASSWORD = f"{core_config.ROOT_PATH}/profile/password/change"
_USERS = f"{core_config.ROOT_PATH}/users"
_STEP_UP = {"current_password": PASSWORD}


def _password_is_current(committed_sessions, user_id, password: str) -> bool:
    with committed_sessions() as db:
        stored = credentials_integration.get_password_hash(user_id, db)
        verified, _ = credentials_integration.verify_and_update_password(
            password, stored, credentials_integration.get_password_hasher()
        )
    return verified


def _unused_reset_tokens(committed_sessions, user_id) -> int:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(sa.func.count()).where(
                password_reset_models.PasswordResetToken.user_id == user_id,
                password_reset_models.PasswordResetToken.used.is_(False),
            )
        )


def _active_keys(committed_sessions, user_id) -> int:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(sa.func.count()).where(
                api_keys_models.UsersApiKeys.user_id == user_id, api_keys_models.UsersApiKeys.is_active.is_(True)
            )
        )


class TestOwnPassword:
    def _user(self, committed_sessions, sign_in, **options):
        with committed_sessions() as db:
            user = make_user(db, **options)
            make_reset_token(db, user)
            db.commit()
        return sign_in(user), sign_in(user)

    def test_the_new_password_replaces_the_old_and_ends_the_other_sessions(self, committed_sessions, sign_in):
        deliver_notices()
        here, _there = self._user(committed_sessions, sign_in)

        response = here.client.post(_PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": _STEP_UP})

        assert response.status_code == 204
        assert _password_is_current(committed_sessions, here.user.id, _NEW_PASSWORD)
        assert session_ids(committed_sessions, here.user.id) == {here.session_id}
        assert _unused_reset_tokens(committed_sessions, here.user.id) == 0
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_CHANGE)
        assert (row.outcome, row.target_id, row.details["sessions_revoked"]) == (
            "success",
            str(here.user.id),
            1,
        )
        assert [m.subject for m in sent_to(here.user.email)] == ["Endurain - Your password was changed"]

    def test_the_caller_can_keep_the_other_sessions(self, committed_sessions, sign_in):
        here, there = self._user(committed_sessions, sign_in)

        here.client.post(
            _PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": _STEP_UP, "revoke_other_sessions": False}
        )

        assert session_ids(committed_sessions, here.user.id) == {here.session_id, there.session_id}

    def test_a_wrong_current_password_changes_nothing(self, committed_sessions, sign_in):
        here, _ = self._user(committed_sessions, sign_in)

        response = here.client.post(
            _PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert _password_is_current(committed_sessions, here.user.id, PASSWORD)
        assert audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_CHANGE) == []

    def test_the_current_password_cannot_be_the_new_one(self, committed_sessions, sign_in):
        here, _ = self._user(committed_sessions, sign_in)

        response = here.client.post(_PROFILE_PASSWORD, json={"password": PASSWORD, "step_up": _STEP_UP})

        assert response.status_code == 422
        assert len(session_ids(committed_sessions, here.user.id)) == 2

    def test_a_password_the_policy_refuses_changes_nothing(self, committed_sessions, sign_in):
        here, _ = self._user(committed_sessions, sign_in)

        response = here.client.post(_PROFILE_PASSWORD, json={"password": "short", "step_up": _STEP_UP})

        assert response.status_code == 422
        assert _password_is_current(committed_sessions, here.user.id, PASSWORD)

    def test_an_account_without_a_local_password_cannot_set_one_itself(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db, with_password=False)
            db.commit()

        response = sign_in(user).client.post(
            _PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": {"current_password": "anything"}}
        )

        assert response.status_code == 403
        with committed_sessions() as db:
            assert credentials_integration.has_local_password(user.id, db) is False


class _Managed:
    """An administrator, and a user of theirs with a session, an API key and a pending reset token."""

    def __init__(self, committed_sessions, sign_in, *, mfa: bool = False) -> None:
        with committed_sessions() as db:
            admin = make_admin(db)
            self.user = make_user(db)
            self.factors = make_mfa(db, self.user) if mfa else None
            make_api_key(db, self.user, scopes=[api_keys_constants.ApiKeyScope.ACCOUNT])
            make_reset_token(db, self.user)
            db.commit()
        self.admin = sign_in(admin)
        self.session = sign_in(self.user)
        self._sessions = committed_sessions

    def sessions(self) -> set:
        return session_ids(self._sessions, self.user.id)


class TestAdministratorSetsPassword:
    def test_the_user_loses_sessions_keys_and_reset_links_and_must_choose_a_new_password(
        self, committed_sessions, sign_in
    ):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/change", json={"password": _NEW_PASSWORD, "step_up": _STEP_UP}
        )

        assert response.status_code == 204
        assert managed.sessions() == set()
        assert _active_keys(committed_sessions, managed.user.id) == 0
        assert _unused_reset_tokens(committed_sessions, managed.user.id) == 0
        assert _password_is_current(committed_sessions, managed.user.id, _NEW_PASSWORD)
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(managed.user.id, db) is True
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_SET)
        assert (row.target_id, row.details["sessions_revoked"]) == (str(managed.user.id), 1)
        assert len(sent_to(managed.user.email)) == 1

    def test_the_administrators_own_password_is_what_is_checked(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/change",
            json={"password": _NEW_PASSWORD, "step_up": {"current_password": "wrong"}},
        )

        assert response.status_code == 403
        assert len(managed.sessions()) == 1
        assert _password_is_current(committed_sessions, managed.user.id, PASSWORD)

    def test_a_password_the_policy_refuses_changes_nothing(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/change", json={"password": "short", "step_up": _STEP_UP}
        )

        assert response.status_code == 422
        assert len(managed.sessions()) == 1


class TestAdministratorResetsMfa:
    def test_the_second_factor_goes_with_every_session_and_the_user_is_told(self, committed_sessions, sign_in):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in, mfa=True)

        response = managed.admin.client.post(f"{_USERS}/{managed.user.id}/mfa/reset", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert managed.sessions() == set()
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.MFA_RESET)
        assert (row.target_id, row.details["sessions_revoked"]) == (str(managed.user.id), 1)
        assert len(sent_to(managed.user.email)) == 1

    def test_a_user_without_mfa_is_a_conflict(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(f"{_USERS}/{managed.user.id}/mfa/reset", json={"step_up": _STEP_UP})

        assert response.status_code == 409
        assert len(managed.sessions()) == 1

    def test_a_wrong_administrator_password_resets_nothing(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in, mfa=True)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/mfa/reset", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert len(managed.sessions()) == 1
        assert audit_rows(committed_sessions, account_security_audit_actions.MFA_RESET) == []


class TestAdministratorRequiresPasswordChange:
    def test_the_password_stays_valid_until_the_next_sign_in_and_every_session_ends(self, committed_sessions, sign_in):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/require-change", json={"step_up": _STEP_UP}
        )

        assert response.status_code == 204
        assert managed.sessions() == set()
        assert _password_is_current(committed_sessions, managed.user.id, PASSWORD)
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(managed.user.id, db) is True
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_CHANGE_REQUIRE)
        assert row.details["sessions_revoked"] == 1
        assert len(sent_to(managed.user.email)) == 1

    def test_a_user_without_a_local_password_is_a_conflict(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db, with_password=False)
            db.commit()

        response = sign_in(admin).client.post(f"{_USERS}/{user.id}/password/require-change", json={"step_up": _STEP_UP})

        assert response.status_code == 409


class TestAdministratorUnlinksIdentityProvider:
    def test_the_link_goes_and_the_last_sign_in_method_stays(self, committed_sessions, sign_in):
        deliver_notices()
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db)
            idp_id = make_identity_provider(db, "admin-unlink")
            make_identity_link(db, user.id, idp_id, "subject")
            db.commit()
        client = sign_in(admin).client

        response = client.post(f"{_USERS}/{user.id}/identity-providers/{idp_id}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert client.get(f"{_USERS}/{user.id}/identity-providers").json()["items"] == []
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.IDENTITY_LINK_UNLINK)
        assert (row.target_id, row.details["idp_id"]) == (str(user.id), str(idp_id))
        assert len(sent_to(user.email)) == 1

    def test_a_user_who_could_then_not_sign_in_keeps_the_link(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db, with_password=False)
            idp_id = make_identity_provider(db, "admin-unlink-last")
            make_identity_link(db, user.id, idp_id, "subject")
            db.commit()
        client = sign_in(admin).client

        response = client.post(f"{_USERS}/{user.id}/identity-providers/{idp_id}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:last-sign-in-method"
        assert len(client.get(f"{_USERS}/{user.id}/identity-providers").json()["items"]) == 1


class TestRequiredPasswordChangeAtSignIn:
    """The sign-in an administrator-set password interrupts is finished on ``/auth/password-change``."""

    def _challenge(self, app, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)
        managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/change", json={"password": _NEW_PASSWORD, "step_up": _STEP_UP}
        )
        anonymous = TestClient(app, headers={"X-Client-Type": "web"})
        response = anonymous.post(
            f"{core_config.ROOT_PATH}/auth/login", data={"username": managed.user.username, "password": _NEW_PASSWORD}
        )
        assert response.json()["next_step"] == "password_change"
        return managed, anonymous, response.json()["password_change_challenge"]

    def test_a_new_password_that_passes_the_policy_finishes_the_sign_in(self, app, committed_sessions, sign_in):
        managed, anonymous, challenge = self._challenge(app, committed_sessions, sign_in)
        chosen = "My-Own-Passphrase-4711!"

        response = anonymous.post(
            f"{core_config.ROOT_PATH}/auth/password-change",
            json={"password_change_challenge": challenge, "password": chosen},
        )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["access_token"]
        assert len(managed.sessions()) == 1
        assert _password_is_current(committed_sessions, managed.user.id, chosen)
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(managed.user.id, db) is False
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_CHANGE)
        assert row.details["sessions_revoked"] == 0

    def test_a_password_the_policy_refuses_keeps_the_challenge_usable(self, app, committed_sessions, sign_in):
        _managed, anonymous, challenge = self._challenge(app, committed_sessions, sign_in)
        url = f"{core_config.ROOT_PATH}/auth/password-change"

        refused = anonymous.post(url, json={"password_change_challenge": challenge, "password": "short"})
        accepted = anonymous.post(
            url, json={"password_change_challenge": challenge, "password": "My-Own-Passphrase-4711!"}
        )

        assert (refused.status_code, accepted.status_code) == (422, 200)

    def test_a_challenge_works_once(self, app, committed_sessions, sign_in):
        _managed, anonymous, challenge = self._challenge(app, committed_sessions, sign_in)
        url = f"{core_config.ROOT_PATH}/auth/password-change"
        body = {"password_change_challenge": challenge, "password": "My-Own-Passphrase-4711!"}

        first = anonymous.post(url, json=body)
        again = anonymous.post(url, json=body)

        assert (first.status_code, again.status_code) == (200, 401)

    def test_an_unknown_challenge_is_refused(self, client):
        response = client.post(
            f"{core_config.ROOT_PATH}/auth/password-change",
            json={"password_change_challenge": "c" * 43, "password": "My-Own-Passphrase-4711!"},
            headers={"X-Client-Type": "web"},
        )

        assert response.status_code == 401

    def test_a_security_change_after_the_sign_in_started_ends_the_challenge(self, app, committed_sessions, sign_in):
        managed, anonymous, challenge = self._challenge(app, committed_sessions, sign_in)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(managed.user.id, db)
            db.commit()

        response = anonymous.post(
            f"{core_config.ROOT_PATH}/auth/password-change",
            json={"password_change_challenge": challenge, "password": "My-Own-Passphrase-4711!"},
        )

        assert response.status_code == 401
        assert _password_is_current(committed_sessions, managed.user.id, _NEW_PASSWORD)

    def test_a_breached_password_is_refused_and_the_challenge_stays_usable(
        self, app, committed_sessions, sign_in, monkeypatch
    ):
        managed, anonymous, challenge = self._challenge(app, committed_sessions, sign_in)
        with committed_sessions() as db:
            edit_server_settings(db, password_breach_check_enabled=True)
            db.commit()
        fake_range_api(monkeypatch).breach("Pwned-Passphrase-4711!")
        url = f"{core_config.ROOT_PATH}/auth/password-change"

        refused = anonymous.post(
            url, json={"password_change_challenge": challenge, "password": "Pwned-Passphrase-4711!"}
        )

        assert refused.status_code == 422
        assert refused.json()["type"] == "urn:endurain:error:password-breached"
        assert _password_is_current(committed_sessions, managed.user.id, _NEW_PASSWORD)
        assert managed.sessions() == set()
        retried = anonymous.post(
            url, json={"password_change_challenge": challenge, "password": "Clean-Passphrase-9182!"}
        )
        assert retried.status_code == 200
        assert _password_is_current(committed_sessions, managed.user.id, "Clean-Passphrase-9182!")


class TestSecurityGeneration:
    """A change of a credential moves the account's security generation on, so what was issued before stops working."""

    def _generation(self, committed_sessions, user_id) -> int:
        with committed_sessions() as db:
            return security_generation_integration.current_generation(user_id, db)

    def test_an_own_password_change_moves_it_on_and_a_refused_one_does_not(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        owner = sign_in(user)
        start = self._generation(committed_sessions, user.id)

        owner.client.post(_PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": {"current_password": "bad"}})
        assert self._generation(committed_sessions, user.id) == start
        owner.client.post(_PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": _STEP_UP})

        assert self._generation(committed_sessions, user.id) > start

    def test_an_own_password_change_keeps_the_users_api_keys(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACCOUNT])
            db.commit()

        sign_in(user).client.post(_PROFILE_PASSWORD, json={"password": _NEW_PASSWORD, "step_up": _STEP_UP})

        assert _active_keys(committed_sessions, user.id) == 1

    def test_an_administrators_password_and_a_required_change_move_it_on(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)
        start = self._generation(committed_sessions, managed.user.id)

        managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/password/change", json={"password": _NEW_PASSWORD, "step_up": _STEP_UP}
        )
        after_set = self._generation(committed_sessions, managed.user.id)
        managed.admin.client.post(f"{_USERS}/{managed.user.id}/password/require-change", json={"step_up": _STEP_UP})

        assert start < after_set < self._generation(committed_sessions, managed.user.id)

    def test_an_unknown_provider_and_an_unlinked_one_are_not_found(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db)
            unlinked = make_identity_provider(db, "admin-unlink-none")
            db.commit()
        client = sign_in(admin).client

        unknown = client.post(
            f"{_USERS}/{user.id}/identity-providers/{uuid.uuid4()}/unlink", json={"step_up": _STEP_UP}
        )
        not_linked = client.post(f"{_USERS}/{user.id}/identity-providers/{unlinked}/unlink", json={"step_up": _STEP_UP})

        assert (unknown.status_code, not_linked.status_code) == (404, 404)
