"""Pure OAuth-state value generation."""

import secrets


def create_state_id_and_nonce() -> tuple[str, str]:
    """Generate random OAuth state and nonce values."""
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)
