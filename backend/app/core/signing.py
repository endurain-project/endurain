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

Every token carries an embedded issue timestamp, but verification only checks it
when the caller passes ``max_age`` — omitting it (the default) keeps a token
valid forever, stable and cacheable, exactly as before. Pass ``max_age`` for a
value that can be revisited after the access decision it was minted from has
changed (e.g. an activity's visibility): a bounded token self-heals on every
fresh view, because the value is re-serialized and re-signed with a new
timestamp each time, while still tolerating the caller's own HTTP cache window.
Their security still rests on being unforgeable and only ever handed to
permitted viewers — an unexpired token is not re-checked against the current
access decision, only against its own signature and age.
"""

import functools

from itsdangerous import BadData, URLSafeTimedSerializer

import core.config as core_config


@functools.cache
def _serializer(salt: str) -> URLSafeTimedSerializer:
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
    return URLSafeTimedSerializer(secret, salt=salt)


def sign_token(salt: str, value: object) -> str:
    """Return a signed, URL-safe token binding ``value`` to ``salt``.

    Args:
        salt: Namespace for this family of tokens.
        value: JSON-serializable value to bind into the token.

    Returns:
        An unforgeable, URL-safe token, timestamped at signing time.
    """
    return _serializer(salt).dumps(value)


def verify_token(salt: str, value: object, token: str, *, max_age: int | None = None) -> bool:
    """Return whether ``token`` is an authentic, unexpired signature of ``value``.

    Args:
        salt: Namespace the token must have been minted under.
        value: The value the token must be bound to.
        token: The token supplied by the caller.
        max_age: Oldest acceptable age in seconds. ``None`` (default) skips the
            age check entirely, matching a token minted with no expiry in mind.

    Returns:
        True when the token is authentic, bound to ``value``, and (when
        ``max_age`` is given) not older than it.
    """
    try:
        return _serializer(salt).loads(token, max_age=max_age) == value
    except BadData:
        return False
