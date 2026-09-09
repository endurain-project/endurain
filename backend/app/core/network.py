"""Network helpers shared across the application.

Currently provides proxy-aware client IP extraction
and SSRF guards for outbound HTTP calls. Lives in
``core/`` so any module — including other ``core/``
modules such as rate limiting — can use it without
creating a dependency on the ``users`` package.
"""

import asyncio
import ipaddress
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

import core.config as core_config
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_TRUSTED_PROXY_HOSTNAME_REFRESH_SECONDS = 60.0
_trusted_proxy_hostname_refresh_lock = threading.Lock()
_trusted_proxy_hostname_last_refresh = float("-inf")

# Keep slow OS resolver calls away from asyncio's shared executor. A running
# getaddrinfo call cannot be cancelled, but this cap prevents unresolved OIDC
# hosts from consuming every worker used by unrelated to_thread operations.
_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS = 5.0
_SSRF_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ssrf-dns")

# RFC 1123 hostname syntax: labels of 1-63 alphanumeric/hyphen
# characters, separated by dots. Hyphens may not start or end
# a label. Total length is capped at 253 characters.
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)"  # first label
    r"(?:\.(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?))*$",  # more
    re.IGNORECASE,
)


def _looks_like_ip(value: str) -> bool:
    """Best-effort check that ``value`` is an IP literal.

    Used by startup/config validation helpers to decide
    whether an entry is an IP literal or a hostname.

    Args:
        value: Candidate IP literal or hostname.

    Returns:
        True when ``value`` is an IPv4/IPv6 literal.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_valid_hostname(value: str) -> bool:
    """Return True when value is a syntactically valid hostname.

    Validates RFC 1123 hostname syntax. Rejects values that
    contain URL schemes, ports, or other non-hostname characters
    (e.g., ``caddy:8080`` or ``http://caddy``).

    Args:
        value: Candidate hostname to validate.

    Returns:
        True when value conforms to RFC 1123 hostname syntax.
    """
    return len(value) <= 253 and _HOSTNAME_RE.match(value) is not None


def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to a list of IP addresses.

    Called when refreshing TRUSTED_PROXIES hostnames to their
    IP addresses. Uses socket.getaddrinfo() to resolve both
    IPv4 and IPv6 addresses.

    Args:
        hostname: The hostname to resolve (e.g., 'proxy.internal').

    Returns:
        List of resolved IP addresses (e.g., ['10.0.0.5', '10.0.0.6']).
        Returns an empty list if resolution fails (a warning is logged).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = [str(info[4][0]) for info in infos]
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_ips = []
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                unique_ips.append(ip)
        return unique_ips
    except socket.gaierror as err:
        logger.warning(
            f"Failed to resolve TRUSTED_PROXIES hostname '{hostname}': {err}", extra=core_logger.context(console=True)
        )
        return []


def _trusted_proxy_hostname_entries() -> list[str]:
    """Return configured TRUSTED_PROXIES hostnames.

    Returns:
        Hostname entries that need DNS resolution.
    """
    hostnames: list[str] = []
    for configured_entry in core_config.settings.TRUSTED_PROXIES:
        entry = configured_entry.strip()
        if not entry:
            continue
        if entry == "*" or "/" in entry or _looks_like_ip(entry):
            continue
        hostnames.append(entry)
    return hostnames


def _trusted_proxy_hostname_cache_is_fresh(now: float) -> bool:
    """Check whether trusted proxy hostname cache is fresh.

    Args:
        now: Current monotonic timestamp.

    Returns:
        True when the refresh throttle window has not elapsed.
    """
    cache_age = now - _trusted_proxy_hostname_last_refresh
    return cache_age < _TRUSTED_PROXY_HOSTNAME_REFRESH_SECONDS


def refresh_trusted_proxy_hostnames(
    *,
    force: bool = False,
    log_success: bool = False,
) -> dict[str, list[str]]:
    """Refresh TRUSTED_PROXIES hostname resolutions.

    Args:
        force: Refresh even when the cache is still fresh.
        log_success: Log successful hostname resolutions.

    Returns:
        Mapping of hostnames to resolved IP addresses.
    """
    global _trusted_proxy_hostname_last_refresh

    hostnames = _trusted_proxy_hostname_entries()
    if not hostnames:
        core_config.settings._resolved_trusted_proxy_ips = set()
        return {}

    now = time.monotonic()
    if not force and _trusted_proxy_hostname_cache_is_fresh(now):
        return {}

    with _trusted_proxy_hostname_refresh_lock:
        now = time.monotonic()
        if not force and _trusted_proxy_hostname_cache_is_fresh(now):
            return {}

        resolved_map: dict[str, list[str]] = {}
        all_resolved_ips: set[str] = set()
        for hostname in hostnames:
            ips = _resolve_hostname(hostname)
            if not ips:
                continue

            resolved_map[hostname] = ips
            all_resolved_ips.update(ips)
            if log_success:
                logger.info(
                    f"Resolved TRUSTED_PROXIES hostname '{hostname}' to {ips}", extra=core_logger.context(console=True)
                )

        core_config.settings._resolved_trusted_proxy_ips = all_resolved_ips
        _trusted_proxy_hostname_last_refresh = now

    return resolved_map


def _is_trusted_peer(peer_ip: str) -> bool:
    """Check whether ``peer_ip`` is in the TRUSTED_PROXIES allow-list.

    Supports exact IPs and CIDR notation. The special value ``"*"``
    (the default) trusts every peer. Also supports resolved hostnames
    (cached from startup resolution).

    Args:
        peer_ip: The direct TCP-connection IP of the caller.

    Returns:
        True if the peer is trusted, False otherwise.
    """
    trusted = core_config.settings.TRUSTED_PROXIES
    if trusted == ["*"]:
        return True
    try:
        addr = ipaddress.ip_address(peer_ip)
        for entry in trusted:
            entry = entry.strip()
            if not entry:
                continue
            try:
                network = ipaddress.ip_network(entry, strict=False)
                if addr in network:
                    return True
            except ValueError:
                # Entry is not a valid network — compare as plain string
                if peer_ip == entry:
                    return True
    except ValueError:
        pass

    hostnames = _trusted_proxy_hostname_entries()
    if not hostnames:
        return False

    resolved_ips = core_config.settings._resolved_trusted_proxy_ips
    return peer_ip in resolved_ips


def get_ip_address(request: Request) -> str:
    """
    Extract client IP address from request, respecting TRUSTED_PROXIES.

    Proxy headers (``X-Forwarded-For``, ``X-Real-IP``) are only trusted
    when the direct TCP peer matches an entry in ``TRUSTED_PROXIES``.
    This prevents attackers from spoofing their IP by injecting those
    headers on direct connections.

    When ``TRUSTED_PROXIES`` is ``["*"]`` (the default) all peers are
    trusted.

    Args:
        request: Request object with headers and client info.

    Returns:
        Client IP address or "unknown" if indeterminate.
    """
    peer_ip = request.client.host if request.client else None

    if peer_ip and _is_trusted_peer(peer_ip):
        # Peer is a trusted proxy — honour the forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the leftmost IP: the original client
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    # Untrusted peer or no peer info — use the raw socket IP
    return peer_ip or "unknown"


# Schemes the application is willing to dial. Anything
# else (file://, gopher://, ftp://, data://, javascript:)
# is rejected outright.
_ALLOWED_OUTBOUND_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _is_private_or_reserved(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if ``addr`` belongs to any non-routable range.

    Combines every "do not dial" predicate Python's
    ``ipaddress`` module exposes: private (RFC1918,
    fc00::/7), loopback, link-local, multicast,
    unspecified (0.0.0.0, ::), and reserved blocks. Any
    of these would let an attacker pivot to internal
    infrastructure or cloud metadata services.
    """
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_reserved
    )


