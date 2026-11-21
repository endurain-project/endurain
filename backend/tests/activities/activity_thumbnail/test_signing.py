"""Activity thumbnail addressing: storage keys, signed tokens and servable URLs."""

import time
import uuid

import itsdangerous

import core.config as core_config
import modules.activities.activity_media.signing as media_signing
import modules.activities.activity_thumbnail.integration_service as thumbnail_integration
import modules.activities.activity_thumbnail.signing as thumbnail_signing

_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_OTHER = uuid.UUID("00000000-0000-4000-8000-000000000002")


class TestToken:
    def test_a_token_is_valid_for_the_activity_it_was_minted_for(self):
        assert thumbnail_signing.verify_thumbnail_token(_ID, thumbnail_signing.sign_thumbnail_token(_ID)) is True

    def test_a_token_is_not_valid_for_another_activity(self):
        assert thumbnail_signing.verify_thumbnail_token(_OTHER, thumbnail_signing.sign_thumbnail_token(_ID)) is False

    def test_a_forged_or_malformed_token_is_refused_without_raising(self):
        for token in ("totally-made-up-token", "a.b.c.d", ""):
            assert thumbnail_signing.verify_thumbnail_token(_ID, token) is False

    def test_a_media_token_does_not_authorize_a_thumbnail(self):
        assert thumbnail_signing.verify_thumbnail_token(_ID, media_signing.sign_media_token(_ID)) is False

    def test_a_token_older_than_the_max_age_is_refused(self, monkeypatch):
        issued_long_ago = int(time.time()) - thumbnail_signing._SIGNER.max_age_seconds - 60
        monkeypatch.setattr(itsdangerous.TimestampSigner, "get_timestamp", lambda self: issued_long_ago)
        token = thumbnail_signing.sign_thumbnail_token(_ID)
        monkeypatch.undo()

        assert thumbnail_signing.verify_thumbnail_token(_ID, token) is False

    def test_a_token_inside_the_max_age_is_accepted(self, monkeypatch):
        signer = thumbnail_signing._SIGNER
        issued_recently = int(time.time()) - (signer.max_age_seconds - signer.bucket_seconds - 60)
        monkeypatch.setattr(itsdangerous.TimestampSigner, "get_timestamp", lambda self: issued_recently)
        token = thumbnail_signing.sign_thumbnail_token(_ID)
        monkeypatch.undo()

        assert thumbnail_signing.verify_thumbnail_token(_ID, token) is True


class TestUrl:
    def test_the_key_is_the_activity_id_with_a_webp_extension(self):
        assert thumbnail_signing.thumbnail_key(_ID) == f"{_ID}.webp"

    def test_a_stored_key_is_addressed_by_the_thumbnail_route_with_a_token_that_verifies(self):
        url = thumbnail_integration.thumbnail_url(thumbnail_signing.thumbnail_key(_ID), _ID)

        path, _, token = url.partition("?t=")
        assert path == f"{core_config.ROOT_PATH}/activities/{_ID}/thumbnail"
        assert thumbnail_signing.verify_thumbnail_token(_ID, token) is True

    def test_no_key_has_no_url(self):
        assert thumbnail_integration.thumbnail_url(None, _ID) is None
        assert thumbnail_integration.thumbnail_url("", _ID) is None
