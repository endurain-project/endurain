"""Which users have linked a provider, paged for the scheduled refresh fan-out.

Run against a real database: the Garmin token is a JSON column, and unlinking
stores a JSON ``null`` rather than SQL ``NULL``, which a mocked session cannot show.
"""

import uuid

import pytest

import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_integrations.models as integrations_models
from tests._helpers.db import create_sqlite_session


def _uid(number: int) -> uuid.UUID:
    """Return a user id that sorts by ``number``."""
    return uuid.UUID(f"00000000-0000-4000-8000-{number:012x}")


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()


def _link(db, user_id: uuid.UUID, *, strava: bool = False, garmin: dict | None = None) -> None:
    db.add(
        integrations_models.UsersIntegrations(
            user_id=user_id,
            strava_token="token" if strava else None,
            garminconnect_token=garmin,
        )
    )
    db.commit()


class TestStravaLinkedUsers:
    def test_lists_only_users_with_a_token_in_id_order(self, db):
        _link(db, _uid(1), strava=True)
        _link(db, _uid(2))
        _link(db, _uid(3), strava=True)

        assert integrations_integration.list_user_ids_with_strava_linked(None, 10, db) == [_uid(1), _uid(3)]

    def test_pages_by_cursor(self, db):
        for number in (1, 2, 3):
            _link(db, _uid(number), strava=True)

        assert integrations_integration.list_user_ids_with_strava_linked(_uid(1), 1, db) == [_uid(2)]
        assert integrations_integration.list_user_ids_with_strava_linked(_uid(2), 5, db) == [_uid(3)]


class TestGarminLinkedUsers:
    def test_an_unlinked_account_stored_as_json_null_is_not_listed(self, db):
        """Unlinking assigns None, which a JSON column persists as JSON ``null``, not SQL NULL."""
        _link(db, _uid(1), garmin={"di_token": "x"})
        _link(db, _uid(2), garmin={"di_token": "y"})
        integration = db.query(integrations_models.UsersIntegrations).filter_by(user_id=_uid(2)).one()
        integration.garminconnect_token = None
        db.commit()

        assert integrations_integration.list_user_ids_with_garminconnect_linked(None, 10, db) == [_uid(1)]

    def test_a_page_of_unlinked_users_does_not_end_the_listing(self, db):
        """The caller stops on an empty page, so a run of unlinked users must not return one."""
        for number in range(1, 6):
            _link(db, _uid(number))
        _link(db, _uid(6), garmin={"di_token": "z"})

        assert integrations_integration.list_user_ids_with_garminconnect_linked(None, 2, db) == [_uid(6)]

    def test_a_full_page_is_cut_at_the_limit_and_resumes_after_its_last_id(self, db):
        for number in (1, 2, 3):
            _link(db, _uid(number), garmin={"di_token": "t"})

        first = integrations_integration.list_user_ids_with_garminconnect_linked(None, 2, db)
        second = integrations_integration.list_user_ids_with_garminconnect_linked(first[-1], 2, db)

        assert (first, second) == ([_uid(1), _uid(2)], [_uid(3)])
