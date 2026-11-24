"""The signed-in user's own two-step verification: status, enrolment, removal and backup codes, after a step-up."""

import pytest

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.security_generation.integration_service as security_generation_integration
from tests._factories.account_security import deliver_notices, sent_to, session_ids
from tests._factories.tokens import audit_rows, make_mfa, totp_code
from tests._factories.users import PASSWORD, make_user

_MFA = f"{core_config.ROOT_PATH}/profile/mfa"
_STEP_UP_FAILED = "urn:endurain:error:step-up-failed"


class _Owner:
    """A user signed in twice (the request's session and another device's), with MFA enrolled when asked."""

    def __init__(self, committed_sessions, sign_in, *, mfa: bool = False) -> None:
        with committed_sessions() as db:
            self.user = make_user(db)
            self.factors = make_mfa(db, self.user) if mfa else None
            db.commit()
        self.session = sign_in(self.user)
        self.other_session = sign_in(self.user)
        self.client = self.session.client
        self._sessions = committed_sessions

    def step_up(self, **extra) -> dict:
        """Return a step-up body: the password and, when MFA is enrolled, a code no earlier request used."""
        body = {"current_password": PASSWORD}
        if self.factors is not None:
            body["mfa_code"] = totp_code(self.factors.secret, steps_ahead=1)
        return {"step_up": body, **extra}

    def sessions(self) -> set:
        return session_ids(self._sessions, self.user.id)

    def enrol(self, **extra):
        """Run setup and enable with a valid code; return the enable response."""
        secret = self.client.post(f"{_MFA}/setup").json()["secret"]
        return self.client.post(
            f"{_MFA}/enable", json={"totp_code": totp_code(secret), "step_up": {"current_password": PASSWORD}, **extra}
        )


@pytest.fixture
def owner(committed_sessions, sign_in) -> _Owner:
    return _Owner(committed_sessions, sign_in)


@pytest.fixture
def mfa_owner(committed_sessions, sign_in) -> _Owner:
    return _Owner(committed_sessions, sign_in, mfa=True)


class TestStatus:
    def test_an_account_without_mfa_reports_it_and_no_codes(self, owner):
        assert owner.client.get(f"{_MFA}/status").json() == {"mfa_enabled": False, "factors": []}
        assert owner.client.get(f"{_MFA}/backup-codes/status").json() == {
            "has_codes": False,
            "total": 0,
            "unused": 0,
            "used": 0,
            "created_at": None,
        }

    def test_an_enrolled_account_lists_its_factor_and_ten_unused_codes(self, mfa_owner):
        status = mfa_owner.client.get(f"{_MFA}/status").json()
        codes = mfa_owner.client.get(f"{_MFA}/backup-codes/status").json()

        assert status["mfa_enabled"] is True
        assert [factor["type"] for factor in status["factors"]] == ["totp"]
        assert (codes["has_codes"], codes["total"], codes["unused"], codes["used"]) == (True, 10, 10, 0)


class TestSetup:
    def test_setup_issues_a_secret_that_no_cache_keeps(self, owner):
        response = owner.client.post(f"{_MFA}/setup")

        assert response.status_code == 201
        assert response.headers["Cache-Control"] == "no-store"
        assert set(response.json()) >= {"secret", "qr_code", "app_name"}

    def test_setup_does_not_enable_mfa(self, owner):
        owner.client.post(f"{_MFA}/setup")

        assert owner.client.get(f"{_MFA}/status").json()["mfa_enabled"] is False

    def test_an_account_with_mfa_cannot_start_another_setup(self, mfa_owner):
        assert mfa_owner.client.post(f"{_MFA}/setup").status_code == 409


