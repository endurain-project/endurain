"""Sign-in audit rows other auth packages write: the refusals and the target of a row about a user."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypedDict

import jasil.audit as jasil_audit

import modules.auth.login_audit.audit_actions as login_audit_actions


class AuditTarget(TypedDict, total=False):
    """The audit target keywords that name a user."""

    target_type: str
    target_id: str
    target_owner_id: str


def user_target(user_id: uuid.UUID | None) -> AuditTarget:
    """Name the user an audit row is about, in the keywords the audit calls take.

    Args:
        user_id: The user, or None when no account is known.

    Returns:
        The target keywords, empty when no account is known.
    """
    if user_id is None:
        return {}
    return {"target_type": "user", "target_id": str(user_id), "target_owner_id": str(user_id)}


@contextmanager
def acting_as_user(user_id: uuid.UUID) -> Iterator[None]:
    """Attribute the audit rows written inside the block to a user who signed in with an OAuth provider.

    For a route that is not behind an auth dependency, so its request audit context is anonymous, when the
    flow has already proven who the user is.

    Args:
        user_id: The user who acts.

    Yields:
        Nothing; the rows written inside the block name the user as the actor.
    """
    with jasil_audit.audit_context(
        actor_type=jasil_audit.ActorType.USER, actor_id=str(user_id), credential_type="oauth"
    ):
        yield


def record_login_refusal(
    method: login_audit_actions.LoginMethod,
    outcome: jasil_audit.Outcome,
    reason: login_audit_actions.LoginFailureReason,
    *,
    mfa: bool = False,
    user_id: uuid.UUID | None = None,
) -> None:
    """Record a refused sign-in, on its own transaction because nothing was changed to join.

    Args:
        method: How the sign-in was attempted.
        outcome: ``FAILURE`` for a wrong credential, token or state, ``DENIED`` for a refusal by policy.
        reason: Why the sign-in was refused.
        mfa: Whether the refused step was the second factor.
        user_id: The account the sign-in named, or None when no account matched; the attempted username is
            never recorded.
    """
    jasil_audit.record_detached(
        login_audit_actions.LOGIN,
        outcome=outcome,
        **user_target(user_id),
        details=login_audit_actions.LoginDetails(method=method, mfa=mfa, reason=reason),
    )
