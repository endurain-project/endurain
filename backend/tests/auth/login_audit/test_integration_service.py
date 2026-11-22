"""The login-audit helper that names a proven user as the actor of the rows written inside it."""

import jasil.audit as jasil_audit
import jasil.testing as jasil_testing

import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration


def _refuse() -> None:
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.IDENTITY_PROVIDER,
        jasil_audit.Outcome.FAILURE,
        login_audit_actions.LoginFailureReason.INVALID_STATE,
    )


def test_rows_inside_the_block_name_the_user_as_an_oauth_actor_and_the_context_is_restored():
    with jasil_testing.capture_audit() as audit:
        with login_audit_integration.acting_as_user(7):
            _refuse()
        _refuse()

    inside, outside = audit.matching(login_audit_actions.LOGIN.id)
    assert (inside.actor_type, inside.actor_id, inside.credential_type) == ("user", "7", "oauth")
    assert outside.actor_type != "user"
    assert outside.actor_id is None
