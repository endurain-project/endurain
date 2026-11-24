"""The public activity link, through the production application: no credentials, and only what is shared."""

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_activity
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/public/activities"
_Visibility = activity_constants.ActivityVisibility
_MISSING = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


@pytest.fixture
def links_shared(arrange):
    arrange(lambda db: edit_server_settings(db, public_shareable_links=True))


class TestReadPublicActivity:
    def test_a_public_activity_is_served_without_credentials_and_without_what_its_owner_hid(
        self, client, links_shared, owner, make_committed_activity
    ):
        activity = make_committed_activity(
            owner, visibility=_Visibility.PUBLIC, private_notes="mine", hide_hr=True, average_hr=150, city="Porto"
        )

        response = client.get(f"{_URL}/{activity.id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["city"], body["average_hr"], body["private_notes"]) == (
            str(activity.id),
            "Porto",
            None,
            None,
        )

    def test_nothing_is_served_while_the_server_does_not_share_public_links(
        self, client, owner, make_committed_activity
    ):
        activity = make_committed_activity(owner, visibility=_Visibility.PUBLIC)

        assert client.get(f"{_URL}/{activity.id}").status_code == 404

    @pytest.mark.parametrize(
        "fields",
        [{"visibility": _Visibility.FOLLOWERS}, {"visibility": _Visibility.PRIVATE}, {"is_hidden": True}],
    )
    def test_an_activity_that_is_not_public_is_404_exactly_like_one_that_does_not_exist(
        self, client, links_shared, owner, make_committed_activity, fields
    ):
        activity = make_committed_activity(owner, **{"visibility": _Visibility.PUBLIC, **fields})

        hidden = client.get(f"{_URL}/{activity.id}")
        missing = client.get(f"{_URL}/{_MISSING}")

        assert (hidden.status_code, missing.status_code) == (404, 404)
        assert hidden.json()["detail"] == missing.json()["detail"]

    def test_an_activity_synced_from_the_strava_api_is_never_public(
        self, client, links_shared, owner, make_committed_activity
    ):
        activity = make_committed_activity(owner, visibility=_Visibility.PUBLIC, strava_activity_id=1)

        assert client.get(f"{_URL}/{activity.id}").status_code == 404

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    def test_the_activity_of_an_inactive_or_pending_owner_is_404(self, client, links_shared, arrange, state):
        gone = arrange(lambda db: make_user(db, **state))
        activity = arrange(lambda db: make_activity(db, gone.id, visibility=_Visibility.PUBLIC))

        assert client.get(f"{_URL}/{activity.id}").status_code == 404

    def test_a_malformed_activity_id_is_422(self, client):
        assert client.get(f"{_URL}/not-a-uuid").status_code == 422
