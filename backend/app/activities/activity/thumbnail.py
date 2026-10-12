"""Thumbnail generation for activity map previews.

Generates static PNG map images using OpenStreetMap tiles and
a polyline overlay of the activity route. Thumbnails are created
at activity import time and served as static files.
"""

import re
from pathlib import Path

from staticmap import CircleMarker, Line, StaticMap

import core.config as core_config
import core.logger as core_logger

# Fallback tile URL used when server settings are unavailable.
# Uses a fixed subdomain; staticmap does not support {s} rotation.
_DEFAULT_TILE_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
_DEFAULT_BG_COLOR = "#dddddd"

# Visual constants matching the Leaflet map renderer
_LINE_COLOR = "#2563eb"
_LINE_WIDTH = 4
_MARKER_OUTER_COLOR = "#ffffff"
_MARKER_OUTER_RADIUS = 20
_START_COLOR = "#28a745"
_END_COLOR = "#dc3545"
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


def generate_activity_thumbnail(
    activity_id: int,
    waypoints: list[dict],
    output_dir: str,
    tile_url: str = _DEFAULT_TILE_URL,
    background_color: str = _DEFAULT_BG_COLOR,
    api_key: str | None = None,
    width: int = 1200,
    height: int = 400,
) -> str | None:
    """Generate a static map thumbnail for an activity.

    Renders map tiles with the activity polyline and start/end
    markers overlaid, matching the Leaflet map appearance used
    on the activity detail page. Saves the result as a PNG.

    Args:
        activity_id: The activity ID, used as the filename.
        waypoints: List of dicts with 'lat' and 'lon' keys.
        output_dir: Absolute directory path to save the PNG.
        tile_url: Leaflet-style tile URL template. {s} subdomains
            are normalised to 'a' automatically.
        background_color: Hex background color for the map canvas.
        api_key: Optional tile provider API key. When provided,
            sent as 'Authorization: Stadia-Auth <key>' HTTP header
            (compatible with Stadia Maps and similar providers).
        width: Thumbnail width in pixels (default 1200).
        height: Thumbnail height in pixels (default 400).

    Returns:
        Absolute path to the saved thumbnail file, or None if
        generation was skipped or failed.

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

        output_path = Path(output_dir) / f"{activity_id}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(output_path), "PNG")

        core_logger.print_to_log_and_console(
            f"Activity {activity_id}: thumbnail saved to {output_path}",
            "info",
        )

        return str(output_path)

    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
        core_logger.print_to_log_and_console(
            f"Activity {activity_id}: thumbnail generation failed — {type(exc).__name__}: {exc}",
            "warning",
        )
        return None
