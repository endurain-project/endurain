"""Inter-module data shapes for server settings.

Separate from ``schema.py`` (the HTTP request/response payloads) because these
are shapes other modules consume, not shapes a client ever sees — keeping them
apart also keeps the generated OpenAPI free of internal types.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TileServerSettings:
    """The configured map-tile source, ready to render with.

    Attributes:
        tile_url: Tile URL template, or None when unconfigured.
        background_color: Map canvas background colour, or None when unconfigured.
        api_key: Tile-provider API key, **decrypted**. Decryption happens inside
            the owning module so a consumer never handles the ciphertext or the
            key material.
    """

    tile_url: str | None = None
    background_color: str | None = None
    api_key: str | None = None
