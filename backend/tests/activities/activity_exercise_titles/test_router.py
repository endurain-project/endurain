"""The exercise-title catalogue route, through the production application."""

import pytest

import core.config as core_config
from tests._factories.activities import make_exercise_titles

_URL = f"{core_config.ROOT_PATH}/activities/exercise-titles"


@pytest.fixture
def catalogue(committed_sessions):
    with committed_sessions() as db:
        make_exercise_titles(db, [(1, n, f"Step {n}") for n in range(3)])
        db.commit()


class TestList:
    def test_a_user_gets_the_catalogue_in_a_page_envelope(self, me, catalogue):
        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["next"]) == (3, 1, None)
        assert [item["wkt_step_name"] for item in body["items"]] == ["Step 0", "Step 1", "Step 2"]
        assert set(body["items"][0]) == {"id", "exercise_category", "exercise_name", "wkt_step_name"}

    def test_a_page_holds_its_slice_and_names_the_next_one(self, me, catalogue):
        first = me.client.get(_URL, params={"page_number": 1, "num_records": 2}).json()
        last = me.client.get(_URL, params={"page_number": 2, "num_records": 2}).json()

        assert ([i["exercise_name"] for i in first["items"]], first["next"]) == ([0, 1], 2)
        assert ([i["exercise_name"] for i in last["items"]], last["next"]) == ([2], None)

    def test_an_empty_catalogue_is_an_empty_page(self, me):
        body = me.client.get(_URL).json()

        assert (body["items"], body["total"]) == ([], 0)

    @pytest.mark.parametrize("params", [{"page_number": 0}, {"num_records": 0}, {"num_records": 201}])
    def test_a_paging_value_out_of_range_is_a_validation_error(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422
