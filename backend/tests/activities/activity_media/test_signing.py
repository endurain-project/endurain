"""Activity media addressing: signed tokens and servable URLs."""

import time
import uuid

import itsdangerous

import core.config as core_config
import modules.activities.activity_media.signing as media_signing
import modules.activities.activity_thumbnail.signing as thumbnail_signing

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_MEDIA_ID = uuid.UUID("00000000-0000-4000-8000-000000000042")
_OTHER_ID = uuid.UUID("00000000-0000-4000-8000-000000000043")


class TestMediaToken:
    def test_a_token_is_valid_for_the_media_it_was_minted_for(self):
        assert media_signing.verify_media_token(_MEDIA_ID, media_signing.sign_media_token(_MEDIA_ID)) is True

    def test_a_token_is_not_valid_for_another_media_id(self):
        assert media_signing.verify_media_token(_OTHER_ID, media_signing.sign_media_token(_MEDIA_ID)) is False

    def test_a_forged_or_malformed_token_is_refused_without_raising(self):
        for token in ("totally-made-up-token", "a.b.c.d", ""):
            assert media_signing.verify_media_token(_MEDIA_ID, token) is False

    def test_a_thumbnail_token_does_not_authorize_media(self):
        assert media_signing.verify_media_token(_MEDIA_ID, thumbnail_signing.sign_thumbnail_token(_MEDIA_ID)) is False

    def test_a_token_older_than_the_max_age_is_refused(self, monkeypatch):
        issued_long_ago = int(time.time()) - media_signing._SIGNER.max_age_seconds - 60
        monkeypatch.setattr(itsdangerous.TimestampSigner, "get_timestamp", lambda self: issued_long_ago)
        token = media_signing.sign_media_token(_MEDIA_ID)
        monkeypatch.undo()

        assert media_signing.verify_media_token(_MEDIA_ID, token) is False

    def test_a_token_inside_the_max_age_is_accepted(self, monkeypatch):
        signer = media_signing._SIGNER
        issued_recently = int(time.time()) - (signer.max_age_seconds - signer.bucket_seconds - 60)
        monkeypatch.setattr(itsdangerous.TimestampSigner, "get_timestamp", lambda self: issued_recently)
        token = media_signing.sign_media_token(_MEDIA_ID)
        monkeypatch.undo()

        assert media_signing.verify_media_token(_MEDIA_ID, token) is True


class TestMediaUrl:
    def test_a_local_url_addresses_the_activitys_media_route_with_a_token_that_verifies(self):
        url = media_signing.media_url(f"{_ACTIVITY_ID}_abc.jpg", _ACTIVITY_ID, _MEDIA_ID)

        path, _, token = url.partition("?t=")
        assert path == f"{core_config.ROOT_PATH}/activities/{_ACTIVITY_ID}/media/{_MEDIA_ID}/file"
        assert media_signing.verify_media_token(_MEDIA_ID, token) is True
