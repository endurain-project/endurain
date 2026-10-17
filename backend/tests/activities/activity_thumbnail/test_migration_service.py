"""Tests that the migration surface stays pinned to the render and signing values."""

import modules.activities.activity_thumbnail.migration_service as migration_service
import modules.activities.activity_thumbnail.render as render
import modules.activities.activity_thumbnail.signing as signing


def test_render_constants_match():
    assert migration_service.THUMBNAIL_WIDTH == render.THUMBNAIL_WIDTH
    assert migration_service.THUMBNAIL_HEIGHT == render.THUMBNAIL_HEIGHT
    assert migration_service.THUMBNAIL_CONTENT_TYPE == render.THUMBNAIL_CONTENT_TYPE


def test_storage_addressing_matches():
    assert migration_service.THUMBNAIL_STORAGE_AREA == signing.THUMBNAIL_STORAGE_AREA
    assert migration_service.thumbnail_key(5) == signing.thumbnail_key(5)
