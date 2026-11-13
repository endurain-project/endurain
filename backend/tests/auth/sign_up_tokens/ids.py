"""Deterministic UUIDs for the token ids the tests name by label."""

import uuid


def tid(label: str) -> uuid.UUID:
    """Return the same UUID for the same label.

    Args:
        label: A short name for a token or an email change.

    Returns:
        A UUID derived from the label.
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, f"endurain-test-token:{label}")
