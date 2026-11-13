"""Shared validation dependencies for FastAPI routers."""

import uuid
from typing import Annotated

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from fastapi import Depends, Header, Path
from sqlalchemy.orm import Session

import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions

#: A path-parameter id that is a UUID. FastAPI answers 422 with the validation problem for a malformed value,
#: and OpenAPI shows ``string``/``uuid``.
UuidId = Annotated[uuid.UUID, Path()]

#: The route's database session. Rolled back on an unhandled error and closed by ``get_db`` as soon as the route
#: function returns, before the response is sent, so a slow client or a streamed body never pins a pooled connection.
DbSession = Annotated[Session, Depends(core_database.get_db, scope="function")]


def require_if_match_header(if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None) -> str:
    """
    Return the request's ``If-Match`` precondition, which a write to a versioned resource must carry.

    Args:
        if_match: The ``If-Match`` header, if the client sent one.

    Returns:
        The raw header value.

    Raises:
        PreconditionRequiredError: When the header is absent (428).
        InvalidInputError: When the header is the wildcard ``*``, which would match any version
            and so defeat the stale-write check; only in-process callers may pass it to a service.
    """
    if if_match is None:
        raise core_exceptions.PreconditionRequiredError()
    if core_etag.WILDCARD in core_etag.parse_if_match(if_match):
        raise core_exceptions.InvalidInputError("If-Match must name the ETag you read, not the wildcard")
    return if_match


#: The ``If-Match`` precondition of a write to a versioned resource; its absence is refused with 428.
IfMatch = Annotated[str, Depends(require_if_match_header)]


def get_storage() -> platform_providers.StorageProvider:
    """
    Return the active platform's blob-storage provider.

    Routers declare it with ``Depends`` so the provider reaches services as an
    argument and a test can override it without patching the runtime.

    Returns:
        The storage provider.
    """
    return platform_runtime.get_active_platform().storage


#: The active platform's blob-storage provider, injected into a route or dependency.
Storage = Annotated[platform_providers.StorageProvider, Depends(get_storage)]


def get_platform_state() -> platform_providers.StateProvider:
    """
    Return the active platform's ephemeral-state provider.

    Routers declare it with ``Depends`` so the provider reaches services and stores as
    an argument and a test can override it without patching the runtime.

    Returns:
        The state provider.
    """
    return platform_runtime.get_state()


#: The active platform's ephemeral-state provider, injected into a route or dependency.
PlatformState = Annotated[platform_providers.StateProvider, Depends(get_platform_state)]


def get_platform_clock() -> platform_providers.ClockProvider:
    """
    Return the active platform's clock.

    Returns:
        The clock provider.
    """
    return platform_runtime.get_active_platform().clock


#: The active platform's clock, injected into a route or dependency.
PlatformClock = Annotated[platform_providers.ClockProvider, Depends(get_platform_clock)]


def get_mail() -> platform_providers.MailProvider:
    """
    Return the active platform's outbound-mail provider.

    Routers declare it with ``Depends`` so the provider reaches services as an
    argument and a test can override it without patching the runtime.

    Returns:
        The mail provider.
    """
    return platform_runtime.get_active_platform().mail


#: The active platform's outbound-mail provider, injected into a route or dependency.
Mail = Annotated[platform_providers.MailProvider, Depends(get_mail)]
