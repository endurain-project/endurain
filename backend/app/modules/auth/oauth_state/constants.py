"""OAuth-state constants."""

from enum import StrEnum

#: How long a state, and anything bound to it in the browser, stays valid.
STATE_TTL_SECONDS = 600


class OAuthStatePurpose(StrEnum):
    """What an OAuth state's flow is for, so the callback never infers it from which columns are set.

    Attributes:
        LOGIN: Sign in, and create the account on first use.
        LINK: Link the provider account to the signed-in user.
        STEP_UP: Prove a fresh provider sign-in before a sensitive change of the signed-in user.
    """

    LOGIN = "login"
    LINK = "link"
    STEP_UP = "step_up"
