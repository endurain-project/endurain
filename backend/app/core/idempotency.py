"""The ``Idempotency-Key`` header: one grammar for the API, and the replay of a create that a client repeats.

The header follows the IETF draft *The Idempotency-Key HTTP Header Field* (draft-ietf-httpapi-idempotency-key-header):
its value is an RFC 9651 Structured Field String, so only the quoted form is accepted (``"8e03978e-40d5-43e8-bc93"``).
:func:`parse_key` is the one parser; every route that reads the header goes through :data:`IdempotencyKey`.

A route opts in to replay with :data:`Idempotent` in its ``dependencies``, after its authentication. A request without
the header behaves exactly as before and never touches the state store. With the header the request is first
claimed, then served, and its outcome is stored under the key:

1. The :func:`idempotent` dependency fingerprints the request, then looks for a stored result under the caller's id and
   the hash of the key. A matching result is raised as :class:`~core.exceptions.IdempotentReplayError`, which the
   exception handler renders as the original status, stored headers and bytes, so the route never runs again and no
   second row, audit row or event exists. A result recorded for another request is ``422``.
2. Otherwise it claims the key with ``set_if_absent``. The loser sees the winner's fingerprint in the claim: another
   request is ``422``, the same one still running is ``409`` with ``Retry-After``.
3. :class:`IdempotencyMiddleware` acts only on a request that won a claim. It holds the response back, and on a final
   ``2xx`` within :data:`MAX_STORED_BODY` it stores the result before it forwards the last chunk, then frees the claim.
   Any other outcome frees the claim and sends the response on, so a refused request can be retried.

The state lives in the platform ``StateProvider``, so every replica sees the same claims and results. The scope is the
user id: a session and an API key of one user share their keys. The raw key is never stored or logged; the keys of the
store carry its SHA-256. A crash between the commit of the route and the storing of the result leaves a claim that
expires after :data:`CLAIM_TTL_SECONDS`, and a retry after that creates the resource again: an accepted limitation.
"""

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, Request
from jasil.providers import StateBackendUnavailableError, StateProvider
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.attempt_state as core_attempt_state
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.openapi_contract as core_openapi_contract

logger = core_logger.get_logger(__name__)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
#: The longest key, counted in the characters of the string the quotes hold.
MAX_KEY_LENGTH = 255
#: How long a stored result answers a repeat of its request.
RESULT_TTL_SECONDS = 24 * 3600
#: How long a claim holds a key while its request runs. It outlasts a request: the server sets no request timeout, and
#: the database bounds a statement's wait by its lock and pool timeouts of 30 seconds each.
CLAIM_TTL_SECONDS = 120
#: The largest response body that is stored; a larger response is sent and not stored.
MAX_STORED_BODY = 256 * 1024
#: Seconds a client is told to wait before it repeats a request whose first attempt is still running.
IN_FLIGHT_RETRY_AFTER_SECONDS = 1
#: The response headers a replay carries; the rest (rate-limit counters, request ids) are the replay's own.
STORED_HEADERS = frozenset({"content-type", "location", "etag", "content-location", "cache-control"})
#: Where the dependency leaves the claim it won for the middleware, on the request's state.
CLAIM_STATE_KEY = "idempotency_claim"

_NAMESPACE = "idempotency"
_PRINTABLE_FIRST, _PRINTABLE_LAST = 0x20, 0x7E


@dataclass(frozen=True)
class Claim:
    """The hold of one request on one key.

    Attributes:
        claim_key: The state key of the claim.
        result_key: The state key of the result.
        value: What the claim stores: a token no other request stores, then ``|`` and the request's fingerprint.
        fingerprint: The fingerprint of the request that holds the claim.
    """

    claim_key: str
    result_key: str
    value: bytes
    fingerprint: str


@dataclass(frozen=True)
class StoredResult:
    """The recorded outcome of a request.

    Attributes:
        status_code: The status that was sent.
        headers: The allow-listed headers that were sent, with lower-case names.
        body: The body that was sent, byte for byte.
    """

    status_code: int
    headers: list[tuple[str, str]]
    body: bytes