def _load_ssrf_allowlist() -> tuple[
    frozenset[str],
    tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
]:
    """Split the configured allowlist into hostnames and IP networks.

    Entries have already been validated by the
    ``SSRF_ALLOWED_HOSTS`` field validator in
    :mod:`core.config`. This helper just classifies them
    for the lookup below.
    """
    hosts: set[str] = set()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in core_config.settings.SSRF_ALLOWED_HOSTS:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            hosts.add(entry.lower())
    return frozenset(hosts), tuple(networks)


def _is_ssrf_allowlisted(
    hostname: str,
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if ``hostname`` or ``addr`` is allowlisted.

    The allowlist is only consulted when the resolved
    address would otherwise be rejected by
    :func:`_is_private_or_reserved`. Both the hostname
    (exact, case-insensitive) and the resolved IP (CIDR
    membership) are checked so administrators can opt
    in by either dimension.
    """
    hosts, networks = _load_ssrf_allowlist()
    if hostname.lower() in hosts:
        return True
    return any(addr in network for network in networks)


# Reasons a destination is refused. Phrased to read correctly after either
# ``"URL "`` (reject_private_url) or a host value (host_rejection_reason), so the
# two entry points share one set of checks and one vocabulary.
_UNRESOLVABLE = "hostname could not be resolved"
_UNPARSEABLE = "resolves to an unparseable address"
_NON_PUBLIC = "resolves to a non-public address"
_NOT_AN_AUTHORITY = "is not a bare host[:port] authority"


def _resolve_checked_addresses(
    hostname: str,
    *,
    purpose: str | None = None,
) -> tuple[tuple[str, ...], str | None]:
    """Resolve a hostname and return its validated addresses or rejection reason.

    Resolves every A/AAAA record and requires all of them to be public unicast.
    A single private/loopback/link-local answer rejects the host — this defends
    against DNS rebinding, where an attacker-controlled name returns a public IP
    on the first lookup and a private IP on the next.

    An address that would otherwise be rejected is permitted when it (or its
    hostname) is covered by ``SSRF_ALLOWED_HOSTS``; every such hit is logged so
    operators can review what the exception is being used for.

    Args:
        hostname: The hostname to resolve, without a port.
        purpose: Optional short tag identifying the outbound call, used only for
            audit logging.

    Returns:
        Validated addresses and ``None``, or no addresses and a reason string.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return (), _UNRESOLVABLE

    addresses: list[str] = []
    for info in infos:
        ip_text = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_text)
        except ValueError:
            # Defensive: if the resolver hands back something we
            # can't parse, treat it as unsafe.
            return (), _UNPARSEABLE
        if _is_private_or_reserved(addr):
            if _is_ssrf_allowlisted(hostname, addr):
                # Audit trail: every allowlisted private destination is logged
                # so operators can review what the SSRF exception is used for.
                logger.info(
                    f"SSRF allowlist hit: dialing private address {ip_text} for host "
                    f"{hostname} (purpose={purpose or 'unspecified'})"
                )
            else:
                return (), _NON_PUBLIC
        normalized_address = str(addr)
        if normalized_address not in addresses:
            addresses.append(normalized_address)
    if not addresses:
        return (), _UNRESOLVABLE
    return tuple(addresses), None


