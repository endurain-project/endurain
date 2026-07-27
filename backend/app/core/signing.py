"""Signed capability tokens derived from the server ``SECRET_KEY``.

A capability URL carries its own authorization: the token is unforgeable, bound
to a specific value, and travels in the URL so it works in contexts that cannot
send an ``Authorization`` header (``<img src>``, downloads, redirects). This
module is the single place such tokens are minted and verified, so every feature
that needs one shares the same secret handling and salt discipline instead of
re-deriving a serializer of its own.

Each caller supplies its own ``salt``, which namespaces its tokens: a token minted
for one salt never validates under another, so an activity-thumbnail token can
never be replayed against a different feature that happens to use the same id.

Tokens carry no expiry, which keeps the resulting URL stable and cacheable. Their
security rests on being unforgeable and only ever handed to permitted viewers, so
do not use them to gate anything that must be revocable.
"""

import functools

from itsdangerous import BadData, URLSafeSerializer

import core.config as core_config


@functools.cache
def _serializer(salt: str) -> URLSafeSerializer:
    """Return the process-wide signer for a salt (secret read once per salt).

    Args:
        salt: Namespace for this family of tokens.

    Returns:
        The cached serializer.

    Raises:
        RuntimeError: When ``SECRET_KEY`` is not configured.
    """
    secret = core_config.read_secret("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured; cannot sign capability tokens")
    return URLSafeSerializer(secret, salt=salt)


def sign_token(salt: str, value: object) -> str:
    """Return a signed, URL-safe token binding ``value`` to ``salt``.

    Args:
        salt: Namespace for this family of tokens.
        value: JSON-serializable value to bind into the token.

    Returns:
        An unforgeable, URL-safe token.
    """
    return _serializer(salt).dumps(value)


def verify_token(salt: str, value: object, token: str) -> bool:
    """Return whether ``token`` is an authentic signature of ``value``.

    Args:
        salt: Namespace the token must have been minted under.
        value: The value the token must be bound to.
        token: The token supplied by the caller.

    Returns:
        True when the token is authentic and bound to ``value``.
    """
    try:
        return _serializer(salt).loads(token) == value
    except BadData:
        return False