def parse_key(raw: str) -> str:
    r"""Read the value of an ``Idempotency-Key`` header.

    The value is one Structured Field String: printable ASCII between double quotes, ``\\"`` and ``\\\\`` the only
    escapes, 1 to :data:`MAX_KEY_LENGTH` characters. A bare token, a parameter, a list or anything after the closing
    quote is refused.

    Args:
        raw: The header value.

    Returns:
        The string the quotes hold.

    Raises:
        IdempotencyKeyInvalidError: When the value is not such a string.
    """
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        raise core_exceptions.IdempotencyKeyInvalidError
    characters: list[str] = []
    escaped = False
    for character in raw[1:-1]:
        if escaped:
            if character not in '"\\':
                raise core_exceptions.IdempotencyKeyInvalidError
            characters.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"' or not _PRINTABLE_FIRST <= ord(character) <= _PRINTABLE_LAST:
            raise core_exceptions.IdempotencyKeyInvalidError
        else:
            characters.append(character)
    if escaped or not 1 <= len(characters) <= MAX_KEY_LENGTH:
        raise core_exceptions.IdempotencyKeyInvalidError
    return "".join(characters)


def read_key(
    raw: Annotated[
        str | None,
        Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            description=(
                'Optional client-generated key, a quoted string of 1 to 255 printable ASCII characters (`"8e03978e"`). '
                "A repeat of the same request with the same key is answered with the first outcome instead of being "
                "done twice; the same key with another request is refused."
            ),
        ),
    ] = None,
) -> str | None:
    """Return the request's ``Idempotency-Key``, parsed, when it sent one.

    Args:
        raw: The header, if the client sent one.

    Returns:
        The key, or None when the header is absent.

    Raises:
        IdempotencyKeyInvalidError: When the header is not one quoted string (400).
    """
    return None if raw is None else parse_key(raw)


#: The request's parsed ``Idempotency-Key``, or None when it sent none.
IdempotencyKey = Annotated[str | None, Depends(read_key)]


def request_fingerprint(method: str, path: str, query_string: str, body: bytes) -> str:
    """Summarise what a request asks for, so a key reused for another request is noticed.

    The query is sorted by parameter and a JSON body is read and written back in canonical form (sorted keys, no
    whitespace), so a client that re-serialises its body, or reorders its parameters, still repeats the request. A body
    that is not JSON is hashed as it is.

    Args:
        method: The HTTP method.
        path: The resolved request path.
        query_string: The raw query string.
        body: The raw request body.

    Returns:
        A SHA-256 hex digest.
    """
    try:
        canonical = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode() if body else b""
    except ValueError:
        canonical = body
    parts = [
        method.upper(),
        path,
        sorted(parse_qsl(query_string, keep_blank_values=True)),
        hashlib.sha256(canonical).hexdigest(),
    ]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _keys(user_id: uuid.UUID, key: str) -> tuple[str, str]:
    """Return the state keys of a user's claim and result for a key."""
    subject = f"{user_id}:{hashlib.sha256(key.encode()).hexdigest()}"
    return core_attempt_state.key(_NAMESPACE, "claim", subject), core_attempt_state.key(_NAMESPACE, "result", subject)


def _stored_result(state: StateProvider, result_key: str, fingerprint: str) -> StoredResult | None:
    """Read the result under a key, refusing it when another request recorded it.

    Raises:
        IdempotencyKeyReusedError: When the result belongs to a request with another fingerprint.
    """
    raw = state.get(result_key)
    if raw is None:
        return None
    record = json.loads(raw)
    if record["fingerprint"] != fingerprint:
        raise core_exceptions.IdempotencyKeyReusedError
    return StoredResult(record["status"], [tuple(pair) for pair in record["headers"]], base64.b64decode(record["body"]))


