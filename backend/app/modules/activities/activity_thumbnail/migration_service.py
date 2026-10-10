"""Version-pinned thumbnail operations exposed only to data migrations."""

import modules.activities.activity_thumbnail.render as thumbnail_render
import modules.activities.activity_thumbnail.signing as thumbnail_signing

THUMBNAIL_WIDTH = thumbnail_render.THUMBNAIL_WIDTH
THUMBNAIL_HEIGHT = thumbnail_render.THUMBNAIL_HEIGHT
THUMBNAIL_CONTENT_TYPE = thumbnail_render.THUMBNAIL_CONTENT_TYPE
THUMBNAIL_STORAGE_AREA = thumbnail_signing.THUMBNAIL_STORAGE_AREA
thumbnail_key = thumbnail_signing.thumbnail_key
