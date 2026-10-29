"""Per-account cooldown on emails that anyone can trigger without signing in.

A password-reset request or a sign-up with a registered address looks the same whoever sends it, so
anyone can aim it at one inbox. Allowing one email per account per cooldown, in the platform
``StateProvider`` (in-process under ``local``, Redis under ``distributed``), keeps a single address
from being flooded across every replica.
"""

from jasil.providers import StateProvider


def claim_email(state: StateProvider, kind: str, user_id: int, cooldown_seconds: int) -> bool:
    """Record that an account is being sent an email, unless one of this kind went out within the cooldown.

    The claim is one atomic ``set_if_absent``, so two requests racing across replicas cannot both send.

    Args:
        state: The platform state provider.
        kind: Which email this is, e.g. ``password_reset``.
        user_id: The account the email goes to.
        cooldown_seconds: How long after a send the next one is refused.

    Returns:
        True when the email may be sent, False when one was sent within the cooldown.

    Raises:
        StateBackendUnavailableError: When the state store cannot be reached.
    """
    return state.set_if_absent(f"endurain:auth:email_cooldown:{kind}:{user_id}", b"1", cooldown_seconds)