class TestEnable:
    def test_a_confirmed_setup_enables_mfa_and_returns_the_backup_codes_once(self, committed_sessions, owner):
        response = owner.enrol()

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert len(response.json()["codes"]) == 10
        assert owner.client.get(f"{_MFA}/status").json()["mfa_enabled"] is True
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.MFA_ENABLE)
        assert (row.outcome, row.target_id) == ("success", str(owner.user.id))

    def test_the_other_sessions_end_unless_the_caller_keeps_them(self, committed_sessions, sign_in):
        ending = _Owner(committed_sessions, sign_in)
        keeping = _Owner(committed_sessions, sign_in)

        ending.enrol()
        keeping.enrol(revoke_other_sessions=False)

        assert ending.sessions() == {ending.session.session_id}
        assert keeping.sessions() == {keeping.session.session_id, keeping.other_session.session_id}
        rows = audit_rows(committed_sessions, account_security_audit_actions.MFA_ENABLE)
        assert sorted(row.details["sessions_revoked"] for row in rows) == [0, 1]

    def test_without_a_setup_in_progress_it_is_a_conflict(self, owner):
        response = owner.client.post(
            f"{_MFA}/enable", json={"totp_code": "123456", "step_up": {"current_password": PASSWORD}}
        )

        assert response.status_code == 409

    def test_a_wrong_password_refuses_the_enrolment_and_the_setup_stays_usable(self, owner):
        secret = owner.client.post(f"{_MFA}/setup").json()["secret"]

        refused = owner.client.post(
            f"{_MFA}/enable", json={"totp_code": totp_code(secret), "step_up": {"current_password": "wrong"}}
        )
        accepted = owner.client.post(
            f"{_MFA}/enable", json={"totp_code": totp_code(secret), "step_up": {"current_password": PASSWORD}}
        )

        assert (refused.status_code, accepted.status_code) == (403, 200)
        assert refused.json()["type"] == _STEP_UP_FAILED

    def test_a_wrong_authenticator_code_is_a_400_and_the_setup_stays_usable(self, owner):
        secret = owner.client.post(f"{_MFA}/setup").json()["secret"]

        wrong = owner.client.post(
            f"{_MFA}/enable", json={"totp_code": "000000", "step_up": {"current_password": PASSWORD}}
        )
        right = owner.client.post(
            f"{_MFA}/enable", json={"totp_code": totp_code(secret), "step_up": {"current_password": PASSWORD}}
        )

        assert wrong.status_code == 400
        assert wrong.json()["type"] == "urn:endurain:error:invalid-mfa-code"
        assert right.status_code == 200
        assert owner.client.get(f"{_MFA}/status").json()["mfa_enabled"] is True

    def test_a_setup_made_stale_by_an_enrolment_elsewhere_is_discarded_with_the_refusal(
        self, committed_sessions, owner
    ):
        secret = owner.client.post(f"{_MFA}/setup").json()["secret"]
        with committed_sessions() as db:
            backup_code = make_mfa(db, owner.user).backup_codes[0]
            db.commit()
        body = {"totp_code": totp_code(secret), "step_up": {"current_password": PASSWORD, "mfa_code": backup_code}}

        refused = owner.client.post(f"{_MFA}/enable", json=body)
        retried = owner.client.post(f"{_MFA}/enable", json=body)

        assert refused.status_code == 409
        assert "already enabled" in refused.json()["detail"]
        assert "No MFA setup in progress" in retried.json()["detail"]

    def test_the_old_mfa_code_field_is_refused(self, owner):
        owner.client.post(f"{_MFA}/setup")

        response = owner.client.post(
            f"{_MFA}/enable", json={"mfa_code": "123456", "step_up": {"current_password": PASSWORD}}
        )

        assert response.status_code == 422

    def test_the_owner_is_told_by_email(self, owner):
        deliver_notices()

        owner.enrol()

        assert [m.subject for m in sent_to(owner.user.email)] == ["Endurain - Two-factor authentication was turned on"]


