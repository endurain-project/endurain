"""The SSO token exchange audits the sign-ins it refuses as ``auth.session.login`` rows."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing

import core.exceptions as core_exceptions
import modules.auth.authentication.sso_exchange_service as sso_exchange_service

_SERVICE = "modules.auth.authentication.sso_exchange_service"
_LOGIN = "auth.session.login"
_USER = SimpleNamespace(id=5, username="alice", active=True, access_type="regular")


def _exchange(
    db, *, state_cleared=False, pkce_error=None, inactive=False, claimed=True, header="web", stamp=0, between=None
):
    oauth_state = SimpleNamespace(
        id="state",
        purpose="login",
        code_challenge="c",
        code_challenge_method="S256",
        client_type="web",
        idp_id=3,
        security_generation=stamp,
    )
    session = SimpleNamespace(
        user_id=5,
        tokens_exchanged=False,
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        client_type="web",
        amr=["fed"],
    )
    inactive_error = core_exceptions.PermissionDeniedError("Inactive user") if inactive else None
    tokens = ("sid", datetime(2026, 11, 1, tzinfo=UTC), "at", datetime(2026, 12, 1, tzinfo=UTC), "rt", "csrf")
    with (
        patch(
            f"{_SERVICE}.sessions_integration.get_session_with_oauth_state",
            return_value=(session, None if state_cleared else oauth_state),
        ),
        patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier", side_effect=pkce_error),
        patch(f"{_SERVICE}.users_integration.require_user", return_value=_USER),
        patch(f"{_SERVICE}.users_integration.require_active_user", side_effect=inactive_error),
        patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.authentication_token_service.create_tokens", return_value=tokens),
        patch(
            f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange",
            return_value=datetime(2027, 1, 1, tzinfo=UTC) if claimed else None,
        ),
        patch(
            f"{_SERVICE}.known_devices_integration.record_sign_in",
            return_value=MagicMock(device_id="d" * 43, new_device=False),
        ),
        jasil_testing.capture_audit() as audit,
    ):
        if between is not None:
            between()
        try:
            sso_exchange_service.exchange_tokens_for_session(
                "sid",
                "verifier",
                None,
                header,
                "127.0.0.1",
                "agent",
                MagicMock(),
                MagicMock(),
                MagicMock(),
                db,
                device_id=None,
            )
        except core_exceptions.DomainError as err:
            return audit, err
    return audit, None


def _assert_refusal(audit, *, outcome, reason):
    entry = audit.assert_audited(_LOGIN, outcome=outcome, target_type="user", target_id="5", target_owner_id="5")
    assert entry.details == {"method": "identity_provider", "mfa": False, "reason": reason, "new_device": False}


def test_a_pkce_mismatch_is_audited_and_still_refused(mock_db):
    error = core_exceptions.InvalidInputError("PKCE verification failed")

    audit, raised = _exchange(mock_db, pkce_error=error)

    assert raised is error
    _assert_refusal(audit, outcome="failure", reason="pkce_mismatch")


def test_a_header_other_than_the_stored_client_type_is_audited_like_a_pkce_mismatch(mock_db):
    audit, raised = _exchange(mock_db, header="mobile")

    assert isinstance(raised, core_exceptions.InvalidInputError)
    assert raised.detail == "Invalid code_verifier"
    _assert_refusal(audit, outcome="failure", reason="pkce_mismatch")


def test_a_lost_exchange_race_answers_like_a_replay(mock_db):
    _, raised = _exchange(mock_db, claimed=False)

    assert isinstance(raised, core_exceptions.NotFoundError)
    assert raised.detail == "Session not found or not eligible for token exchange"


def test_a_replay_after_the_first_exchange_finds_no_state_and_answers_not_found(mock_db):
    _, raised = _exchange(mock_db, state_cleared=True)

    assert isinstance(raised, core_exceptions.NotFoundError)
    assert raised.detail == "Session not found or not eligible for token exchange"


def test_an_inactive_user_is_audited(mock_db):
    audit, raised = _exchange(mock_db, inactive=True)

    assert isinstance(raised, core_exceptions.PermissionDeniedError)
    _assert_refusal(audit, outcome="denied", reason="inactive")


def test_a_successful_exchange_writes_only_its_success_row(mock_db):
    audit, raised = _exchange(mock_db)

    assert raised is None
    entry = audit.assert_audited(_LOGIN, outcome="success")
    assert entry.details["reason"] is None
    assert len([e for e in audit.entries if e.action_id == _LOGIN]) == 1


def test_a_security_change_since_the_session_was_created_refuses_the_exchange_and_issues_nothing(
    mock_db, security_generations
):
    audit, raised = _exchange(mock_db, between=lambda: security_generations.stage_bump(5, mock_db))

    assert isinstance(raised, core_exceptions.NotFoundError)
    assert raised.detail == "Session not found or not eligible for token exchange"
    _assert_refusal(audit, outcome="failure", reason="security_changed")


def test_a_session_whose_state_has_no_stamp_is_refused(mock_db):
    audit, raised = _exchange(mock_db, stamp=None)

    assert isinstance(raised, core_exceptions.NotFoundError)
    _assert_refusal(audit, outcome="failure", reason="security_changed")


def test_a_session_under_the_current_generation_still_exchanges(mock_db, security_generations):
    security_generations.generations[5] = 3

    audit, raised = _exchange(mock_db, stamp=3)

    assert raised is None
    audit.assert_audited(_LOGIN, outcome="success")