def _address_rejection_reason(hostname: str, *, purpose: str | None = None) -> str | None:
    """Return why ``hostname`` must not be dialed, or None when every address is safe."""
    _, reason = _resolve_checked_addresses(hostname, purpose=purpose)
    return reason


def host_rejection_reason(host: str | None, *, purpose: str | None = None) -> str | None:
    """Return why an operator-configured ``host[:port]`` must not be dialed, or None.

    The host-authority counterpart to :func:`reject_private_url`, for callers
    handed a bare authority from configuration rather than a full URL, and which
    must *degrade* (disable the feature) rather than fail a request — so this
    returns a reason instead of raising.

    It adds one check the URL form does not need: the configured value must be a
    plain ``host[:port]``. A value carrying a scheme, path, or credentials would
    otherwise be interpolated into a URL by the caller and silently redirect the
    request elsewhere — ``"evil.example.com/x"`` becomes
    ``"https://evil.example.com/x/reverse"``, whose hostname check passes.

    Args:
        host: The configured host authority, or ``None``.
        purpose: Optional short tag identifying the outbound call, used only for
            audit logging.

    Returns:
        A short human-readable reason, or ``None`` when the host may be dialed.
    """
    if host is None:
        return _NOT_AN_AUTHORITY

    hostname, separator, port = host.rpartition(":")
    if not separator:
        hostname = host
    elif not (port.isdigit() and len(port) <= 5):
        return _NOT_AN_AUTHORITY

    if not _is_valid_hostname(hostname):
        return _NOT_AN_AUTHORITY

    return _address_rejection_reason(hostname, purpose=purpose)


