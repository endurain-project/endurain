# pyright: reportMissingTypeStubs=false
"""Static-map route renderer with SSRF-safe outbound tile requests."""

from io import BytesIO
from typing import Any

import requests
from staticmap import CircleMarker, Line, StaticMap

import core.logger as core_logger
import core.network as core_network
from infra.providers import RouteMapRenderRequest

logger = core_logger.get_logger(__name__)


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


class StaticRouteMapRenderer:
    """Render route maps using ``staticmap`` behind the platform provider port."""

    def render(self, request: RouteMapRenderRequest) -> bytes:
        """Render one route as WebP bytes."""
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
        static_map.add_marker(
            CircleMarker(request.coordinates[0], request.marker_outer_color, request.marker_outer_radius)
        )
        static_map.add_marker(CircleMarker(request.coordinates[0], request.start_color, request.marker_inner_radius))
        static_map.add_marker(
            CircleMarker(request.coordinates[-1], request.marker_outer_color, request.marker_outer_radius)
        )
        static_map.add_marker(CircleMarker(request.coordinates[-1], request.end_color, request.marker_inner_radius))

        image = static_map.render()
        buffer = BytesIO()
        image.save(buffer, "WEBP", quality=request.quality, method=request.encoder_method)
        return buffer.getvalue()
