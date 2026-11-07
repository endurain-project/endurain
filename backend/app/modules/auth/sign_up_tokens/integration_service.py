"""Behavior published by the sign-up-token module to other packages."""

from collections.abc import Collection

from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.service as sign_up_service


def revoke_pending_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens with the caller's pending user update."""
    sign_up_service.revoke_user_tokens(user_id, db)


def stage_email_changed_notice(user_id: int, email: str, previous_email: str, db: Session) -> None:
    """Stage the notice to the previous address that an applied email change took effect, with the caller's transaction.

    Args:
        user_id: The user whose address changed.
        email: The address the account now uses.
        previous_email: The address the account had, which receives the notice.
        db: Database session.
    """
    sign_up_service.stage_email_changed_notice(user_id, email, previous_email, db)


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


def request_self_service_email_change(
    user_id: int, email: str, previous_email: str, state: StateProvider, db: Session
) -> bool:
    """Stage a user's own pending email change with the caller's transaction.

    A free address is mailed a confirmation link; an address another account holds is not, and its holder is told
    instead. Both are staged alike.

    Args:
        user_id: The user whose address changes.
        email: The pending address.
        previous_email: The user's current address, which the confirmation replaces.
        state: The platform state provider, for the holder's notice cooldown.
        db: Database session.

    Returns:
        True when the change was staged, False when mail is not configured and nothing was staged.
    """
    return sign_up_service.request_self_service_email_change(user_id, email, previous_email, state, db)


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
