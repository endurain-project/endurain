"""The token-gated media file route, through the production application: the signed token is the only credential."""

import uuid

import core.config as core_config
import modules.activities.activity_media.signing as media_signing
from tests._factories.activities import make_stored_media
from tests._helpers import images

_ROOT = core_config.ROOT_PATH


def _url(activity_id, media_id) -> str:
    return f"{_ROOT}/activities/{activity_id}/media/{media_id}/file"


def _photo(committed_sessions, make_owned_activity, data: bytes, name: str):
    holder = {}

    def stage(db, activity):
        holder["media"] = make_stored_media(db, activity, data, name)

    activity = make_owned_activity(stage=stage)
    return activity, holder["media"]


class TestFile:
    def test_a_valid_token_serves_the_stored_bytes_with_the_type_of_the_extension_and_a_private_cache(
        self, client, committed_sessions, make_owned_activity
    ):
        activity, media = _photo(committed_sessions, make_owned_activity, images.png_with_text(), "a.png")
        token = media_signing.sign_media_token(media.id)

        response = client.get(_url(activity.id, media.id), params={"t": token})

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"].startswith("private, max-age=")
        assert not images.has_metadata(response.content)

    def test_a_jpeg_and_a_webp_are_served_with_their_own_types(self, client, committed_sessions, make_owned_activity):
        activity, jpeg = _photo(committed_sessions, make_owned_activity, images.jpeg_with_exif(), "a.jpg")
        types = {}
        types["jpeg"] = client.get(_url(activity.id, jpeg.id), params={"t": media_signing.sign_media_token(jpeg.id)})
        other, webp = _photo(committed_sessions, make_owned_activity, images.webp_with_exif(), "a.webp")

        types["webp"] = client.get(_url(other.id, webp.id), params={"t": media_signing.sign_media_token(webp.id)})

        assert (types["jpeg"].headers["content-type"], types["webp"].headers["content-type"]) == (
            "image/jpeg",
            "image/webp",
        )

    def test_a_forged_token_is_a_404_problem_that_confirms_nothing(
        self, client, committed_sessions, make_owned_activity
    ):
        activity, media = _photo(committed_sessions, make_owned_activity, images.png_with_text(), "a.png")

        forged = client.get(_url(activity.id, media.id), params={"t": "forged"})
        missing = client.get(_url(activity.id, uuid.uuid4()), params={"t": "forged"})

        assert forged.status_code == missing.status_code == 404
        assert forged.json()["type"] == missing.json()["type"] == "urn:endurain:error:not-found"

    def test_a_token_minted_for_another_photo_is_a_404(self, client, committed_sessions, make_owned_activity):
        activity, media = _photo(committed_sessions, make_owned_activity, images.png_with_text(), "a.png")

        response = client.get(_url(activity.id, media.id), params={"t": media_signing.sign_media_token(uuid.uuid4())})

        assert response.status_code == 404

    def test_a_token_replayed_under_another_activity_is_a_404(self, client, committed_sessions, make_owned_activity):
        _, media = _photo(committed_sessions, make_owned_activity, images.png_with_text(), "a.png")

        response = client.get(_url(uuid.uuid4(), media.id), params={"t": media_signing.sign_media_token(media.id)})

        assert response.status_code == 404

    def test_a_request_without_a_token_is_a_validation_error(self, client, committed_sessions, make_owned_activity):
        activity, media = _photo(committed_sessions, make_owned_activity, images.png_with_text(), "a.png")

        assert client.get(_url(activity.id, media.id)).status_code == 422

    def test_malformed_ids_are_a_validation_error(self, client):
        assert client.get(_url("not-a-uuid", uuid.uuid4()), params={"t": "x"}).status_code == 422
        assert client.get(_url(uuid.uuid4(), "not-a-uuid"), params={"t": "x"}).status_code == 422
