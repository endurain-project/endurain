"""The legs of a multisport activity through the activity routes, with real authentication and database."""

from datetime import UTC, datetime

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_activity, make_multisport
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings

_URL = f"{core_config.ROOT_PATH}/activities"
_PUBLIC_URL = f"{core_config.ROOT_PATH}/public/activities"
_START = datetime(2026, 7, 28, 9, tzinfo=UTC)
_MISSING = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"
_Visibility = activity_constants.ActivityVisibility


@pytest.fixture
def group(arrange, owner):
    """A committed public multisport activity of the owner with its five legs."""
    return arrange(lambda db: make_multisport(db, owner.id, start=_START, visibility=_Visibility.PUBLIC))


@pytest.fixture
def links_shared(arrange):
    arrange(lambda db: edit_server_settings(db, public_shareable_links=True))


def _ids(response):
    return [item["id"] for item in response.json()["items"]]


class TestOwner:
    def test_the_owner_gets_the_legs_in_start_order_with_the_total(self, me, group):
        parent, legs = group

        response = me.client.get(f"{_URL}/{parent.id}/legs")

        assert response.status_code == 200
        assert _ids(response) == [str(leg.id) for leg in legs]
        assert response.json()["total"] == len(legs)
        assert all(item["parent_activity_id"] == str(parent.id) for item in response.json()["items"])

    def test_the_legs_are_ordered_by_start_time_then_id_whatever_the_order_they_were_stored_in(
        self, arrange, me, owner
    ):
        def stage(db):
            parent = make_activity(
                db, owner.id, activity_type=activity_constants.ActivityType.MULTISPORT.stored, start_time=_START
            )
            late = make_activity(db, owner.id, parent_activity_id=parent.id, start_time=_START.replace(hour=11))
            early = make_activity(db, owner.id, parent_activity_id=parent.id, start_time=_START)
            return parent, early, late

        parent, early, late = arrange(stage)

        assert _ids(me.client.get(f"{_URL}/{parent.id}/legs")) == [str(early.id), str(late.id)]

    def test_a_page_holds_the_asked_window_and_the_total_counts_every_leg(self, me, group):
        parent, legs = group

        second = me.client.get(f"{_URL}/{parent.id}/legs", params={"page_number": 2, "num_records": 2})

        assert _ids(second) == [str(leg.id) for leg in legs[2:4]]
        assert second.json()["total"] == len(legs)

    def test_a_row_is_a_summary_without_private_notes_or_import_info(self, me, group):
        parent, _ = group

        item = me.client.get(f"{_URL}/{parent.id}/legs").json()["items"][0]

        assert "private_notes" not in item
        assert "import_info" not in item

    def test_an_activity_without_legs_is_an_empty_page(self, me, make_committed_activity, owner):
        single = make_committed_activity(owner)

        response = me.client.get(f"{_URL}/{single.id}/legs")

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    def test_a_missing_activity_is_an_empty_page_and_a_malformed_id_is_refused(self, me):
        missing = me.client.get(f"{_URL}/{_MISSING}/legs")

        assert (missing.status_code, missing.json()["items"], missing.json()["total"]) == (200, [], 0)
        assert me.client.get(f"{_URL}/not-a-uuid/legs").status_code == 422

    def test_the_route_needs_credentials(self, client, group):
        parent, _ = group

        assert client.get(f"{_URL}/{parent.id}/legs").status_code == 401


