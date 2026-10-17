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
from dataclasses import dataclass

import jasil.runtime as platform_runtime
from itsdangerous import BadData, URLSafeTimedSerializer

import core.config as core_config

#: How long a capability token stays valid. Every blob signer used to declare
#: this itself, each with a comment saying it was "kept identical for
#: consistency across the three signers" — which is a rule three files cannot
#: enforce between them.
#:
#: Bounded rather than eternal because the access decision a token was minted
#: from can change afterwards (an activity is hidden, a photo replaced). The
#: window self-heals: re-serializing the resource mints a fresh token, so this
#: only caps how long an *already issued* token outlives the change. Kept
#: comfortably longer than the routes' browser cache window so a still-cached
#: image never 404s mid-cache.
DEFAULT_TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60


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


@dataclass(frozen=True)
class CapabilitySigner:
    """A salt plus its token lifetime, bound together.

    Each blob subsystem (activity thumbnails, activity media, user photos) needs
    exactly the same pair of one-line wrappers around :func:`sign_token` and
    :func:`verify_token`, differing only in the salt — and each was passing its
    own copy of the max age on every verify, where forgetting it would silently
    turn a bounded token into an eternal one. Pairing the two here means the
    lifetime cannot be dropped at a call site.

    Attributes:
        salt: Namespaces this family of tokens; a token minted under one salt
            never validates under another.
        max_age_seconds: Oldest acceptable token age, applied by
            :meth:`verify`.
    """

    salt: str
    max_age_seconds: int = DEFAULT_TOKEN_MAX_AGE_SECONDS

    def sign(self, value: object) -> str:
        """Return a signed, URL-safe token binding ``value`` to this salt."""
        return sign_token(self.salt, value)

    def verify(self, value: object, token: str) -> bool:
        """Return whether ``token`` authentically binds ``value`` and is unexpired."""
        return verify_token(self.salt, value, token, max_age=self.max_age_seconds)


def blob_url(area: str, key: str, *, local_path: str, token: str) -> str:
    """Return a servable URL for a stored blob, however it is stored.

    Object storage already issues presigned, expiring, ``<img>``-compatible URLs,
    so those are used directly rather than round-tripping every blob through the
    app. Local disk has no such concept, so the blob is served by a token-gated
    route instead of a public static mount, and the capability travels as ``?t=``.

    Falls back to the local route when the platform is not yet initialised
    (``RuntimeError``), which is what keeps serialization working outside a
    running app (tests, migrations).

    Args:
        area: The domain-owned storage namespace the blob lives under.
        key: The stored storage key.
        local_path: Route path serving the blob, relative to the API root.
        token: The signed capability token for this blob.

    Returns:
        A servable URL.
    """
    if core_config.settings.resolved_storage_uri.startswith("s3"):
        try:
            return platform_runtime.get_active_platform().storage.url(area, key)
        except RuntimeError:
            pass
    return f"{core_config.ROOT_PATH}{local_path}?t={token}"
