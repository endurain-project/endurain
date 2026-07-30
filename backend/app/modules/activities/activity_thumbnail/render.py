"""Render activity map thumbnails.

Renders a static WebP map image (OpenStreetMap tiles + a polyline of the
activity route) as raw bytes, and nothing else: persisting the bytes goes through
the platform ``StorageProvider`` in ``service.py``, and addressing them (storage
key, signed URL) lives in ``signing.py``. Keeping this module purely
bytes-in/bytes-out means the read path never has to import the rendering stack.
"""

import re

import core.config as core_config
import core.logger as core_logger
import infra.runtime as platform_runtime
from infra.providers import RouteMapRenderRequest

logger = core_logger.get_logger(__name__)

# Thumbnail geometry and encoding. Kept at 1200x400 so the map stays crisp in
# the large desktop feed/detail cards; WebP at quality 75 keeps the file far
# smaller than the previous 1200x400 PNG.
THUMBNAIL_WIDTH = 1200
THUMBNAIL_HEIGHT = 400
THUMBNAIL_CONTENT_TYPE = "image/webp"
_THUMBNAIL_QUALITY = 75
# WebP encoder effort (0-6). 6 searches hardest for the smallest file at a given
# quality — identical visual result, fewer bytes; the extra CPU is negligible for
# a one-time background render.
_THUMBNAIL_METHOD = 6

# Fallback tile URL used when server settings are unavailable.
# Uses a fixed subdomain; staticmap does not support {s} rotation.
_DEFAULT_TILE_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
_DEFAULT_BG_COLOR = "#dddddd"

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
    # Replace {s} with a fixed subdomain
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


def render_activity_thumbnail(
    activity_id: int,
    waypoints: list[dict],
    *,
    tile_url: str = _DEFAULT_TILE_URL,
    background_color: str = _DEFAULT_BG_COLOR,
    api_key: str | None = None,
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
        api_key: Optional tile provider API key. When provided,
            sent as 'Authorization: Stadia-Auth <key>' HTTP header
            (compatible with Stadia Maps and similar providers).
        width: Thumbnail width in pixels.
        height: Thumbnail height in pixels.

    Returns:
        WebP-encoded bytes, or None if generation was skipped or
        failed.

    Raises:
        None — errors are logged and None is returned.
    """
    if not waypoints or len(waypoints) < 2:
        logger.debug(
            "Skipping thumbnail render: fewer than 2 waypoints",
            extra=core_logger.context(console=True, activity_id=activity_id, waypoint_count=len(waypoints or [])),
        )
        return None

    try:
        # staticmap expects (longitude, latitude) order
        coords = [(float(wp["lon"]), float(wp["lat"])) for wp in waypoints]

        normalised_url = _normalise_tile_url(tile_url)

        # Build request headers; inject Authorization when an API
        # key is present (e.g. Stadia Maps requires backend auth).
        headers: dict[str, str] = {
            "User-Agent": f"Endurain {core_config.API_VERSION} - StaticMap backend thumbnail generator"
        }
        if not api_key and "stadiamaps.com" in normalised_url:
            logger.warning(
                "Skipping thumbnail render: Stadia Maps tile URL requires an API key",
                extra=core_logger.context(console=True, activity_id=activity_id),
            )
            return None
        if api_key and "stadiamaps.com" in normalised_url:
            headers["Authorization"] = f"Stadia-Auth {api_key}"
        elif api_key:
            separator = "&" if "?" in normalised_url else "?"
            normalised_url += f"{separator}api_key={api_key}"

        data = platform_runtime.get_active_platform().route_map_renderer.render(
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

        logger.info(
            "Thumbnail rendered",
            extra=core_logger.context(console=True, activity_id=activity_id, width=width, height=height),
        )

        return data

    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        logger.warning(
            "Thumbnail generation failed",
            exc_info=exc,
            extra=core_logger.context(console=True, activity_id=activity_id),
        )
        return None
