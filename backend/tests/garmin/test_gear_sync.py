"""The Garmin Connect gear sync on the real database: the gear stored and the activities it is assigned to."""

import garminconnect
import pytest
from sqlalchemy import select

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.garmin.gear_service as garmin_gear_service
import modules.gears.gear.models as gear_models
import modules.users.users_integrations.models as user_integrations_models
from tests._factories import garmin as garmin_factories
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear
from tests.garmin.conftest import notifications_of, stored_token


def _gears(sessions, user):
    with sessions() as db:
        return list(
            db.scalars(
                select(gear_models.Gear)
                .where(gear_models.Gear.user_id == user.id, gear_models.Gear.garminconnect_gear_id.is_not(None))
                .order_by(gear_models.Gear.garminconnect_gear_id)
            )
        )


def _sync_gear_is_on(sessions, user) -> bool:
    with sessions() as db:
        return db.scalars(
            select(user_integrations_models.UsersIntegrations.garminconnect_sync_gear).where(
                user_integrations_models.UsersIntegrations.user_id == user.id
            )
        ).one()


class TestGearSync:
    def test_the_gear_is_stored_and_gear_sync_turns_on(self, account, linked, rate_limits, committed_sessions):
        account.gear = [
            garmin_factories.gear_payload("g-shoes"),
            garmin_factories.gear_payload(
                "g-bike", gearTypeName="Bike", gearMakeName="Canyon", gearModelName="Grail", displayName="Gravel"
            ),
            garmin_factories.gear_payload("g-old", gearStatusName="retired", displayName="Old shoes"),
        ]

        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is True

        bike, old, shoes = _gears(committed_sessions, linked)
        assert (bike.nickname, bike.brand, bike.model, bike.active) == ("Gravel", "Canyon", "Grail", True)
        assert (shoes.nickname, shoes.brand, shoes.model, shoes.active) == ("Road shoes", "Nike", "Pegasus", True)
        assert old.active is False
        assert bike.gear_type != shoes.gear_type
        assert _sync_gear_is_on(committed_sessions, linked) is True
        assert account.called("get_gear") == [(42,)]

    def test_a_piece_without_a_display_name_is_named_after_its_custom_make_and_model(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.gear = [garmin_factories.gear_payload("g-1", displayName="", customMakeModel="Home built")]

        garmin_gear_service.get_user_gear(linked.id, rate_limits)

        assert [gear.nickname for gear in _gears(committed_sessions, linked)] == ["Home built"]

    def test_a_piece_without_a_make_or_model_stores_none(self, account, linked, rate_limits, committed_sessions):
        account.gear = [garmin_factories.gear_payload("g-1", gearMakeName="", gearModelName=None)]

        garmin_gear_service.get_user_gear(linked.id, rate_limits)

        [gear] = _gears(committed_sessions, linked)
        assert (gear.brand, gear.model) == (None, None)

    def test_gear_already_stored_is_not_stored_twice_and_a_hand_made_gear_is_kept(
        self, account, linked, rate_limits, committed_sessions
    ):
        with committed_sessions() as db:
            make_gear(db, linked.id, nickname="By hand")
            db.commit()
        account.gear = [garmin_factories.gear_payload("g-1")]
        garmin_gear_service.get_user_gear(linked.id, rate_limits)
        account.gear = [
            garmin_factories.gear_payload("g-1"),
            garmin_factories.gear_payload("g-2", displayName="Trail shoes"),
        ]

        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is True

        assert [gear.garminconnect_gear_id for gear in _gears(committed_sessions, linked)] == ["g-1", "g-2"]
        with committed_sessions() as db:
            nicknames = set(db.scalars(select(gear_models.Gear.nickname).where(gear_models.Gear.user_id == linked.id)))
        assert "By hand" in nicknames

    def test_another_users_gear_with_the_same_garmin_id_does_not_count_as_stored(
        self, account, linked, make_linked, rate_limits, committed_sessions
    ):
        account.gear = [garmin_factories.gear_payload("g-1")]
        other = make_linked()
        garmin_gear_service.get_user_gear(other.id, rate_limits)

        garmin_gear_service.get_user_gear(linked.id, rate_limits)

        assert len(_gears(committed_sessions, linked)) == 1

    def test_an_unlinked_user_is_not_synced_and_gear_sync_stays_off(
        self, account, unlinked, rate_limits, committed_sessions
    ):
        assert garmin_gear_service.get_user_gear(unlinked.id, rate_limits) is False

        assert _sync_gear_is_on(committed_sessions, unlinked) is False
        assert account.calls == []

    def test_gear_sync_stays_off_when_the_account_was_unlinked_while_the_gear_was_fetched(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.gear = [garmin_factories.gear_payload("g-1")]

        def unlink_meanwhile(method):
            if method == "get_gear":
                with committed_sessions() as db:
                    row = db.scalars(
                        select(user_integrations_models.UsersIntegrations).where(
                            user_integrations_models.UsersIntegrations.user_id == linked.id
                        )
                    ).one()
                    row.garminconnect_token = None
                    db.commit()

        account.on_call = unlink_meanwhile

        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is False

        assert _sync_gear_is_on(committed_sessions, linked) is False

    def test_a_gear_answer_that_is_not_a_list_is_a_garmin_failure_and_gear_sync_stays_off(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.gear = {"uuid": "a"}

        with pytest.raises(core_exceptions.DependencyFailedError):
            garmin_gear_service.get_user_gear(linked.id, rate_limits)

        assert _sync_gear_is_on(committed_sessions, linked) is False

    def test_garmin_is_called_with_no_database_connection_checked_out(self, account, linked, rate_limits):
        account.gear = [garmin_factories.gear_payload("g-1")]
        checked_out: list[tuple[str, int]] = []
        account.on_call = lambda method: checked_out.append((method, core_database.engine.pool.checkedout()))

        garmin_gear_service.get_user_gear(linked.id, rate_limits)

        assert {method for method, _ in checked_out} == {"get_device_last_used", "get_gear"}
        assert {count for _, count in checked_out} == {0}


class TestRejectedToken:
    def test_an_expired_token_unlinks_the_account_and_leaves_gear_sync_off(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.fail("get_device_last_used", garminconnect.GarminConnectAuthenticationError("401"))

        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is False

        assert stored_token(committed_sessions, linked.id) is None
        assert _sync_gear_is_on(committed_sessions, linked) is False
        assert len(notifications_of(committed_sessions, linked.id)) == 1


class TestGearOfActivities:
    def test_activities_carrying_a_garmin_gear_id_get_the_matching_local_gear(
        self, account, linked, rate_limits, committed_sessions
    ):
        with committed_sessions() as db:
            matched = make_activity(db, linked.id, garminconnect_gear_id="g-1")
            unmatched = make_activity(db, linked.id, garminconnect_gear_id="g-other", start_time=matched.start_time)
            plain = make_activity(db, linked.id)
            db.commit()
        account.gear = [garmin_factories.gear_payload("g-1")]

        garmin_gear_service.get_user_gear(linked.id, rate_limits)

        [gear] = _gears(committed_sessions, linked)
        with committed_sessions() as db:
            assigned = dict(db.execute(select(activity_models.Activity.id, activity_models.Activity.gear_id)).all())
        assert assigned[matched.id] == gear.id
        assert assigned[unmatched.id] is None
        assert assigned[plain.id] is None

    def test_an_activity_whose_gear_is_not_stored_stays_without_gear(
        self, account, linked, rate_limits, committed_sessions
    ):
        with committed_sessions() as db:
            activity = make_activity(db, linked.id, garminconnect_gear_id="g-other")
            db.commit()
        account.gear = [garmin_factories.gear_payload("g-1")]

        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is True

        with committed_sessions() as db:
            assert db.get(activity_models.Activity, activity.id).gear_id is None


class TestGearList:
    def test_a_gear_answer_is_the_list_garmin_sent(self):
        assert garmin_gear_service.gear_list([{"uuid": "a"}]) == [{"uuid": "a"}]

    def test_a_gear_answer_that_is_not_a_list_is_a_garmin_failure(self):
        with pytest.raises(core_exceptions.DependencyFailedError):
            garmin_gear_service.gear_list({"uuid": "a"})
