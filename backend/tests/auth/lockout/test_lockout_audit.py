"""A lockout applied by a failed attempt is audited against the account, never with the username."""

import uuid

import jasil.testing as jasil_testing
import pytest

import core.config as core_config
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user

_USER_ID = uuid.UUID(int=7)

_ACTION = lockout_audit_actions.LOCKOUT_APPLY.id


@pytest.mark.parametrize(
    ("store_name", "tiers"),
    [
        ("login", lockout_contracts.LOGIN_LOCKOUT_TIERS),
        ("mfa", lockout_contracts.MFA_LOCKOUT_TIERS),
        ("mfa_account", lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS),
        ("step_up", lockout_contracts.STEP_UP_LOCKOUT_TIERS),
        ("step_up_account", lockout_contracts.ACCOUNT_STEP_UP_LOCKOUT_TIERS),
    ],
)
def test_a_lockout_is_audited_with_its_counter_and_count(store_name, tiers):
    attempts = tiers[0][0]
    with jasil_testing.capture_audit() as audit:
        lockout_integration.report_lockout_applied(store_name, tiers, attempts, user_id=_USER_ID)

    entry = audit.assert_audited(
        _ACTION, outcome="success", target_type="user", target_id=str(_USER_ID), target_owner_id=str(_USER_ID)
    )
    assert entry.details == {"counter": store_name, "failed_attempts": attempts}
    assert len(audit.matching(_ACTION)) == 1


def test_a_lockout_with_no_known_account_has_no_target_and_no_username():
    with jasil_testing.capture_audit() as audit:
        lockout_integration.report_lockout_applied(
            "login", lockout_contracts.LOGIN_LOCKOUT_TIERS, 5, username="alice@example.com"
        )

    entry = audit.assert_audited(_ACTION, outcome="success")
    assert entry.details == {"counter": "login", "failed_attempts": 5}
    assert entry.target_type is None
    assert entry.target_id is None
    assert "alice" not in repr(entry)


def test_a_count_below_the_first_tier_writes_nothing():
    with jasil_testing.capture_audit() as audit:
        lockout_integration.report_lockout_applied("login", lockout_contracts.LOGIN_LOCKOUT_TIERS, 4, user_id=_USER_ID)

    audit.assert_not_audited(_ACTION)


def test_a_refused_step_up_that_locks_the_user_audits_the_lockout_against_them(committed_sessions, sign_in):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    owner = sign_in(user)
    tier = lockout_contracts.STEP_UP_LOCKOUT_TIERS[0][0]
    body = {"name": "k", "scopes": ["activities:upload"], "step_up": {"current_password": "wrong"}}

    statuses = [
        owner.client.post(f"{core_config.ROOT_PATH}/profile/api-keys", json=body).status_code for _ in range(tier)
    ]

    assert statuses == [403] * tier
    (row,) = audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY)
    assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
        "success",
        "user",
        str(user.id),
        str(user.id),
    )
    assert row.details == {"counter": "step_up", "failed_attempts": tier}
