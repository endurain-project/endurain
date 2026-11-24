"""The default gear routes: the user's own settings with their version, and edits."""

import pytest

import core.config as core_config
import modules.users.users_default_gear.crud as crud
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/profile/default-gear"


@pytest.fixture
def me(sign_in, committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return sign_in(user)


def _stored(committed_sessions, user_id):
    with committed_sessions() as db:
        return crud.get_user_default_gear_by_user_id(user_id, db)


class TestRead:
    def test_the_settings_come_with_their_version_as_an_etag(self, me):
        response = me.client.get(_URL)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.json()["user_id"] == str(me.user.id)
        assert response.json()["run_gear_id"] is None


class TestEdit:
    def test_a_gear_is_assigned_and_the_new_version_is_returned(self, me, committed_sessions):
        with committed_sessions() as db:
            gear = make_gear(db, me.user.id)
            db.commit()

        response = me.client.patch(_URL, json={"run_gear_id": str(gear.id)}, headers={"If-Match": '"1"'})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert response.json()["run_gear_id"] == str(gear.id)
        stored = _stored(committed_sessions, me.user.id)
        assert stored is not None
        assert stored.run_gear_id == gear.id

    def test_a_gear_of_another_user_is_not_found_and_nothing_changes(self, me, committed_sessions):
        with committed_sessions() as db:
            stranger = make_user(db)
            foreign = make_gear(db, stranger.id)
            db.commit()

        response = me.client.patch(_URL, json={"run_gear_id": str(foreign.id)}, headers={"If-Match": '"1"'})

        assert response.status_code == 404
        stored = _stored(committed_sessions, me.user.id)
        assert stored is not None
        assert (stored.run_gear_id, stored.version) == (None, 1)

    def test_a_stale_version_is_refused(self, me, committed_sessions):
        response = me.client.patch(_URL, json={}, headers={"If-Match": '"5"'})

        assert response.status_code == 412