class TestAnotherUser:
    @pytest.fixture
    def viewer(self, sign_in, other):
        return sign_in(other)

    def test_a_public_group_is_served_with_the_hidden_fields_of_a_leg_masked(self, arrange, owner, viewer):
        parent, legs = arrange(
            lambda db: make_multisport(
                db, owner.id, start=_START, visibility=_Visibility.PUBLIC, hide_hr=True, average_hr=150
            )
        )

        response = viewer.client.get(f"{_URL}/{parent.id}/legs")

        assert response.status_code == 200
        assert _ids(response) == [str(leg.id) for leg in legs]
        assert {item["average_hr"] for item in response.json()["items"]} == {None}

    def test_the_owner_sees_the_same_field_unmasked(self, arrange, owner, me):
        parent, _ = arrange(
            lambda db: make_multisport(
                db, owner.id, start=_START, visibility=_Visibility.PUBLIC, hide_hr=True, average_hr=150
            )
        )

        items = me.client.get(f"{_URL}/{parent.id}/legs").json()["items"]

        assert {item["average_hr"] for item in items} == {150}

    def test_a_followers_group_is_served_to_an_accepted_follower_only(self, arrange, owner, other, viewer):
        parent, legs = arrange(lambda db: make_multisport(db, owner.id, start=_START, visibility=_Visibility.FOLLOWERS))

        refused = viewer.client.get(f"{_URL}/{parent.id}/legs")
        arrange(lambda db: make_follow(db, other.id, owner.id, accepted=True))
        served = viewer.client.get(f"{_URL}/{parent.id}/legs")

        assert (refused.status_code, refused.json()["items"], refused.json()["total"]) == (200, [], 0)
        assert _ids(served) == [str(leg.id) for leg in legs]

    @pytest.mark.parametrize("fields", [{"visibility": _Visibility.PRIVATE}, {"is_hidden": True}])
    def test_a_private_or_hidden_group_is_an_empty_page_exactly_like_one_that_does_not_exist(
        self, arrange, owner, viewer, fields
    ):
        parent, _ = arrange(
            lambda db: make_multisport(db, owner.id, start=_START, **{"visibility": _Visibility.PUBLIC, **fields})
        )

        hidden = viewer.client.get(f"{_URL}/{parent.id}/legs")
        missing = viewer.client.get(f"{_URL}/{_MISSING}/legs")

        assert (hidden.status_code, missing.status_code) == (200, 200)
        assert hidden.json() == missing.json()
        assert hidden.json()["total"] == 0


class TestPublic:
    def test_a_public_group_is_served_without_credentials_and_masked(self, arrange, client, links_shared, owner):
        parent, legs = arrange(
            lambda db: make_multisport(
                db, owner.id, start=_START, visibility=_Visibility.PUBLIC, hide_hr=True, average_hr=150
            )
        )

        response = client.get(f"{_PUBLIC_URL}/{parent.id}/legs", params={"num_records": 3})

        assert response.status_code == 200
        assert _ids(response) == [str(leg.id) for leg in legs[:3]]
        assert response.json()["total"] == len(legs)
        assert {item["average_hr"] for item in response.json()["items"]} == {None}

    def test_nothing_is_served_while_the_server_does_not_share_public_links(self, client, group):
        parent, _ = group

        response = client.get(f"{_PUBLIC_URL}/{parent.id}/legs")

        assert (response.status_code, response.json()["items"], response.json()["total"]) == (200, [], 0)

    @pytest.mark.parametrize(
        "fields",
        [{"visibility": _Visibility.FOLLOWERS}, {"visibility": _Visibility.PRIVATE}, {"is_hidden": True}],
    )
    def test_a_group_that_is_not_public_is_an_empty_page_exactly_like_one_that_does_not_exist(
        self, arrange, client, links_shared, owner, fields
    ):
        parent, _ = arrange(
            lambda db: make_multisport(db, owner.id, start=_START, **{"visibility": _Visibility.PUBLIC, **fields})
        )

        hidden = client.get(f"{_PUBLIC_URL}/{parent.id}/legs")
        missing = client.get(f"{_PUBLIC_URL}/{_MISSING}/legs")

        assert (hidden.status_code, missing.status_code) == (200, 200)
        assert hidden.json() == missing.json()
        assert hidden.json()["total"] == 0

    def test_a_public_activity_without_legs_is_an_empty_page(
        self, client, links_shared, owner, make_committed_activity
    ):
        single = make_committed_activity(owner, visibility=_Visibility.PUBLIC)

        response = client.get(f"{_PUBLIC_URL}/{single.id}/legs")

        assert response.status_code == 200
        assert response.json()["items"] == []
