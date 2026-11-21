"""The public workout steps route, through the production application: it follows the parent's visibility."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_workout_steps

_VISIBILITY = activity_constants.ActivityVisibility
_EMPTY = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/public/activities/{activity_id}/workout-steps"


def _stage(db, activity):
    make_workout_steps(db, activity, [{"message_index": 0, "duration_type": "time", "notes": "go"}])


@pytest.mark.usefixtures("public_links")
class TestPublicList:
    def test_the_steps_of_a_public_activity_need_no_credentials(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

        response = client.get(_url(activity.id))

        assert response.status_code == 200
        assert [item["notes"] for item in response.json()["items"]] == ["go"]

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_answers_as_a_missing_one_does(
        self, client, make_owned_activity, visibility
    ):
        activity = make_owned_activity(visibility, stage=_stage)

        assert client.get(_url(activity.id)).json() == client.get(_url(uuid.uuid4())).json() == _EMPTY

    def test_hide_workout_sets_steps_serves_nothing(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_workout_sets_steps=True)

        assert client.get(_url(activity.id)).json()["total"] == 0

    def test_a_malformed_activity_id_is_a_validation_error(self, client):
        assert client.get(_url("not-a-uuid")).status_code == 422


def test_with_public_links_off_a_public_activity_serves_no_steps(client, make_owned_activity):
    activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

    assert client.get(_url(activity.id)).json() == _EMPTY
