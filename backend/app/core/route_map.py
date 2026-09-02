# pyright: reportMissingTypeStubs=false
"""Static-map route renderer with SSRF-safe outbound tile requests.

Lives in ``core`` rather than in the activities module because it performs raw
network egress: ``activities-no-raw-egress`` in ``.importlinter`` forbids the
domain from importing ``staticmap`` / ``requests`` directly, so the outbound
call sits behind this host-owned seam next to the ``core.network`` host checks
it enforces.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import requests
from staticmap import CircleMarker, Line, StaticMap

import core.logger as core_logger
import core.network as core_network

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class RouteMapRenderRequest:
    """Renderer-neutral request to render a route over map tiles."""

    coordinates: tuple[tuple[float, float], ...]
    tile_url: str
    background_color: str
    headers: dict[str, str]
    width: int
    height: int
    line_color: str
    line_width: int
    marker_outer_color: str
    marker_outer_radius: int
    start_color: str
    end_color: str
    marker_inner_radius: int
    quality: int
    encoder_method: int
    request_timeout_seconds: float = 10.0


class UnsafeTileServerError(ValueError):
    """Raised when a tile URL violates the shared outbound-network policy."""


def _ensure_safe_url(url: str) -> None:
    """Reject a tile URL that could target an internal service."""
    reason = core_network.url_rejection_reason(url, purpose="activity_thumbnail_tile")
    if reason is not None:
        logger.warning(
            "Rejected an unsafe activity thumbnail tile URL",
            extra=core_logger.context(reason=reason),
        )
        raise UnsafeTileServerError(reason)


class _GuardedStaticMap(StaticMap):
    """StaticMap variant that validates every request and refuses redirects."""

    def get(self, url: str, **kwargs: Any) -> tuple[int, bytes]:
        """Fetch one validated tile without following redirects."""
        _ensure_safe_url(url)
        timeout = kwargs.pop("timeout", None) or 10.0
        response = requests.get(url, allow_redirects=False, timeout=timeout, **kwargs)
        return response.status_code, response.content


def render(request: RouteMapRenderRequest) -> bytes:
    """Render one route as WebP bytes.

    Args:
        request: The route geometry, tile source, and encoding options.

    Returns:
        The rendered map as WebP-encoded bytes.

    Raises:
        ValueError: When fewer than two coordinates are supplied.
        UnsafeTileServerError: When the tile URL targets a non-public address.
    """
    if len(request.coordinates) < 2:
        raise ValueError("At least two route coordinates are required")

    _ensure_safe_url(request.tile_url.format(z=0, x=0, y=0))
    static_map = _GuardedStaticMap(
        request.width,
        request.height,
        url_template=request.tile_url,
        tile_request_timeout=request.request_timeout_seconds,
        background_color=request.background_color,
        headers=request.headers,
    )
    static_map.add_line(Line(list(request.coordinates), request.line_color, request.line_width))
    static_map.add_marker(CircleMarker(request.coordinates[0], request.marker_outer_color, request.marker_outer_radius))
    static_map.add_marker(CircleMarker(request.coordinates[0], request.start_color, request.marker_inner_radius))
    static_map.add_marker(
        CircleMarker(request.coordinates[-1], request.marker_outer_color, request.marker_outer_radius)
    )
    static_map.add_marker(CircleMarker(request.coordinates[-1], request.end_color, request.marker_inner_radius))

    image = static_map.render()
    buffer = BytesIO()
    image.save(buffer, "WEBP", quality=request.quality, method=request.encoder_method)
    return buffer.getvalue()
