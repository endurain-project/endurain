"""The thumbnail operations exposed only to data migrations."""

import modules.activities.activity_thumbnail.render as activity_thumbnail_render
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing

THUMBNAIL_WIDTH = activity_thumbnail_render.THUMBNAIL_WIDTH
THUMBNAIL_HEIGHT = activity_thumbnail_render.THUMBNAIL_HEIGHT
THUMBNAIL_CONTENT_TYPE = activity_thumbnail_render.THUMBNAIL_CONTENT_TYPE
THUMBNAIL_STORAGE_AREA = activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA
thumbnail_key = activity_thumbnail_signing.thumbnail_key