def begin(state: StateProvider, user_id: uuid.UUID, key: str, fingerprint: str) -> Claim | StoredResult:
    """Claim a key for a request, or find what an earlier request recorded under it.

    Args:
        state: The platform state provider.
        user_id: The caller; keys are scoped to one user.
        key: The parsed key.
        fingerprint: The request's fingerprint.

    Returns:
        The claim when this request is the first and must run, or the stored result of the request it repeats.

    Raises:
        IdempotencyKeyReusedError: When the key belongs to a request with another fingerprint.
        IdempotencyInFlightError: When the same request is still running.
        StateBackendUnavailableError: When the state store cannot be reached.
    """
    claim_key, result_key = _keys(user_id, key)
    value = f"{uuid.uuid4().hex}|{fingerprint}".encode()
    # A second pass covers a claim that vanished between the two reads: its holder finished (and stored the result
    # first) or it expired.
    for _ in range(2):
        stored = _stored_result(state, result_key, fingerprint)
        if stored is not None:
            return stored
        if state.set_if_absent(claim_key, value, CLAIM_TTL_SECONDS):
            return Claim(claim_key, result_key, value, fingerprint)
        holder = state.get(claim_key)
        if holder is not None:
            if holder.decode().partition("|")[2] != fingerprint:
                raise core_exceptions.IdempotencyKeyReusedError
            raise core_exceptions.IdempotencyInFlightError(retry_after_seconds=IN_FLIGHT_RETRY_AFTER_SECONDS)
    raise core_exceptions.IdempotencyInFlightError(retry_after_seconds=IN_FLIGHT_RETRY_AFTER_SECONDS)


def release(state: StateProvider, claim: Claim) -> None:
    """Free a claim, but only while its holder still holds it.

    Args:
        state: The platform state provider.
        claim: The claim to free.

    Raises:
        StateBackendUnavailableError: When the state store cannot be reached.
    """
    state.delete_if_equals(claim.claim_key, claim.value)


def complete(state: StateProvider, claim: Claim, status_code: int, headers: list[tuple[str, str]], body: bytes) -> None:
    """Record a request's outcome under its key, then free its claim.

    The result is written first, so a repeat that finds the claim gone finds the result. The first completion wins.

    Args:
        state: The platform state provider.
        claim: The claim the request won.
        status_code: The status that is sent.
        headers: The response headers; only :data:`STORED_HEADERS` are kept.
        body: The response body.

    Raises:
        StateBackendUnavailableError: When the state store cannot be reached.
    """
    record = {
        "fingerprint": claim.fingerprint,
        "status": status_code,
        "headers": [[name.lower(), value] for name, value in headers if name.lower() in STORED_HEADERS],
        "body": base64.b64encode(body).decode(),
    }
    state.set_if_absent(claim.result_key, json.dumps(record).encode(), RESULT_TTL_SECONDS)
    release(state, claim)


@core_openapi_contract.replays_responses
async def idempotent(request: Request, key: IdempotencyKey, state: core_dependencies.PlatformState) -> None:
    """Claim the request's key, or replay what an earlier request with it recorded.

    List it after the route's authentication, which resolves the caller it scopes the key to. A request without a key
    returns at once and touches nothing.

    Args:
        request: The request, whose body is read for the fingerprint.
        key: The parsed key, if the client sent one.
        state: The platform state provider.

    Raises:
        IdempotentReplayError: When the request repeats one that is answered.
        IdempotencyKeyReusedError: When the key belongs to another request (422).
        IdempotencyInFlightError: When the same request is still running (409).
        StateUnavailableError: When the state store cannot be reached (503).
        RuntimeError: When the route did not authenticate the caller before this dependency.
    """
    if key is None:
        return
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise RuntimeError("An idempotent route must authenticate the caller before it declares Idempotent")
    fingerprint = request_fingerprint(request.method, request.url.path, request.url.query, await request.body())
    try:
        outcome = await run_in_threadpool(begin, state, principal.user_id, key, fingerprint)
    except StateBackendUnavailableError as err:
        core_attempt_state.raise_unavailable("idempotency claim", err)
    if isinstance(outcome, StoredResult):
        raise core_exceptions.IdempotentReplayError(outcome.status_code, outcome.headers, outcome.body)
    setattr(request.state, CLAIM_STATE_KEY, outcome)


