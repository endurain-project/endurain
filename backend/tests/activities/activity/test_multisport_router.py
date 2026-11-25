"""A multisport activity and its legs through the activity routes, with real authentication and database."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

import core.config as core_config
import modules.activities.activity.models as activity_models
from tests._factories.activities import make_multisport

_URL = f"{core_config.ROOT_PATH}/activities"
_START = datetime(2026, 7, 28, 9, tzinfo=UTC)


@pytest.fixture
def group(arrange, owner):
    """A committed multisport activity of the owner with its five legs."""
    return arrange(lambda db: make_multisport(db, owner.id, start=_START))


def _patch(client, activity_id, body, version=1):
    return client.patch(f"{_URL}/{activity_id}", json=body, headers={"If-Match": f'"{version}"'})


class TestReads:
    def test_the_list_holds_the_parent_and_a_leg_is_read_by_id_naming_its_parent(self, me, group):
        parent, legs = group

        listed = me.client.get(_URL).json()
        leg = me.client.get(f"{_URL}/{legs[0].id}")

        assert [item["id"] for item in listed["items"]] == [str(parent.id)]
        assert listed["total"] == 1
        assert listed["items"][0]["parent_activity_id"] is None
        assert listed["items"][0]["activity_type"] == "multisport"
        assert leg.status_code == 200
        assert leg.json()["parent_activity_id"] == str(parent.id)

    def test_the_types_name_multisport_and_not_the_types_of_its_legs(self, me, group):
        assert me.client.get(f"{_URL}/types").json() == {"multisport": "Multisport"}


class TestEdit:
    def test_a_client_cannot_set_the_multisport_type_422(self, me, group, committed_sessions):
        _, legs = group

        response = _patch(me.client, legs[0].id, {"activity_type": "multisport"})

        assert response.status_code == 422

    def test_the_type_of_a_multisport_activity_cannot_be_edited_409(self, me, group):
        parent, _ = group

        response = _patch(me.client, parent.id, {"activity_type": "run"})

        assert response.status_code == 409

    def test_the_privacy_of_a_leg_cannot_be_edited_409(self, me, group):
        _, legs = group

        response = _patch(me.client, legs[0].id, {"hide_hr": True})

        assert response.status_code == 409

    def test_the_privacy_of_a_parent_reaches_its_legs(self, me, group, committed_sessions):
        parent, legs = group

        response = _patch(me.client, parent.id, {"visibility": "public"})

        assert response.status_code == 200
        with committed_sessions() as db:
            visibilities = db.scalars(
                select(activity_models.Activity.visibility).where(
                    activity_models.Activity.id.in_([leg.id for leg in legs])
                )
            ).all()
        assert visibilities == [0] * len(legs)


class TestDelete:
    def test_a_leg_is_deleted_with_its_parent_409(self, me, group):
        _, legs = group

        response = me.client.delete(f"{_URL}/{legs[0].id}", headers={"If-Match": '"1"'})

        assert response.status_code == 409

    def test_a_parent_goes_with_its_legs_and_a_204(self, me, group, committed_sessions):
        parent, legs = group

        response = me.client.delete(f"{_URL}/{parent.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 204
        with committed_sessions() as db:
            assert db.scalars(select(activity_models.Activity.id)).all() == []
            tombstoned = set(db.scalars(select(activity_models.ActivityDeletion.record_id)))
        assert tombstoned == {parent.id, *(leg.id for leg in legs)}
