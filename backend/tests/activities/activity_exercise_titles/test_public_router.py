"""The public exercise-title route, through the production application: it follows the public-links setting."""

import pytest

import core.config as core_config
from tests._factories.activities import make_exercise_titles

_URL = f"{core_config.ROOT_PATH}/public/activities/exercise-titles"


@pytest.fixture
def catalogue(committed_sessions):
    with committed_sessions() as db:
        make_exercise_titles(db, [(1, 1, "Bench Press"), (1, 2, "Squat")])
        db.commit()


@pytest.mark.usefixtures("public_links")
def test_with_public_links_on_anyone_reads_the_catalogue(client, catalogue):
    response = client.get(_URL, params={"num_records": 1})

    assert response.status_code == 200
    body = response.json()
    assert ([i["wkt_step_name"] for i in body["items"]], body["total"], body["next"]) == (["Bench Press"], 2, 2)


def test_with_public_links_off_the_catalogue_is_an_empty_page(client, catalogue):
    response = client.get(_URL)

    assert response.status_code == 200
    body = response.json()
    assert (body["items"], body["total"], body["page"]) == ([], 0, 1)