def resolve_url_addresses(
    url: str,
    *,
    purpose: str | None = None,
) -> tuple[tuple[str, ...], str | None]:
    """Resolve an outbound URL to validated addresses or a rejection reason.

    Args:
        url: Fully-qualified outbound URL.
        purpose: Optional audit tag for allowlisted private destinations.

    Returns:
        Validated addresses and ``None``, or no addresses and a safe reason.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return (), "Malformed URL"

    if parsed.scheme.lower() not in _ALLOWED_OUTBOUND_SCHEMES:
        return (), "URL scheme is not permitted"

    hostname = parsed.hostname
    if not hostname:
        return (), "URL has no hostname"

    addresses, reason = _resolve_checked_addresses(hostname, purpose=purpose)
    return addresses, f"URL {reason}" if reason is not None else None


def url_rejection_reason(url: str, *, purpose: str | None = None) -> str | None:
    """Return why an outbound URL must not be dialed, or ``None``.

    Args:
        url: Fully-qualified outbound URL.
        purpose: Optional audit tag for allowlisted private destinations.

    Returns:
        A safe client-facing reason, or ``None`` when the URL may be dialed.
    """
    _, reason = resolve_url_addresses(url, purpose=purpose)
    return reason


def reject_private_url(url: str, *, purpose: str | None = None) -> None:
    """Refuse to dial URLs that resolve to private/internal hosts.

    Mitigates Server-Side Request Forgery (SSRF) by
    enforcing two checks before any outbound HTTP call:

    1. The scheme must be ``http`` or ``https``.
    2. Every address the hostname resolves to (both A
       and AAAA records) must be a public unicast
       address. A single private/loopback/link-local
       answer aborts the request — this defends against
       DNS rebinding where an attacker-controlled host
       returns a public IP on the first lookup and a
       private IP on the next.

    Note: this is a *time-of-check* guard. Callers that
    want full TOCTOU safety should also pin the resolved
    public IP and dial it directly with the original
    Host header. For our current use cases (admin-set
    OIDC discovery / JWKS endpoints) the time-of-check
    guard is sufficient hardening.

    Args:
        url: The fully-qualified URL the caller intends
            to fetch.
        purpose: Optional short tag identifying the
            outbound call (e.g. ``"oidc_discovery"``).
            Used only for audit logging when a private
            destination is allowed via
            ``SSRF_ALLOWED_HOSTS``; never trusted as a
            security boundary.

    Raises:
        HTTPException: 400 if the URL is malformed,
            uses a forbidden scheme, has no hostname,
            or resolves to any non-public address that
            is not covered by the
            ``SSRF_ALLOWED_HOSTS`` allowlist.
    """
    reason = url_rejection_reason(url, purpose=purpose)
    if reason is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )


async def reject_private_url_async(url: str, *, purpose: str | None = None) -> None:
    """Await :func:`reject_private_url` without blocking the event loop.

    The guard resolves every A/AAAA record with :func:`socket.getaddrinfo`, which
    is blocking and cannot be cancelled once started. Async callers run it in a
    small dedicated executor so stalled DNS calls cannot exhaust asyncio's shared
    worker pool, and stop awaiting it after a bounded interval. Synchronous
    callers (scheduled jobs, subscribers) call :func:`reject_private_url`
    directly.

    Args:
        url: The fully-qualified URL the caller intends to fetch.
        purpose: Optional short tag identifying the outbound call, used only for
            audit logging.

    Raises:
        HTTPException: 400, for the reasons listed on :func:`reject_private_url`.
        HTTPException: 504 when hostname resolution exceeds the allowed time.
    """
    loop = asyncio.get_running_loop()
    operation = partial(reject_private_url, url, purpose=purpose)
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_SSRF_DNS_EXECUTOR, operation),
            timeout=_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS,
        )
    except TimeoutError as err:
        logger.warning(
            "SSRF hostname resolution timed out",
            extra=core_logger.context(purpose=purpose or "unspecified"),
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Hostname resolution timed out",
        ) from err