class TestDisable:
    def test_the_password_and_a_code_turn_mfa_off_and_end_the_other_sessions(self, committed_sessions, mfa_owner):
        response = mfa_owner.client.post(f"{_MFA}/disable", json=mfa_owner.step_up())

        assert response.status_code == 204
        assert mfa_owner.client.get(f"{_MFA}/status").json() == {"mfa_enabled": False, "factors": []}
        assert mfa_owner.sessions() == {mfa_owner.session.session_id}
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.MFA_DISABLE)
        assert row.details["sessions_revoked"] == 1

    def test_the_caller_can_keep_the_other_sessions(self, mfa_owner):
        mfa_owner.client.post(f"{_MFA}/disable", json=mfa_owner.step_up(revoke_other_sessions=False))

        assert len(mfa_owner.sessions()) == 2

    def test_a_backup_code_stands_in_for_the_authenticator_code(self, mfa_owner):
        body = {"step_up": {"current_password": PASSWORD, "mfa_code": mfa_owner.factors.backup_codes[0]}}

        assert mfa_owner.client.post(f"{_MFA}/disable", json=body).status_code == 204

    def test_a_wrong_code_leaves_mfa_on(self, committed_sessions, mfa_owner):
        body = {"step_up": {"current_password": PASSWORD, "mfa_code": "000000"}}

        response = mfa_owner.client.post(f"{_MFA}/disable", json=body)

        assert response.status_code == 403
        assert mfa_owner.client.get(f"{_MFA}/status").json()["mfa_enabled"] is True
        assert audit_rows(committed_sessions, account_security_audit_actions.MFA_DISABLE) == []

    def test_an_account_without_mfa_has_nothing_to_disable(self, owner):
        assert owner.client.post(f"{_MFA}/disable", json=owner.step_up()).status_code == 409

    def test_an_unknown_key_is_refused(self, mfa_owner):
        assert mfa_owner.client.post(f"{_MFA}/disable", json=mfa_owner.step_up(unexpected=1)).status_code == 422


class TestBackupCodes:
    def test_new_codes_replace_the_old_set_and_are_audited_with_their_count(self, committed_sessions, mfa_owner):
        old = mfa_owner.factors.backup_codes

        response = mfa_owner.client.post(f"{_MFA}/backup-codes", json=mfa_owner.step_up())

        assert response.status_code == 201
        assert response.headers["Cache-Control"] == "no-store"
        codes = response.json()["codes"]
        assert len(codes) == 10 and not set(codes) & set(old)
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.BACKUP_CODES_GENERATE)
        assert (row.details["count"], row.details["sessions_revoked"]) == (10, 1)
        stale = {"step_up": {"current_password": PASSWORD, "mfa_code": old[0]}}
        assert mfa_owner.client.post(f"{_MFA}/backup-codes", json=stale).status_code == 403

    def test_new_codes_leave_the_security_generation_alone(self, committed_sessions, mfa_owner):
        def generation() -> int:
            with committed_sessions() as db:
                return security_generation_integration.current_generation(mfa_owner.user.id, db)

        before = generation()
        mfa_owner.client.post(f"{_MFA}/backup-codes", json=mfa_owner.step_up())

        assert generation() == before

    def test_the_caller_can_keep_the_other_sessions(self, mfa_owner):
        mfa_owner.client.post(f"{_MFA}/backup-codes", json=mfa_owner.step_up(revoke_other_sessions=False))

        assert len(mfa_owner.sessions()) == 2

    def test_an_account_without_mfa_has_no_backup_codes_to_renew(self, owner):
        assert owner.client.post(f"{_MFA}/backup-codes", json=owner.step_up()).status_code == 409

    def test_a_wrong_password_issues_nothing(self, committed_sessions, mfa_owner):
        body = {
            "step_up": {"current_password": "wrong", "mfa_code": totp_code(mfa_owner.factors.secret, steps_ahead=1)}
        }

        response = mfa_owner.client.post(f"{_MFA}/backup-codes", json=body)

        assert response.status_code == 403
        assert audit_rows(committed_sessions, account_security_audit_actions.BACKUP_CODES_GENERATE) == []
