"""The workout sets route, through the production application: the page envelope, paging, and who is told what."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import DEFAULT_START, make_sets

_VISIBILITY = activity_constants.ActivityVisibility
_EMPTY = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/sets"


def _stage(db, activity):
    make_sets(
        db,
        activity,
        [
            {"start_time": DEFAULT_START.isoformat(), "duration": 30.0, "set_type": "active", "repetitions": 10},
            {"start_time": DEFAULT_START.replace(minute=5).isoformat(), "duration": 60.0, "set_type": "rest"},
        ],
    )


class TestList:
    def test_the_owner_gets_the_sets_in_recorded_order_in_a_page_envelope(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 200, None)
        assert [item["set_type"] for item in body["items"]] == ["active", "rest"]
        assert body["items"][0]["activity_id"] == str(activity.id)
        assert body["items"][0]["start_time"] == "2025-03-10T08:00:00Z"
        assert (body["items"][0]["repetitions"], body["items"][1]["repetitions"]) == (10, None)

    def test_a_page_holds_its_slice_and_names_the_next_one(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)
        client = sign_in(people.owner).client

        first = client.get(_url(activity.id), params={"page_number": 1, "num_records": 1}).json()
        last = client.get(_url(activity.id), params={"page_number": 2, "num_records": 1}).json()

        assert ([item["set_type"] for item in first["items"]], first["next"]) == (["active"], 2)
        assert ([item["set_type"] for item in last["items"]], last["next"]) == (["rest"], None)

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

    def test_a_follower_gets_the_sets_of_a_followers_only_activity_without_their_start(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_start_time=True)

        body = sign_in(people.follower).client.get(_url(activity.id)).json()

        assert [(item["start_time"], item["set_type"]) for item in body["items"]] == [(None, "active"), (None, "rest")]

    def test_hide_workout_sets_steps_empties_the_page_for_a_follower_and_not_for_the_owner(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_workout_sets_steps=True)

        assert sign_in(people.follower).client.get(_url(activity.id)).json()["total"] == 0
        assert sign_in(people.owner).client.get(_url(activity.id)).json()["total"] == 2
