"""Render activity map thumbnails and address them in storage.

Renders a static WebP map image (OpenStreetMap tiles + a polyline of the
activity route) as raw bytes. Persisting the bytes, addressing them by storage
key, and turning a key back into a servable URL all go through the platform
``StorageProvider`` (foundations plan §13), so the same code serves local disk
or remote object storage without change.
"""

import re
from io import BytesIO

from staticmap import CircleMarker, Line, StaticMap

import core.config as core_config
import core.logger as core_logger
import core.platform.runtime as platform_runtime

# The storage area (domain-owned namespace) activity thumbnails live under.
THUMBNAIL_STORAGE_AREA = "activity_thumbnails"

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


def thumbnail_key(activity_id: int) -> str:
    """Return the storage key for an activity's thumbnail (e.g. ``42.webp``)."""
    return f"{activity_id}.webp"


def thumbnail_url(key: str | None) -> str | None:
    """Resolve a stored thumbnail *key* to a servable URL.

    Uses the process-wide ``StorageProvider`` so the URL is a same-origin path
    for local disk (``/activity_thumbnails/42.webp``) or a presigned URL for
    object storage. Falls back to the local static path when the platform is not
    initialised (e.g. isolated unit tests).

    Args:
        key: The stored storage key, or ``None``.

    Returns:
        A servable URL, or ``None`` when ``key`` is falsy.
    """
    if not key:
        return None
    try:
        storage = platform_runtime.get_active_platform().storage
    except RuntimeError:
        return f"/{THUMBNAIL_STORAGE_AREA}/{key}"
    return storage.url(THUMBNAIL_STORAGE_AREA, key)


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
        core_logger.print_to_log_and_console(
            f"Activity {activity_id}: skipping thumbnail (fewer than 2 waypoints)",
            "debug",
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
            core_logger.print_to_log_and_console(
                f"Activity {activity_id}: warning — tile URL looks like "
                f"Stadia Maps but no API key provided; API KEY is required "
                "and will skip thumbnail generation",
                "warning",
            )
            return None
        if api_key and "stadiamaps.com" in normalised_url:
            headers["Authorization"] = f"Stadia-Auth {api_key}"
        elif api_key:
            separator = "&" if "?" in normalised_url else "?"
            normalised_url += f"{separator}api_key={api_key}"

        static_map = StaticMap(
            width,
            height,
            url_template=normalised_url,
            background_color=background_color,
            headers=headers,
        )

        # Route polyline — matches Leaflet color and weight
        static_map.add_line(Line(coords, _LINE_COLOR, _LINE_WIDTH))

        # Start marker: white outer ring + green inner dot
        static_map.add_marker(CircleMarker(coords[0], _MARKER_OUTER_COLOR, _MARKER_OUTER_RADIUS))
        static_map.add_marker(CircleMarker(coords[0], _START_COLOR, _MARKER_INNER_RADIUS))

        # End marker: white outer ring + red inner dot
        static_map.add_marker(CircleMarker(coords[-1], _MARKER_OUTER_COLOR, _MARKER_OUTER_RADIUS))
        static_map.add_marker(CircleMarker(coords[-1], _END_COLOR, _MARKER_INNER_RADIUS))

        image = static_map.render()

        buffer = BytesIO()
        image.save(buffer, "WEBP", quality=_THUMBNAIL_QUALITY, method=_THUMBNAIL_METHOD)

        core_logger.print_to_log_and_console(
            f"Activity {activity_id}: thumbnail rendered ({width}x{height} WebP)",
            "info",
        )

        return buffer.getvalue()

    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        core_logger.print_to_log_and_console(
            f"Activity {activity_id}: thumbnail generation failed — {type(exc).__name__}: {exc}",
            "warning",
        )
        return None
