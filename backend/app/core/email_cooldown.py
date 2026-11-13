"""Per-account cooldown on emails that anyone can trigger without signing in.

A password-reset request or a sign-up with a registered address looks the same whoever sends it, so
anyone can aim it at one inbox. Allowing one email per account per cooldown, in the platform
``StateProvider`` (in-process under ``local``, Redis under ``distributed``), keeps a single address
from being flooded across every replica.
"""

import uuid

from jasil.providers import StateProvider


def claim_email(
    state: StateProvider, kind: str, user_id: uuid.UUID, cooldown_seconds: int, *, claimant: str | None = None
) -> bool:
    """Record that an account is being sent an email, unless one of this kind went out within the cooldown.

    The claim is one atomic ``set_if_absent``, so two requests racing across replicas cannot both send. With a
    ``claimant`` the claim is stored under that name, and the claimant that holds it may claim again, so a retry
    of the same work is not refused by its own earlier claim. Anyone else is refused until the cooldown ends.

    Args:
        state: The platform state provider.
        kind: Which email this is, e.g. ``password_reset``.
        user_id: The account the email goes to.
        cooldown_seconds: How long after a send the next one is refused.
        claimant: Names who holds the claim, e.g. the id of the event being handled.

    Returns:
        True when the email may be sent, False when one was sent within the cooldown.

    Raises:
        StateBackendUnavailableError: When the state store cannot be reached.
    """
    key = f"endurain:auth:email_cooldown:{kind}:{user_id}"
    value = b"1" if claimant is None else claimant.encode()
    if state.set_if_absent(key, value, cooldown_seconds):
        return True
    if claimant is None:
        return False
    holder = state.get(key)
    if holder is None:
        return state.set_if_absent(key, value, cooldown_seconds)
    return holder == value
