"""Map tile server policy: which tile URLs are safe, which domains the CSP allows and the presets."""

import ipaddress
from urllib.parse import urlparse

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import core.route_map as core_route_map
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.schema as server_settings_schema

logger = core_logger.get_logger(__name__)


def reject_unsafe_tileserver(tile_url: str) -> None:
    """Refuse a tile URL that resolves somewhere the server must not dial.

    The renderer already refuses the request at tile-fetch time, but that is a
    background job: the admin who set the value sees no error, and the bad value
    is persisted meanwhile. Checking here answers the write instead, so a URL
    pointing at cloud metadata or an internal service never reaches the row.

    It lives in the service rather than in the schema validator because the check
    resolves DNS, and the schema is also what deserializes settings on every
    *read* — a validator would put a lookup on the read path of the whole app. The
    lookup is bounded, so an unresponsive resolver cannot hold the request thread.

    Args:
        tile_url: The tile URL template being saved.

    Raises:
        InvalidInputError: When the template cannot be resolved to a URL, or the
            URL is not one the server may dial.
    """
    try:
        # Probe the template the way the renderer will: it drops ``{r}``, pins
        # ``{s}`` and escapes other placeholders before filling ``{z}/{x}/{y}``,
        # so the built-in Stadia templates (``{r}``) must pass here.
        probe_url = core_route_map.normalise_tile_url(tile_url).format(z=0, x=0, y=0)
    except (IndexError, KeyError, ValueError) as err:
        raise core_exceptions.InvalidInputError(
            "Tile server URL contains a placeholder the renderer cannot fill"
        ) from err

    reason = core_network.url_rejection_reason_bounded(probe_url, purpose="activity_thumbnail_tile")
    if reason is None:
        return
    logger.warning(
        "Refused a tile server URL that targets a non-public address",
        extra=core_logger.context(reason=reason),
    )
    raise core_exceptions.InvalidInputError(f"Tile server {reason}")


def decrypt_tileserver_api_key(encrypted_api_key: str | None) -> str | None:
    """Decrypt a stored tile API key.

    Args:
        encrypted_api_key: The stored (encrypted) key, or None / empty when unset.

    Returns:
        The plain-text key, or None when no key is set.

    Raises:
        ServiceUnavailableError: When the stored key cannot be decrypted, for example
            after the encryption key changed.
    """
    return server_settings_change_utils.decrypt_secret(encrypted_api_key, server_settings_constants.API_KEY_LABEL)


def get_tile_maps_templates() -> list[server_settings_schema.TileMapsTemplate]:
    """Return the built-in tile map templates an admin can pick from.

    Returns:
        One template per built-in tile provider.
    """
    return [
        server_settings_schema.TileMapsTemplate(template_id=template_id, **template_data)
        for template_id, template_data in server_settings_constants.TILE_MAPS_TEMPLATES.items()
    ]


def extract_domain_from_tile_url(url: str) -> str | None:
    """Derive the CSP ``img-src`` source for a custom tile server URL.

    The source is the tile host itself, never a registrable-domain wildcard: without
    a public-suffix list, ``tiles.example.co.uk`` would widen to ``*.co.uk``. Only the
    ``{s}`` subdomain placeholder, which stands for a set of sibling hosts, widens
    the source, and then only to that host's own subdomains.

    Args:
        url: Tile server URL template (e.g., https://tiles.example.com/map/{z}/{x}/{y}.png).

    Returns:
        ``scheme://host[:port]``, with ``*.`` standing in for the ``{s}`` label; or None
        if the URL is invalid. For example ``https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png``
        gives ``https://*.tile.openstreetmap.org`` and ``https://tiles.example.com/{z}/{x}/{y}.png``
        gives ``https://tiles.example.com``.
    """
    has_subdomain_placeholder = "{s}" in url.lower()
    try:
        parsed = urlparse(url.replace("{s}", "a").replace("{S}", "a"))
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not hostname:
        return None

    try:
        is_ip = ipaddress.ip_address(hostname) is not None
    except ValueError:
        is_ip = False

    if is_ip:
        host = f"[{hostname}]" if ":" in hostname else hostname
    elif has_subdomain_placeholder and "." in hostname:
        host = f"*.{hostname.split('.', 1)[1]}"
    else:
        host = hostname
    return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")


def _is_covered_by(source: str, allowed_sources: list[str]) -> bool:
    """Return whether a CSP source is already allowed, exactly or by a ``*.`` wildcard.

    Args:
        source: A ``scheme://host[:port]`` source.
        allowed_sources: The sources already allowed.

    Returns:
        True when an allowed source with the same scheme matches the host.
    """
    scheme, _, host = source.partition("://")
    for allowed in allowed_sources:
        allowed_scheme, _, allowed_host = allowed.partition("://")
        if allowed_scheme != scheme:
            continue
        if allowed_host == host or (allowed_host.startswith("*.") and host.endswith(allowed_host[1:])):
            return True
    return False


def allowed_tile_domains_for_url(tile_url: str) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows for a tile URL.

    Args:
        tile_url: The configured tile server URL template.

    Returns:
        The built-in provider domains plus the tile URL's own domain.
    """
    allowed_domains: list[str] = server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS.copy()
    custom_domain = extract_domain_from_tile_url(tile_url)
    if custom_domain and not _is_covered_by(custom_domain, allowed_domains):
        allowed_domains.append(custom_domain)
    return allowed_domains
