"""Behavior published by the sign-up-token module to other packages."""

from collections.abc import Collection

from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.service as sign_up_service


def revoke_pending_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens with the caller's pending user update."""
    sign_up_service.revoke_user_tokens(user_id, db)


def request_email_change(user_id: int, email: str, previous_email: str, db: Session) -> bool:
    """Stage a pending email change and its confirmation event with the caller's transaction.

    Args:
        user_id: The user whose address changes.
        email: The pending address to confirm.
        previous_email: The user's current address, which the confirmation replaces.
        db: Database session.

    Returns:
        True when the change was staged, False when mail is not configured and nothing was staged.
    """
    return sign_up_service.request_email_change(user_id, email, previous_email, db)


def get_pending_email_changes(
    user_ids: Collection[int], db: Session
) -> dict[int, sign_up_contracts.PendingEmailChange]:
    """Return the unconfirmed email change of each given user that has one, keyed by user id."""
    return sign_up_service.get_pending_email_changes(user_ids, db)


def request_email_change_resend(user_id: int, state: StateProvider, db: Session) -> None:
    """Stage a new confirmation email for a user's pending change, at most once per cooldown; the caller commits."""
    sign_up_service.request_email_change_resend(user_id, state, db)


def request_sign_up_approved_email(user_id: int, db: Session) -> bool:
    """Stage an approval notice event with the caller's pending user update."""
    return sign_up_service.request_sign_up_approved_email(user_id, db)
