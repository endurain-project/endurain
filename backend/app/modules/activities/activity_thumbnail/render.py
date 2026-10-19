"""Render activity map thumbnails.

Renders a static WebP map image (OpenStreetMap tiles + a polyline of the
activity route) as raw bytes, and nothing else: persisting the bytes goes through
the platform ``StorageProvider`` in ``service.py``, and addressing them (storage
key, signed URL) lives in ``signing.py``. Keeping this module purely
bytes-in/bytes-out means the read path never has to import the rendering stack.
"""

import re
from urllib.parse import urlparse

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.route_map as core_route_map
from core.route_map import RouteMapRenderRequest

logger = core_logger.get_logger(__name__)

# Thumbnail geometry and encoding. 1200x400 keeps the map crisp in the large
# desktop feed/detail cards; WebP at quality 75 keeps the file small.
THUMBNAIL_WIDTH = 1200
THUMBNAIL_HEIGHT = 400
THUMBNAIL_CONTENT_TYPE = "image/webp"
_THUMBNAIL_QUALITY = 75
# WebP encoder effort (0-6). 6 searches hardest for the smallest file at a given
# quality — identical visual result, fewer bytes; the extra CPU is negligible for
# a one-time background render.
_THUMBNAIL_METHOD = 6

# Fallback tile URL used when server settings are unavailable.
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_BG_COLOR = "#dddddd"

# Visual constants mirroring the frontend Leaflet map (design tokens):
# track = --color-brand, start marker = --color-goal, finish marker = --color-hr.
# staticmap's CircleMarker has no stroke, so the white "border" the frontend gets
# from Leaflet is drawn as a larger white circle behind the coloured dot.
_LINE_COLOR = "#1d9e75"  # --color-brand (brand teal)
_LINE_WIDTH = 4
_MARKER_OUTER_COLOR = "#ffffff"
_MARKER_OUTER_RADIUS = 20
_START_COLOR = "#639922"  # --color-goal (green)
_END_COLOR = "#e24b4a"  # --color-hr (red)
_MARKER_INNER_RADIUS = 13


def _is_stadia_url(url: str) -> bool:
    """Return whether a tile URL points at Stadia Maps.

    Compared on the parsed host, not as a substring: a URL that merely contains
    ``stadiamaps.com`` in its path or query, or on a look-alike host such as
    ``notstadiamaps.com``, must not get the Stadia authorization scheme.

    Args:
        url: The tile URL template.

    Returns:
        ``True`` when the host is ``stadiamaps.com`` or one of its subdomains.
    """
    host = (urlparse(url).hostname or "").lower()
    return host == "stadiamaps.com" or host.endswith(".stadiamaps.com")


def _normalise_tile_url(url: str) -> str:
    """Convert a Leaflet tile URL template to staticmap format.

    staticmap uses Python's str.format() with only {z}, {x}, {y}
    substitutions. Any other placeholders (e.g. {s} for subdomains,
    {r} for retina tiles) cause a KeyError at render time.

    This function:
    - Replaces {s} with the literal subdomain 'a'
    - Removes {r} (retina suffix — not needed for thumbnails)
    - Escapes any remaining unknown placeholders so they are
      passed through as literal strings.

    Args:
        url: Leaflet-style tile URL template.

    Returns:
        Tile URL safe for use with staticmap.
    """
    # The OSM default no longer uses {s}, but custom providers and older
    # stored URLs may; staticmap can't rotate subdomains, so pin it to 'a'.
    url = re.sub(r"\{s\}", "a", url)
    # Remove {r} retina placeholder (e.g. Stadia Maps)
    url = re.sub(r"\{r\}", "", url)
    # Escape any remaining unknown {placeholders} that are not
    # the three staticmap knows about ({z}, {x}, {y})
    url = re.sub(
        r"\{(?!z\}|x\}|y\})([^}]+)\}",
        lambda m: "{{" + m.group(1) + "}}",
        url,
    )
    return url


