"""The laps route, through the production application: the page envelope, paging, and who is told what."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import DEFAULT_START, make_laps

_VISIBILITY = activity_constants.ActivityVisibility


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/laps"


def _stage(db, activity):
    make_laps(
        db,
        activity,
        [
            {"start_time": DEFAULT_START, "total_distance": 1000.0, "avg_heart_rate": 150},
            {"start_time": DEFAULT_START.replace(minute=10), "total_distance": 900.0, "avg_heart_rate": 155},
        ],
    )


class TestList:
    def test_the_owner_gets_the_laps_in_recorded_order_in_a_page_envelope(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 200, None)
        assert [lap["total_distance"] for lap in body["items"]] == [1000.0, 900.0]
        assert body["items"][0]["activity_id"] == str(activity.id)
        assert body["items"][0]["start_time"] == "2025-03-10T08:00:00Z"
        assert body["items"][0]["avg_power"] is None

    def test_a_page_holds_its_slice_and_names_the_next_one(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)
        client = sign_in(people.owner).client

        first = client.get(_url(activity.id), params={"page_number": 1, "num_records": 1}).json()
        last = client.get(_url(activity.id), params={"page_number": 2, "num_records": 1}).json()

        assert ([lap["total_distance"] for lap in first["items"]], first["next"]) == ([1000.0], 2)
        assert ([lap["total_distance"] for lap in last["items"]], last["next"]) == ([900.0], None)

    @pytest.mark.parametrize(
        "params",
        [{"page_number": 0}, {"num_records": 0}, {"num_records": 201}, {"page_number": "x"}],
    )
    def test_a_paging_value_out_of_range_is_a_validation_error(self, sign_in, people, make_owned_activity, params):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id), params=params)

        assert response.status_code == 422

    def test_a_malformed_activity_id_is_a_validation_error(self, sign_in, people):
        assert sign_in(people.owner).client.get(_url("not-a-uuid")).status_code == 422

    def test_a_stranger_gets_the_page_an_activity_that_does_not_exist_gets(self, sign_in, people, make_owned_activity):
        shared = make_owned_activity(_VISIBILITY.PRIVATE, stage=_stage)
        client = sign_in(people.stranger).client

        refused = client.get(_url(shared.id))
        missing = client.get(_url(uuid.uuid4()))

        assert refused.status_code == missing.status_code == 200
        assert (
            refused.json() == missing.json() == {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}
        )

    def test_a_follower_gets_the_laps_of_a_followers_only_activity_without_what_it_hides(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_hr=True, hide_start_time=True)

        body = sign_in(people.follower).client.get(_url(activity.id)).json()

        assert body["total"] == 2
        assert [(lap["avg_heart_rate"], lap["start_time"]) for lap in body["items"]] == [(None, None), (None, None)]
        assert body["items"][0]["total_distance"] == 1000.0

    def test_hide_laps_empties_the_page_for_a_follower_and_not_for_the_owner(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_laps=True)

        assert sign_in(people.follower).client.get(_url(activity.id)).json()["total"] == 0
        assert sign_in(people.owner).client.get(_url(activity.id)).json()["total"] == 2
