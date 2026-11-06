"""Signed capability tokens keyed from the server ``SECRET_KEY``.

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
fresh view, because the value is re-serialized and re-signed with the current
bucket's timestamp, while still tolerating the caller's own HTTP cache window.
A capability signer rounds that timestamp down to a bucket, so repeated reads
inside one bucket return the same URL and the browser cache can serve it.
Their security still rests on being unforgeable and only ever handed to
permitted viewers — an unexpired token is not re-checked against the current
access decision, only against its own signature and age.
"""

import functools
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import jasil.runtime as platform_runtime
from itsdangerous import BadData, TimestampSigner, URLSafeTimedSerializer

import core.config as core_config
import core.key_derivation as core_key_derivation

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

#: How coarsely a capability token's issue time is rounded down, so every mint for the same value inside one
#: bucket is the same token and so the same URL. The browser caches a blob response per URL, and a token that
#: changed on every read (its timestamp is part of it) made every cached response unreachable.
#:
#: A token minted at ``t`` is stamped ``t - t % bucket``, so it is at most one bucket "older" than it is, and
#: is valid for at least ``max_age - bucket`` after it is handed out and never beyond ``max_age`` from now.
#: With the 24 h lifetime and a 6 h bucket a URL is therefore good for 18 to 24 h from the read that returned
#: it, against the 1 h the blob routes let a browser reuse a response (``core.http_cache``): a response cached
#: from a URL is never cached past that URL's expiry.
DEFAULT_TOKEN_BUCKET_SECONDS = 6 * 60 * 60


class _BucketedTimestampSigner(TimestampSigner):
    """A timestamp signer that rounds the issue time down to a bucket.

    The signature is over the rounded time, so verification is the ordinary timed check and needs no bucket.

    Attributes:
        bucket_seconds: Width of the bucket the issue time is rounded down to; 1 keeps the exact second.
    """

    def __init__(self, *args: Any, bucket_seconds: int = 1, **kwargs: Any) -> None:
        """Build the signer.

        Args:
            *args: Positional arguments of :class:`itsdangerous.TimestampSigner`.
            bucket_seconds: Width of the bucket the issue time is rounded down to.
            **kwargs: Keyword arguments of :class:`itsdangerous.TimestampSigner`.
        """
        super().__init__(*args, **kwargs)
        self.bucket_seconds = bucket_seconds

    def get_timestamp(self) -> int:
        """Return the current time rounded down to the bucket."""
        now = super().get_timestamp()
        return now - now % self.bucket_seconds


@functools.cache
def _serializer(salt: str, bucket_seconds: int = 1) -> URLSafeTimedSerializer:
    """Return the process-wide signer for a salt (key derived once per salt).

    Args:
        salt: Namespace for this family of tokens.
        bucket_seconds: Width of the bucket the issue time is rounded down to; 1 keeps the exact second.

    Returns:
        The cached serializer.

    Raises:
        RuntimeError: When ``SECRET_KEY`` is not configured.
    """
    key = core_key_derivation.derive_key(core_key_derivation.CAPABILITY_URLS)
    if not key:
        raise RuntimeError("SECRET_KEY is not configured; cannot sign capability tokens")
    return URLSafeTimedSerializer(
        key, salt=salt, signer=_BucketedTimestampSigner, signer_kwargs={"bucket_seconds": bucket_seconds}
    )


def sign_token(salt: str, value: object, *, bucket_seconds: int = 1) -> str:
    """Return a signed, URL-safe token binding ``value`` to ``salt``.

    Args:
        salt: Namespace for this family of tokens.
        value: JSON-serializable value to bind into the token.
        bucket_seconds: Width of the bucket the issue time is rounded down to, so two calls inside one bucket
            return the same token; 1 (default) stamps the exact second.

    Returns:
        An unforgeable, URL-safe token, timestamped at signing time (rounded down to the bucket).
    """
    return _serializer(salt, bucket_seconds).dumps(value)


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
        bucket_seconds: Width of the bucket :meth:`sign` rounds the issue time down to, so the same value is
            signed to the same token for the length of a bucket. A token is valid for at least
            ``max_age_seconds - bucket_seconds`` from the moment it is signed.

    Raises:
        ValueError: When the bucket is longer than the lifetime, which would sign tokens already expired.
    """

    salt: str
    max_age_seconds: int = DEFAULT_TOKEN_MAX_AGE_SECONDS
    bucket_seconds: int = DEFAULT_TOKEN_BUCKET_SECONDS

    def __post_init__(self) -> None:
        """Refuse a bucket longer than the lifetime, which would sign a token already expired."""
        if not 0 < self.bucket_seconds <= self.max_age_seconds:
            raise ValueError("bucket_seconds must be positive and no longer than max_age_seconds")

    def sign(self, value: object) -> str:
        """Return a signed, URL-safe token binding ``value`` to this salt."""
        return sign_token(self.salt, value, bucket_seconds=self.bucket_seconds)

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


def blob_origin() -> str | None:
    """Return the origin browsers fetch blobs from, when it is not this server.

    Object storage serves presigned URLs on its own origin, which a
    ``Content-Security-Policy`` must allow or the browser blocks every thumbnail,
    photo and media file. Local storage is served by this server, so it needs
    nothing extra. The origin is read from a real presigned URL rather than
    rebuilt from the storage URI, so it is right for virtual-hosted AWS, path-style
    and S3-compatible endpoints alike.

    Returns:
        ``scheme://host[:port]`` of the storage origin, or ``None`` for local
        storage or when the platform is not initialised.
    """
    if not core_config.settings.resolved_storage_uri.startswith("s3"):
        return None
    try:
        url = platform_runtime.get_active_platform().storage.url("origin_probe", "probe")
    except RuntimeError:
        return None
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None
