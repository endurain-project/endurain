"""The token-gated thumbnail route, through the production application: the signed token is the only credential."""

import io
import uuid

import jasil.runtime as platform_runtime
from PIL import Image

import core.config as core_config
import modules.activities.activity_thumbnail.constants as thumbnail_constants
import modules.activities.activity_thumbnail.signing as thumbnail_signing

_AREA = thumbnail_constants.THUMBNAIL_STORAGE_AREA


def _url(activity_id) -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/thumbnail"


def _webp() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 4), (10, 200, 30)).save(buffer, "WEBP")
    return buffer.getvalue()


def _store(activity_id: uuid.UUID) -> bytes:
    data = _webp()
    platform_runtime.get_active_platform().storage.save(
        _AREA, thumbnail_signing.thumbnail_key(activity_id), data, "image/webp"
    )
    return data


def test_a_valid_token_serves_the_stored_image_as_webp_with_a_private_cache(client):
    activity_id = uuid.uuid4()
    data = _store(activity_id)

    response = client.get(_url(activity_id), params={"t": thumbnail_signing.sign_thumbnail_token(activity_id)})

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"].startswith("private, max-age=")


def test_a_forged_token_is_the_same_404_as_a_thumbnail_that_does_not_exist(client):
    activity_id = uuid.uuid4()
    _store(activity_id)

    forged = client.get(_url(activity_id), params={"t": "forged"})
    missing = client.get(_url(uuid.uuid4()), params={"t": "forged"})

    assert forged.status_code == missing.status_code == 404
    assert forged.json()["type"] == missing.json()["type"] == "urn:endurain:error:not-found"


def test_a_token_minted_for_another_activity_is_a_404(client):
    activity_id = uuid.uuid4()
    _store(activity_id)

    response = client.get(_url(activity_id), params={"t": thumbnail_signing.sign_thumbnail_token(uuid.uuid4())})

    assert response.status_code == 404


def test_a_valid_token_for_an_activity_with_no_thumbnail_is_a_404(client):
    activity_id = uuid.uuid4()

    response = client.get(_url(activity_id), params={"t": thumbnail_signing.sign_thumbnail_token(activity_id)})

    assert response.status_code == 404


def test_a_request_without_a_token_is_a_validation_error(client):
    assert client.get(_url(uuid.uuid4())).status_code == 422


def test_a_malformed_activity_id_is_a_validation_error(client):
    assert client.get(_url("not-a-uuid"), params={"t": "x"}).status_code == 422