#: The opt-in of a create route: ``dependencies=[Security(...), core_idempotency.Idempotent]``.
Idempotent = Depends(idempotent)


class _ResponseHold:
    """Holds back the response of one request that won a claim, until its outcome is known.

    Attributes:
        _send: The ASGI send callable of the layer above.
        _request_state: The request's state dict, where the dependency leaves the claim.
        _held: The response messages not sent yet.
        _status: The status of the response start.
        _size: The body bytes seen so far.
        _settled: Whether the claim is stored or freed and the rest of the response goes straight through.
    """

    def __init__(self, send: Send, request_state: dict[str, Any]) -> None:
        """Start with nothing held.

        Args:
            send: The ASGI send callable to forward to.
            request_state: The request's state dict.
        """
        self._send = send
        self._request_state = request_state
        self._held: list[Message] = []
        self._status = 0
        self._size = 0
        self._settled = False

    @property
    def _claim(self) -> Claim | None:
        return self._request_state.get(CLAIM_STATE_KEY)

    async def _free(self, claim: Claim) -> None:
        """Free the claim; if the store is unreachable it expires on its own."""
        self._settled = True
        try:
            await run_in_threadpool(release, core_dependencies.get_platform_state(), claim)
        except StateBackendUnavailableError:
            logger.warning("Could not free an idempotency claim; it expires on its own")

    async def _flush(self) -> None:
        held, self._held = self._held, []
        for message in held:
            await self._send(message)

    async def _store(self, claim: Claim) -> None:
        """Record the held response, or free the claim when the store cannot be written."""
        headers = [(name.decode("latin-1"), value.decode("latin-1")) for name, value in self._held[0]["headers"]]
        body = b"".join(message.get("body", b"") for message in self._held[1:])
        self._settled = True
        try:
            await run_in_threadpool(
                complete, core_dependencies.get_platform_state(), claim, self._status, headers, body
            )
        except StateBackendUnavailableError:
            logger.error("Could not store the result of an idempotent request; a retry may repeat it")
            await self._free(claim)

    async def send(self, message: Message) -> None:
        """Forward a response message, or hold it until the response is complete.

        Args:
            message: The ASGI response message.
        """
        claim = self._claim
        if claim is None or self._settled:
            await self._send(message)
            return
        if message["type"] == "http.response.start":
            self._status = message["status"]
            if not 200 <= self._status < 300:
                await self._free(claim)
                await self._send(message)
                return
            self._held.append(message)
            return
        self._size += len(message.get("body", b""))
        self._held.append(message)
        if self._size > MAX_STORED_BODY:
            await self._free(claim)
            await self._flush()
        elif not message.get("more_body", False):
            await self._store(claim)
            await self._flush()

    async def abandon(self, *, failed: bool) -> None:
        """Free the claim of a request that ended without a settled response.

        Args:
            failed: Whether the application raised; the response it held back is then dropped, so the error handlers
                above can answer, and otherwise it is sent.
        """
        claim = self._claim
        if claim is not None and not self._settled:
            await self._free(claim)
        if failed:
            self._held.clear()
        else:
            await self._flush()


class IdempotencyMiddleware:
    """Store the outcome of a request that won an idempotency claim.

    It reads the claim :func:`idempotent` left on the request's state, so a request without one (every other route,
    streamed and file responses included) is forwarded untouched. A request with one has its response held back: a
    final ``2xx`` within :data:`MAX_STORED_BODY` is stored before the last chunk goes out, and any other outcome (a
    refusal, an exception, a body over the cap) frees the claim and sends the response on.

    Install it just outside the innermost middleware, so it sees the response as the route made it, and inside the
    layers that refuse a request before the route runs (they never leave a claim).

    Attributes:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped application.

        Args:
            app: The ASGI application to wrap.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the wrapped application, storing the response of a request that holds a claim.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Set before anything copies the scope, so every layer below shares the dict the dependency writes to.
        hold = _ResponseHold(send, scope.setdefault("state", {}))
        try:
            await self.app(scope, receive, hold.send)
        except BaseException:
            await hold.abandon(failed=True)
            raise
        await hold.abandon(failed=False)
