"""Audit rows of the administrator's session deletions."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.schema as auth_schema
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.auth.sessions.service as sessions_service

_STEP_UP = auth_schema.StepUpVerification(current_password="admin-password")
_ACTION = sessions_audit_actions.SESSION_REVOKE.id


def test_one_session_delete_is_audited_against_the_session(mock_db):
    with (
        patch.object(sessions_service, "stage_delete_session"),
        jasil_testing.capture_audit() as audit,
    ):
        sessions_service.delete_session("sess-1", 7, _STEP_UP, MagicMock(), mock_db)

    entry = audit.assert_audited(_ACTION, target_type="session", target_id="sess-1", target_owner_id="7")
    assert entry.details == {"sessions_revoked": 1}
    mock_db.commit.assert_called_once()


def test_a_missing_session_is_not_audited(mock_db):
    with (
        patch.object(sessions_service, "stage_delete_session", side_effect=core_exceptions.NotFoundError("x")),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.NotFoundError),
    ):
        sessions_service.delete_session("sess-1", 7, _STEP_UP, MagicMock(), mock_db)

    audit.assert_not_audited(_ACTION)


def test_a_bulk_delete_is_audited_against_the_user_with_the_count(mock_db):
    with (
        patch.object(sessions_service.sessions_crud, "delete_sessions_by_user", return_value=3),
        jasil_testing.capture_audit() as audit,
    ):
        sessions_service.delete_sessions_by_user_and_commit(
            7, _STEP_UP, MagicMock(), mock_db, exclude_session_id="keep"
        )

    entry = audit.assert_audited(_ACTION, target_type="user", target_id="7", target_owner_id="7")
    assert entry.details == {"sessions_revoked": 3}
    mock_db.commit.assert_called_once()


def test_a_bulk_delete_that_removes_nothing_is_not_audited(mock_db):
    with (
        patch.object(sessions_service.sessions_crud, "delete_sessions_by_user", return_value=0),
        jasil_testing.capture_audit() as audit,
    ):
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, MagicMock(), mock_db)

    audit.assert_not_audited(_ACTION)


def test_the_staged_delete_used_by_logout_and_self_revocation_adds_no_row(mock_db):
    with (
        patch.object(sessions_service.sessions_crud, "delete_session") as delete,
        patch.object(sessions_service.oauth_state_integration, "delete_oauth_state"),
        patch.object(sessions_service.rotated_refresh_tokens_integration, "delete_by_family"),
        jasil_testing.capture_audit() as audit,
    ):
        delete.return_value.oauth_state_id = None
        sessions_service.stage_delete_session("sess-1", 7, mock_db)

    audit.assert_not_audited(_ACTION)
