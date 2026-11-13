"""Builders for the sign-in records the auth tests put in the stores."""

import uuid

import modules.auth.constants as auth_constants
import modules.auth.mfa.dependencies as mfa_dependencies

#: The id of the signed-in user the test app's overridden principal carries.
MOCK_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
#: The id of a second user, for tests that need someone else.
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def pending_login(
    user_id: uuid.UUID = MOCK_USER_ID,
    client_type: auth_constants.ClientType = auth_constants.ClientType.WEB,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    client_network: str = "127.0.0.1",
    security_generation: int | None = 0,
) -> mfa_dependencies.PendingLogin:
    """Return a pending MFA login; a web login by default, which carries no PKCE challenge."""
    return mfa_dependencies.PendingLogin(
        user_id=user_id,
        client_type=client_type,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        client_network=client_network,
        security_generation=security_generation,
    )
