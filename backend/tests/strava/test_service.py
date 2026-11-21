"""Unlinking Strava and deleting what it imported, and the work that deletes a revoked account's data."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.gears.gear.integration_service as gears_integration
import modules.notifications.constants as notifications_constants
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.constants as strava_constants
import modules.strava.service as strava_service
import modules.users.users_integrations.constants as user_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.activities import DEFAULT_START, make_activity
from tests._factories.gears import gear_payload
from tests._factories.users import make_user

_DATA_DELETED = notifications_constants.NotificationType.STRAVA_DATA_DELETED.stored
_GRACE = timedelta(days=user_integrations_constants.STRAVA_REVOKED_DATA_GRACE_DAYS)


def _linked(db, **link):
    user = make_user(db)
    strava_factories.link_strava(db, user.id, **link)
    db.flush()
    return user


def _integrations(user_id):
    with core_database.SessionLocal() as db:
        return user_integrations_integration.require_user_integrations(user_id, db)


def _activity_ids(user_id) -> set[uuid.UUID]:
    with core_database.SessionLocal() as db:
        return set(db.scalars(select(activity_models.Activity.id).where(activity_models.Activity.user_id == user_id)))


def _gear_names(user_id) -> set[str]:
    with core_database.SessionLocal() as db:
        return {gear.nickname for gear in gears_integration.get_gear_user(user_id, db)}


def _with_imported_data(db, user):
    """Give a user two activities and a gear imported from Strava, and one of each of their own."""
    imported = make_activity(db, user.id, strava_activity_id=1001)
    own = make_activity(
        db, user.id, start_time=DEFAULT_START + timedelta(days=1), end_time=DEFAULT_START + timedelta(days=1, hours=1)
    )
    gears_integration.create_multiple_gears(
        [gear_payload("From Strava", user_id=user.id, strava_gear_id="b1"), gear_payload("Mine", user_id=user.id)],
        user.id,
        db,
    )
    return imported, own


class TestUnlinkAccount:
    def test_strava_is_deauthorized_and_the_account_unlinked_with_what_was_imported_deleted(
        self, db, strava, rate_limits
    ):
        user = _linked(db, sync_gear=True)
        _imported, own = _with_imported_data(db, user)
        strava.on("POST", "/oauth/deauthorize", strava_factories.ok({}))

        assert strava_service.unlink_account(user.id, rate_limits) is True

        (call,) = strava.made("POST", "/oauth/deauthorize")
        assert call.headers["Authorization"] == f"Bearer {strava_factories.ACCESS_TOKEN}"
        stored = _integrations(user.id)
        assert (stored.strava_token, stored.strava_client_id, stored.strava_sync_gear) == (None, None, False)
        assert _activity_ids(user.id) == {own.id}
        assert _gear_names(user.id) == {"Mine"}

    def test_a_refused_deauthorization_still_unlinks_and_clears_what_was_imported(self, db, strava, rate_limits):
        user = _linked(db)
        _imported, own = _with_imported_data(db, user)
        strava.on("POST", "/oauth/deauthorize", strava_factories.refused(500))

        assert strava_service.unlink_account(user.id, rate_limits) is True

        assert _integrations(user.id).strava_token is None
        assert _activity_ids(user.id) == {own.id}

    def test_an_expired_token_is_refreshed_before_deauthorizing_with_the_new_token(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        strava.on("POST", "/oauth/token", strava_factories.ok(strava_factories.token_payload("fresh", "fresh-refresh")))
        strava.on("POST", "/oauth/deauthorize", strava_factories.ok({}))

        strava_service.unlink_account(user.id, rate_limits)

        (call,) = strava.made("POST", "/oauth/deauthorize")
        assert call.headers["Authorization"] == "Bearer fresh"

    def test_a_grant_strava_already_revoked_has_nothing_to_deauthorize_but_still_unlinks_locally(
        self, db, strava, rate_limits
    ):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        _imported, own = _with_imported_data(db, user)
        strava.on("POST", "/oauth/token", strava_factories.refused(400, resource="RefreshToken"))

        assert strava_service.unlink_account(user.id, rate_limits) is True

        assert strava.made("POST", "/oauth/deauthorize") == []
        assert _integrations(user.id).strava_revoked_at is None, "an unlink clears the revocation mark"
        assert _activity_ids(user.id) == {own.id}

    def test_a_refresh_that_fails_otherwise_still_unlinks_locally(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        strava.on("POST", "/oauth/token", strava_factories.refused(500))

        assert strava_service.unlink_account(user.id, rate_limits) is True

        assert strava.made("POST", "/oauth/deauthorize") == []
        assert _integrations(user.id).strava_token is None

    def test_a_rate_limited_refresh_leaves_the_account_linked_so_a_later_attempt_can_still_revoke_it(
        self, db, strava, rate_limits
    ):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        imported, own = _with_imported_data(db, user)
        strava.on("POST", "/oauth/token", strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_service.unlink_account(user.id, rate_limits)

        assert raised.value.retry_at == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)
        assert _integrations(user.id).strava_token is not None
        assert _activity_ids(user.id) == {imported.id, own.id}
        assert _gear_names(user.id) == {"From Strava", "Mine"}

    def test_an_account_that_is_not_linked_is_left_alone(self, db, strava, rate_limits):
        user = make_user(db)
        _, _own = _with_imported_data(db, user)

        assert strava_service.unlink_account(user.id, rate_limits) is False

        assert strava.calls == []
        assert len(_activity_ids(user.id)) == 2

    def test_a_user_without_integrations_is_not_found(self, db, rate_limits):
        with pytest.raises(core_exceptions.NotFoundError):
            strava_service.unlink_account(uuid.uuid4(), rate_limits)

    def test_strava_is_called_with_no_database_session_open(self, committed_sessions, strava, rate_limits):
        with committed_sessions() as db:
            user = _linked(db)
            db.commit()
        open_connections = []

        def answer(_call):
            open_connections.append(core_database.engine.pool.checkedout())
            return strava_factories.ok({})

        strava.on("POST", "/oauth/deauthorize", answer)

        strava_service.unlink_account(user.id, rate_limits)

        assert open_connections == [0]

    def test_more_activities_than_one_batch_are_all_deleted_and_the_unlink_still_completes(
        self, committed_sessions, strava, rate_limits
    ):
        with committed_sessions() as db:
            user = _linked(db)
            for index in range(strava_constants.UNLINK_DELETE_BATCH_SIZE + 1):
                moment = DEFAULT_START + timedelta(minutes=index)
                make_activity(
                    db,
                    user.id,
                    strava_activity_id=index + 1,
                    start_time=moment,
                    end_time=moment + timedelta(hours=1),
                )
            db.commit()
        strava.on("POST", "/oauth/deauthorize", strava_factories.ok({}))

        strava_service.unlink_account(user.id, rate_limits)

        assert _activity_ids(user.id) == set()
        assert _integrations(user.id).strava_token is None


class TestDeleteRevokedData:
    def _revoked(self, db, ago):
        user = _linked(db, sync_gear=True)
        strava_factories.revoke_strava_access(db, user.id, revoked_ago=ago)
        return user

    def test_data_of_a_user_revoked_past_the_grace_period_is_deleted_audited_and_the_user_told(self, db):
        user = self._revoked(db, _GRACE + timedelta(hours=1))
        _imported, own = _with_imported_data(db, user)

        assert strava_service.delete_revoked_data(user.id) is True

        stored = _integrations(user.id)
        assert (stored.strava_revoked_at, stored.strava_client_id) == (
            None,
            strava_factories.CLIENT_ID and stored.strava_client_id,
        )
        assert stored.strava_client_id is not None, "the client id and secret stay"
        assert _activity_ids(user.id) == {own.id}
        assert _gear_names(user.id) == {"Mine"}
        assert len(strava_factories.notifications_of(db, user.id, _DATA_DELETED)) == 1
        (row,) = strava_factories.audit_rows(db, strava_audit_actions.DATA_DELETE.id)
        assert (row.target_owner_id, row.details) == (str(user.id), {"activity_count": 1})

    def test_a_user_still_inside_the_grace_period_is_left_alone(self, db):
        user = self._revoked(db, _GRACE - timedelta(hours=1))
        imported, own = _with_imported_data(db, user)

        assert strava_service.delete_revoked_data(user.id) is False

        assert _activity_ids(user.id) == {imported.id, own.id}
        assert _integrations(user.id).strava_revoked_at is not None
        assert strava_factories.notifications_of(db, user.id, _DATA_DELETED) == []

    def test_a_user_who_relinked_is_left_alone(self, db):
        user = self._revoked(db, _GRACE + timedelta(days=1))
        imported, own = _with_imported_data(db, user)
        user_integrations_integration.link_strava_account(user.id, strava_factories.token_payload("a", "b"), db)

        assert strava_service.delete_revoked_data(user.id) is False

        assert _activity_ids(user.id) == {imported.id, own.id}

    def test_a_user_who_never_revoked_is_left_alone(self, db):
        user = _linked(db)
        imported, own = _with_imported_data(db, user)

        assert strava_service.delete_revoked_data(user.id) is False

        assert _activity_ids(user.id) == {imported.id, own.id}

    def test_a_user_without_integrations_is_left_alone(self, db):
        assert strava_service.delete_revoked_data(uuid.uuid4()) is False


class TestListingUsers:
    def test_linked_users_are_listed_ascending_a_page_after_the_given_id(self, db):
        linked = sorted([_linked(db).id for _ in range(3)])
        make_user(db)

        everyone = strava_service.linked_user_ids(None, 100)
        page = strava_service.linked_user_ids(linked[0], 1)

        assert [user_id for user_id in everyone if user_id in linked] == linked
        assert page == [next(user_id for user_id in everyone if user_id > linked[0])]

    def test_users_revoked_past_the_grace_period_are_listed(self, db):
        due = _linked(db)
        strava_factories.revoke_strava_access(db, due.id, revoked_ago=_GRACE + timedelta(days=1))
        recent = _linked(db)
        strava_factories.revoke_strava_access(db, recent.id, revoked_ago=timedelta(days=1))

        listed = strava_service.revoked_user_ids_due(None, 100)

        assert due.id in listed
        assert recent.id not in listed
