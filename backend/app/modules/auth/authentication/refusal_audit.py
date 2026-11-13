"""Audit rows for refused refreshes, shared by the authentication workflows."""

from __future__ import annotations

import uuid
from contextlib import AbstractContextManager

import jasil.audit as jasil_audit

import core.logger as core_logger
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration

logger = core_logger.get_logger(__name__)


def refresh_token_context(user_id: uuid.UUID) -> AbstractContextManager[jasil_audit.AuditContext]:
    """Name the user whose refresh token a request presented as its audit actor.

    A request that carries only a refresh token has no principal for the audit context to read.

    Args:
        user_id: The user the signed refresh token names.

    Returns:
        A context manager that sets the actor for the rows staged inside it.
    """
    return jasil_audit.audit_context(
        actor_type=jasil_audit.ActorType.USER, actor_id=str(user_id), credential_type="refresh_token"
    )


def record_refresh_refusal(
    user_id: uuid.UUID, outcome: jasil_audit.Outcome, reason: authentication_audit_actions.RefreshRefusalReason
) -> None:
    """Record a refused session refresh, on its own transaction because the request answers with an error.

    Args:
        user_id: The user the signed refresh token names.
        outcome: ``FAILURE`` for a token or session that is not valid, ``DENIED`` for a refusal by policy.
        reason: Why the refresh was refused.
    """
    with refresh_token_context(user_id):
        jasil_audit.record_detached(
            authentication_audit_actions.REFRESH,
            outcome=outcome,
            **login_audit_integration.user_target(user_id),
            details=authentication_audit_actions.RefreshRefusalDetails(reason=reason),
        )
