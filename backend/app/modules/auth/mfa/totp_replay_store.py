"""Single-use rule for accepted TOTP time steps, backed by the platform state.

A TOTP code stays valid for its own 30-second step and one step either side, so without a record a code
read off a screen or a log can be replayed for about 90 seconds. Accepting each step once per user, in the
shared state store, closes that across every replica.
"""

import hmac
from datetime import datetime

import pyotp
from jasil.providers import StateBackendUnavailableError, StateProvider

import core.exceptions as core_exceptions

_KEY_PREFIX = "endurain:auth:mfa:totp_step"
# A code can match the current step and one either side, so a claim must outlive all three steps (90 s).
_CLAIM_TTL_SECONDS = 120
_DRIFT_STEPS = 1


def matching_totp_step(secret: str, token: str, now: datetime) -> int | None:
    """Find the time step a TOTP code was generated for, allowing one step of clock drift either way.

    Args:
        secret: Base32-encoded TOTP secret.
        token: The submitted code.
        now: The instant to check the code against.

    Returns:
        The matching time step, or None when the code matches none of the accepted steps.
    """
    totp = pyotp.TOTP(secret)
    current = totp.timecode(now)
    matched: int | None = None
    # Every candidate is compared, so the time taken does not reveal which step matched.
    for step in (current, *(current + offset for offset in range(-_DRIFT_STEPS, _DRIFT_STEPS + 1) if offset)):
        if hmac.compare_digest(token, totp.generate_otp(step)) and matched is None:
            matched = step
    return matched


def claim_totp_step(state: StateProvider, user_id: int, step: int) -> bool:
    """Record a user's TOTP time step as used, once.

    Args:
        state: The platform state provider.
        user_id: The user whose code was accepted.
        step: The time step the code matched.

    Returns:
        True when this call used the step, False when it was already used.

    Raises:
        ServiceUnavailableError: When the state store cannot be reached. The code is refused rather than
            accepted without the replay check.
    """
    try:
        return state.set_if_absent(f"{_KEY_PREFIX}:{user_id}:{step}", b"1", _CLAIM_TTL_SECONDS)
    except StateBackendUnavailableError as err:
        raise core_exceptions.ServiceUnavailableError("MFA verification temporarily unavailable") from err
