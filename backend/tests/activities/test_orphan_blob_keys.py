"""Each activity storage area names the activity that owns a blob, so the orphan sweep can find it."""

import modules.activities.activity_file_storage.files as files
import modules.activities.activity_media.service as media_service
import modules.activities.activity_thumbnail.service as thumbnail_service


class TestKeyParsers:
    def test_processed_key_names_its_activity(self):
        assert files.activity_id_of_processed_key("processed/42.fit") == 42

    def test_staged_upload_in_the_same_area_is_not_a_retained_file(self):
        assert files.activity_id_of_processed_key("upload_staging/42.fit") is None

    def test_processed_key_with_unknown_extension_is_ignored(self):
        assert files.activity_id_of_processed_key("processed/42.exe") is None

    def test_thumbnail_key(self):
        assert thumbnail_service._activity_id_of_thumbnail_key("7.webp") == 7
        assert thumbnail_service._activity_id_of_thumbnail_key("7.png") is None
        assert thumbnail_service._activity_id_of_thumbnail_key("x.webp") is None

    def test_media_key(self):
        assert media_service._activity_id_of_media_key("7_abc.jpg") == 7
        assert media_service._activity_id_of_media_key("abc.jpg") is None
