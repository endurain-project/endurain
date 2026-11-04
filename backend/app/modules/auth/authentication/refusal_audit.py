"""Audit rows for refused sign-ins and refreshes, shared by the authentication workflows."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TypedDict

import jasil.audit as jasil_audit

import core.logger as core_logger
import modules.auth.authentication.audit_actions as authentication_audit_actions

logger = core_logger.get_logger(__name__)


def record_login_refusal(
    method: authentication_audit_actions.LoginMethod,
    outcome: jasil_audit.Outcome,
    reason: authentication_audit_actions.LoginFailureReason,
    *,
    mfa: bool = False,
    user_id: int | None = None,
) -> None:
    """Record a refused password sign-in, on its own transaction because nothing was changed to join.

    Args:
        method: How the sign-in was attempted.
        outcome: ``FAILURE`` for a wrong credential, ``DENIED`` for a refusal by policy.
        reason: Why the sign-in was refused.
        mfa: Whether the refused step was the second factor.
        user_id: The account the sign-in named, or None when no account matched; the attempted username is
            never recorded.
    """
    jasil_audit.record_detached(
        authentication_audit_actions.LOGIN,
        outcome=outcome,
        **user_target(user_id),
        details=authentication_audit_actions.LoginDetails(method=method, mfa=mfa, reason=reason),
    )


class _AuditTarget(TypedDict, total=False):
    """The audit target keywords that name a user."""

    target_type: str
    target_id: str
    target_owner_id: str


def user_target(user_id: int | None) -> _AuditTarget:
    """Name the user an audit row is about, in the keywords the audit calls take.

    Args:
        user_id: The user, or None when no account is known.

    Returns:
        The target keywords, empty when no account is known.
    """
    if user_id is None:
        return {}
    return {"target_type": "user", "target_id": str(user_id), "target_owner_id": str(user_id)}


def refresh_token_context(user_id: int) -> AbstractContextManager[jasil_audit.AuditContext]:
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
    user_id: int, outcome: jasil_audit.Outcome, reason: authentication_audit_actions.RefreshRefusalReason
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
            **user_target(user_id),
            details=authentication_audit_actions.RefreshRefusalDetails(reason=reason),
        )