DEFAULT_USER_AGENT = "Endurain - StaticMap backend thumbnail generator"


def render_activity_thumbnail(
    activity_id: int,
    waypoints: list[dict],
    *,
    tile_url: str = DEFAULT_TILE_URL,
    background_color: str = DEFAULT_BG_COLOR,
    api_key: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    width: int = THUMBNAIL_WIDTH,
    height: int = THUMBNAIL_HEIGHT,
) -> bytes | None:
    """Render an activity map thumbnail as WebP bytes.

    Renders map tiles with the activity polyline and start/end
    markers overlaid, matching the Leaflet map appearance used
    on the activity detail page.

    Args:
        activity_id: The activity ID (used only for logging).
        waypoints: List of dicts with 'lat' and 'lon' keys.
        tile_url: Leaflet-style tile URL template. {s} subdomains
            are normalised to 'a' automatically.
        background_color: Hex background color for the map canvas.
        api_key: Optional tile provider API key. Stadia receives it through its
            authorization header; other providers receive it as an HTTPS query
            parameter.
        user_agent: ``User-Agent`` sent with tile requests; the caller supplies the
            app version.
        width: Thumbnail width in pixels.
        height: Thumbnail height in pixels.

    Returns:
        WebP-encoded bytes, or None when generation was deliberately skipped
        (too few waypoints, a tile provider that needs a key).

    Raises:
        ProcessingError: When rendering was attempted and failed (tile server
            unreachable, malformed waypoints). Distinct from a skip so a durable
            job is retried instead of recorded as done.
    """
    if not waypoints or len(waypoints) < 2:
        logger.debug(
            "Skipping thumbnail render: fewer than 2 waypoints",
            extra=core_logger.context(activity_id=activity_id, waypoint_count=len(waypoints or [])),
        )
        return None

    try:
        # staticmap expects (longitude, latitude) order
        coords = [(float(wp["lon"]), float(wp["lat"])) for wp in waypoints]

        normalised_url = _normalise_tile_url(tile_url)

        # Build request headers; inject Authorization when an API
        # key is present (e.g. Stadia Maps requires backend auth).
        headers: dict[str, str] = {"User-Agent": user_agent}
        if not api_key and _is_stadia_url(normalised_url):
            logger.warning(
                "Skipping thumbnail render: Stadia Maps tile URL requires an API key",
                extra=core_logger.context(activity_id=activity_id),
            )
            return None
        if api_key and _is_stadia_url(normalised_url):
            headers["Authorization"] = f"Stadia-Auth {api_key}"
        elif api_key:
            if urlparse(normalised_url).scheme.lower() != "https":
                logger.warning(
                    "Skipping thumbnail render: a tile API key requires HTTPS",
                    extra=core_logger.context(activity_id=activity_id),
                )
                return None
            separator = "&" if "?" in normalised_url else "?"
            normalised_url += f"{separator}api_key={api_key}"

        data = core_route_map.render(
            RouteMapRenderRequest(
                coordinates=tuple(coords),
                tile_url=normalised_url,
                background_color=background_color,
                headers=headers,
                width=width,
                height=height,
                line_color=_LINE_COLOR,
                line_width=_LINE_WIDTH,
                marker_outer_color=_MARKER_OUTER_COLOR,
                marker_outer_radius=_MARKER_OUTER_RADIUS,
                start_color=_START_COLOR,
                end_color=_END_COLOR,
                marker_inner_radius=_MARKER_INNER_RADIUS,
                quality=_THUMBNAIL_QUALITY,
                encoder_method=_THUMBNAIL_METHOD,
            )
        )

        return data

    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        # The exception text can carry the tile URL, which includes the API key,
        # so only its type is logged and it is not chained onto the error that
        # callers log with a traceback.
        logger.warning(
            "Thumbnail generation failed",
            extra=core_logger.context(
                activity_id=activity_id,
                error_type=type(exc).__name__,
            ),
        )
        raise core_exceptions.ProcessingError() from None
