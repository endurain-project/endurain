"""The media routes, through the production application: upload, list and delete of an activity's photos."""

import uuid

import jasil.runtime as platform_runtime
import pytest
from sqlalchemy import select

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.activities.activity_media.constants as media_constants
import modules.activities.activity_media.models as media_models
from tests._helpers import images

_AREA = media_constants.MEDIA_STORAGE_AREA
_ROOT = core_config.ROOT_PATH


def _url(activity_id: uuid.UUID | str, media_id: uuid.UUID | str = "") -> str:
    return f"{_ROOT}/activities/{activity_id}/media" + (f"/{media_id}" if media_id else "")


def _upload(client, activity_id, data: bytes, name: str = "photo.jpg", content_type: str = "image/jpeg"):
    return client.post(_url(activity_id), files={"file": (name, data, content_type)})


def _stored_media(committed_sessions, activity_id):
    with committed_sessions() as db:
        return db.scalars(
            select(media_models.ActivityMedia).where(media_models.ActivityMedia.activity_id == activity_id)
        ).all()


@pytest.fixture
def activity(make_owned_activity):
    return make_owned_activity()


class TestUpload:
    def test_a_photo_is_stored_without_its_metadata_and_answered_with_a_signed_url(
        self, sign_in, people, activity, committed_sessions
    ):
        original = images.jpeg_with_exif()

        response = _upload(sign_in(people.owner).client, activity.id, original)

        assert response.status_code == 201
        body = response.json()
        assert (body["activity_id"], body["media_type"]) == (str(activity.id), "photo")
        assert body["url"].startswith(f"{_ROOT}/activities/{activity.id}/media/{body['id']}/file?t=")
        [row] = _stored_media(committed_sessions, activity.id)
        stored = platform_runtime.get_active_platform().storage.get(_AREA, row.media_path)
        assert str(row.id) == body["id"] and stored is not None and not images.has_metadata(stored)

    def test_the_activity_is_touched_but_not_edited(self, sign_in, people, activity, committed_sessions):
        def state():
            with committed_sessions() as db:
                row = db.get(activity_models.Activity, activity.id)
                return row.version, row.updated_at

        before = state()
        _upload(sign_in(people.owner).client, activity.id, images.png_with_text())

        after = state()
        assert after[0] == before[0] and after[1] >= before[1]

    def test_the_photo_is_served_back_through_its_signed_url(self, sign_in, people, activity, client):
        body = _upload(sign_in(people.owner).client, activity.id, images.png_with_text(), "a.png").json()

        served = client.get(body["url"])

        assert served.status_code == 200
        assert served.headers["content-type"] == "image/png"
        assert not images.has_metadata(served.content)

    def test_the_same_photo_twice_answers_the_same_record(self, sign_in, people, activity, committed_sessions):
        client = sign_in(people.owner).client
        data = images.png_with_text()

        first = _upload(client, activity.id, data, "a.png").json()
        second = _upload(client, activity.id, data, name="again.png").json()

        assert first["id"] == second["id"]
        assert len(_stored_media(committed_sessions, activity.id)) == 1

    @pytest.mark.parametrize(
        ("name", "data"),
        [("a.gif", images.gif()), ("a.heic", images.heic_like()), ("a.jpg", b"not an image"), ("a.txt", b"text")],
    )
    def test_a_file_that_is_not_an_accepted_image_is_refused_and_stores_nothing(
        self, sign_in, people, activity, committed_sessions, name, data
    ):
        response = _upload(sign_in(people.owner).client, activity.id, data, name=name)

        assert 400 <= response.status_code < 500 and response.status_code != 404
        assert _stored_media(committed_sessions, activity.id) == []

    def test_a_request_without_a_file_is_a_validation_error(self, sign_in, people, activity):
        assert sign_in(people.owner).client.post(_url(activity.id)).status_code == 422

    def test_another_users_activity_is_a_404_and_stores_nothing(self, sign_in, people, activity, committed_sessions):
        response = _upload(sign_in(people.stranger).client, activity.id, images.png_with_text(), name="a.png")

        assert response.status_code == 404
        assert _stored_media(committed_sessions, activity.id) == []

    def test_a_follower_cannot_upload_to_a_followers_only_activity(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(visibility=activity_constants.ActivityVisibility.FOLLOWERS)

        assert _upload(sign_in(people.follower).client, activity.id, images.png_with_text(), "a.png").status_code == 404


class TestList:
    def test_the_owner_lists_the_photos_in_a_page_envelope_with_signed_urls(self, sign_in, people, activity):
        client = sign_in(people.owner).client
        first = _upload(client, activity.id, images.png_with_text(), "a.png").json()
        second = _upload(client, activity.id, images.jpeg_with_exif()).json()

        body = client.get(_url(activity.id)).json()

        assert [item["id"] for item in body["items"]] == [first["id"], second["id"]]
        assert (body["total"], body["page"], body["next"]) == (2, 1, None)
        assert set(body["items"][0]) == {"id", "activity_id", "media_type", "url"}

    def test_a_page_holds_its_slice_and_names_the_next_one(self, sign_in, people, activity):
        client = sign_in(people.owner).client
        _upload(client, activity.id, images.png_with_text(), "a.png")
        _upload(client, activity.id, images.jpeg_with_exif())

        body = client.get(_url(activity.id), params={"page_number": 1, "num_records": 1}).json()

        assert (len(body["items"]), body["total"], body["next"]) == (1, 2, 2)

    def test_a_stranger_gets_the_page_an_activity_that_does_not_exist_gets(self, sign_in, people, activity):
        _upload(sign_in(people.owner).client, activity.id, images.png_with_text(), "a.png")
        client = sign_in(people.stranger).client

        refused = client.get(_url(activity.id)).json()
        missing = client.get(_url(uuid.uuid4())).json()

        assert refused == missing == {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}

    @pytest.mark.parametrize("params", [{"page_number": 0}, {"num_records": 0}, {"num_records": 201}])
    def test_a_paging_value_out_of_range_is_a_validation_error(self, sign_in, people, activity, params):
        assert sign_in(people.owner).client.get(_url(activity.id), params=params).status_code == 422


class TestDelete:
    def test_the_photo_and_its_blob_go_with_a_204(self, sign_in, people, activity, committed_sessions):
        client = sign_in(people.owner).client
        body = _upload(client, activity.id, images.png_with_text(), "a.png").json()
        [row] = _stored_media(committed_sessions, activity.id)

        response = client.delete(_url(activity.id, body["id"]))

        assert (response.status_code, response.content) == (204, b"")
        assert _stored_media(committed_sessions, activity.id) == []
        assert not platform_runtime.get_active_platform().storage.exists(_AREA, row.media_path)

    def test_a_missing_photo_is_a_404(self, sign_in, people, activity):
        assert sign_in(people.owner).client.delete(_url(activity.id, uuid.uuid4())).status_code == 404

    def test_a_photo_reached_through_another_activity_is_a_404_and_stays(
        self, sign_in, people, make_owned_activity, activity, committed_sessions
    ):
        other = make_owned_activity(
            start_time=activity.start_time.replace(day=12), end_time=activity.end_time.replace(day=12)
        )
        client = sign_in(people.owner).client
        body = _upload(client, activity.id, images.png_with_text(), "a.png").json()

        response = client.delete(_url(other.id, body["id"]))

        assert response.status_code == 404
        assert len(_stored_media(committed_sessions, activity.id)) == 1

    def test_a_malformed_media_id_is_a_validation_error(self, sign_in, people, activity):
        assert sign_in(people.owner).client.delete(_url(activity.id, "not-a-uuid")).status_code == 422
