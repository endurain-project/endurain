"""The workout steps route, through the production application: the page envelope, paging, and who is told what."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_workout_steps

_VISIBILITY = activity_constants.ActivityVisibility
_EMPTY = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/workout-steps"


def _stage(db, activity):
    make_workout_steps(
        db,
        activity,
        [
            {"message_index": 1, "duration_type": "distance", "duration_value": 1000.0, "target_value": 150},
            {"message_index": 0, "duration_type": "time", "duration_value": 300.0, "notes": "warm up"},
        ],
    )


class TestList:
    def test_the_owner_gets_the_steps_in_workout_order_in_a_page_envelope(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 200, None)
        assert [item["message_index"] for item in body["items"]] == [0, 1]
        assert body["items"][0]["activity_id"] == str(activity.id)
        assert (body["items"][0]["notes"], body["items"][1]["target_value"]) == ("warm up", 150)

    def test_a_page_holds_its_slice_and_names_the_next_one(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)
        client = sign_in(people.owner).client

        first = client.get(_url(activity.id), params={"page_number": 1, "num_records": 1}).json()
        last = client.get(_url(activity.id), params={"page_number": 2, "num_records": 1}).json()

        assert ([item["message_index"] for item in first["items"]], first["next"]) == ([0], 2)
        assert ([item["message_index"] for item in last["items"]], last["next"]) == ([1], None)

    @pytest.mark.parametrize("params", [{"page_number": 0}, {"num_records": 0}, {"num_records": 201}])
    def test_a_paging_value_out_of_range_is_a_validation_error(self, sign_in, people, make_owned_activity, params):
        activity = make_owned_activity(stage=_stage)

        assert sign_in(people.owner).client.get(_url(activity.id), params=params).status_code == 422

    def test_a_malformed_activity_id_is_a_validation_error(self, sign_in, people):
        assert sign_in(people.owner).client.get(_url("not-a-uuid")).status_code == 422

    def test_a_stranger_gets_the_page_an_activity_that_does_not_exist_gets(self, sign_in, people, make_owned_activity):
        shared = make_owned_activity(_VISIBILITY.PRIVATE, stage=_stage)
        client = sign_in(people.stranger).client

        refused = client.get(_url(shared.id))
        missing = client.get(_url(uuid.uuid4()))

        assert refused.status_code == missing.status_code == 200
        assert refused.json() == missing.json() == _EMPTY

    def test_a_follower_gets_the_steps_of_a_followers_only_activity(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage)

        assert sign_in(people.follower).client.get(_url(activity.id)).json()["total"] == 2

    def test_hide_workout_sets_steps_empties_the_page_for_a_follower_and_not_for_the_owner(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_workout_sets_steps=True)

        assert sign_in(people.follower).client.get(_url(activity.id)).json()["total"] == 0
        assert sign_in(people.owner).client.get(_url(activity.id)).json()["total"] == 2
