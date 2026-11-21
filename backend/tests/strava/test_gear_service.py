"""Strava gear: the sync of the athlete's gear from the fake Strava, and the import of a Strava export's gear CSVs."""

import contextlib
import io
import os
from datetime import timedelta
from functools import partial

import jasil.audit.models as audit_models
import pytest
from fastapi import UploadFile
from sqlalchemy import select

import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import modules.activities.activity.models as activity_models
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.gear_service as strava_gear_service
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.activities import DEFAULT_START, make_activity
from tests._factories.gears import gear_payload
from tests._factories.users import make_user

BIKE = gears_schema.GearType.BIKE
SHOES = gears_schema.GearType.SHOES
_GEAR_IMPORT = strava_audit_actions.GEAR_IMPORT.id


def _linked(db, **link):
    user = make_user(db)
    strava_factories.link_strava(db, user.id, **link)
    db.flush()
    return user


def _gear_of(user_id):
    with core_database.SessionLocal() as db:
        return gears_integration.get_gear_user(user_id, db)


def _integrations(user_id):
    with core_database.SessionLocal() as db:
        return user_integrations_integration.require_user_integrations(user_id, db)


def _csv_saver(content: bytes, seen: list[str] | None = None):
    """Build the saver the route binds: it streams an upload through the shared writer, noting where it landed."""
    upload = UploadFile(filename="whatever.csv", file=io.BytesIO(content))
    save = partial(core_file_uploads.save_text_upload_sync, upload, max_bytes=strava_constants.GEAR_CSV_MAX_BYTES)

    def saver(*, upload_dir: str, filename: str) -> str:
        path = save(upload_dir=upload_dir, filename=filename)
        if seen is not None:
            seen.append(path)
        return path

    return saver


def _bikes(*rows: str) -> bytes:
    return ("Bike Name,Bike Brand,Bike Model\n" + "".join(f"{row}\n" for row in rows)).encode()


def _shoes(*rows: str) -> bytes:
    return ("Shoe Name,Shoe Brand,Shoe Model\n" + "".join(f"{row}\n" for row in rows)).encode()


class TestGetUserGear:
    def test_new_gear_is_created_with_the_sync_preference_and_matched_to_existing_activities(
        self, db, strava, rate_limits
    ):
        user = _linked(db)
        activity = make_activity(db, user.id, strava_gear_id="b1")
        other_activity = make_activity(
            db, user.id, strava_gear_id="elsewhere", start_time=activity.start_time.replace(hour=12)
        )
        ungeared = make_activity(db, user.id, start_time=activity.start_time.replace(hour=15))
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"], shoes=["s1"])))
        strava.on("GET", "/gear/b1", strava_factories.ok(strava_factories.gear_payload("b1")))
        strava.on(
            "GET",
            "/gear/s1",
            strava_factories.ok(
                strava_factories.gear_payload("s1", name="Pegasus", brand_name="Nike", model_name="Peg 40")
            ),
        )

        assert strava_gear_service.get_user_gear(user.id, rate_limits) is True

        gear = {g.strava_gear_id: g for g in _gear_of(user.id)}
        assert (gear["b1"].nickname, gear["b1"].brand, gear["b1"].gear_type) == ("Road bike", "Canyon", BIKE)
        assert (gear["s1"].nickname, gear["s1"].model, gear["s1"].gear_type, gear["s1"].active) == (
            "Pegasus",
            "Peg 40",
            SHOES,
            True,
        )
        assert _integrations(user.id).strava_sync_gear is True
        with core_database.SessionLocal() as session:
            assigned = {
                row.id: row.gear_id
                for row in session.scalars(
                    select(activity_models.Activity).where(activity_models.Activity.user_id == user.id)
                )
            }
        assert assigned == {activity.id: gear["b1"].id, other_activity.id: None, ungeared.id: None}

    def test_gear_the_user_already_has_is_not_fetched_again(self, db, strava, rate_limits):
        user = _linked(db)
        gears_integration.create_multiple_gears(
            [gear_payload("Mine", user_id=user.id, strava_gear_id="b1")], user.id, db
        )
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"])))

        assert strava_gear_service.get_user_gear(user.id, rate_limits) is True

        assert strava.made("GET", "/gear/b1") == []
        assert [g.nickname for g in _gear_of(user.id)] == ["Mine"]

    def test_an_athlete_without_gear_still_turns_the_preference_on(self, db, strava, rate_limits):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload()))

        assert strava_gear_service.get_user_gear(user.id, rate_limits) is True

        assert (_gear_of(user.id), _integrations(user.id).strava_sync_gear) == ([], True)

    def test_a_user_who_is_not_linked_is_reported_not_crashed(self, db, strava, rate_limits):
        user = make_user(db)

        assert strava_gear_service.get_user_gear(user.id, rate_limits) is False
        assert strava.calls == []

    def test_a_long_history_is_matched_page_by_page(self, db, strava, rate_limits):
        user = _linked(db)
        count = strava_gear_service._ACTIVITY_PAGE_SIZE + 1
        for minute in range(count):
            make_activity(
                db,
                user.id,
                strava_gear_id="b1",
                start_time=DEFAULT_START + timedelta(minutes=minute),
                end_time=DEFAULT_START + timedelta(minutes=minute, hours=1),
            )
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"])))
        strava.on("GET", "/gear/b1", strava_factories.ok(strava_factories.gear_payload("b1")))

        strava_gear_service.get_user_gear(user.id, rate_limits)

        with core_database.SessionLocal() as session:
            gear_ids = session.scalars(
                select(activity_models.Activity.gear_id).where(
                    activity_models.Activity.user_id == user.id, activity_models.Activity.strava_gear_id == "b1"
                )
            ).all()
        assert len(gear_ids) == count
        assert None not in gear_ids

    def test_a_failed_gear_fetch_stores_nothing_and_leaves_the_preference_off(self, db, strava, rate_limits):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1", "b2"])))
        strava.on("GET", "/gear/b1", strava_factories.ok(strava_factories.gear_payload("b1")))
        strava.on("GET", "/gear/b2", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_gear_service.get_user_gear(user.id, rate_limits)

        assert (_gear_of(user.id), _integrations(user.id).strava_sync_gear) == ([], False)

    def test_a_failed_athlete_fetch_is_a_failed_dependency(self, db, strava, rate_limits):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_gear_service.get_user_gear(user.id, rate_limits)

    def test_a_gear_piece_strava_lists_without_an_id_fails_the_sync_and_stores_nothing(self, db, strava, rate_limits):
        user = _linked(db)
        athlete = strava_factories.athlete_payload()
        athlete["bikes"] = [{"name": "no id", "primary": False, "distance": 0}]
        strava.on("GET", "/athlete", strava_factories.ok(athlete))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_gear_service.get_user_gear(user.id, rate_limits)

        assert _gear_of(user.id) == []

    def test_a_gear_piece_strava_returns_without_a_name_fails_the_sync_and_stores_nothing(
        self, db, strava, rate_limits
    ):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"])))
        strava.on("GET", "/gear/b1", strava_factories.ok(strava_factories.gear_payload("b1", name=None)))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_gear_service.get_user_gear(user.id, rate_limits)

        assert (_gear_of(user.id), _integrations(user.id).strava_sync_gear) == ([], False)

    def test_a_token_strava_rejects_unlinks_the_account_and_stores_nothing(self, db, strava, rate_limits):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.refused(401))
        strava.on("POST", "/oauth/token", strava_factories.refused(400, resource="RefreshToken"))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            strava_gear_service.get_user_gear(user.id, rate_limits)

        stored = _integrations(user.id)
        assert (stored.strava_token, stored.strava_revoked_at is not None, _gear_of(user.id)) == (None, True, [])

    def test_an_active_rate_limit_stops_the_sync_before_strava_is_called(self, db, strava, rate_limits):
        user = _linked(db)
        until = rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_gear_service.get_user_gear(user.id, rate_limits)

        assert raised.value.retry_at == until
        assert strava.calls == []

    def test_a_429_marks_the_limit_and_refuses_with_when_it_clears(self, db, strava, rate_limits):
        user = _linked(db)
        strava.on("GET", "/athlete", strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_gear_service.get_user_gear(user.id, rate_limits)

        assert raised.value.retry_at == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)

    def test_strava_is_called_with_no_database_session_open(self, committed_sessions, strava, rate_limits):
        with committed_sessions() as db:
            user = _linked(db)
            db.commit()
        open_connections = []

        def watching(reply):
            def answer(_call):
                open_connections.append(core_database.engine.pool.checkedout())
                return reply

            return answer

        strava.on("GET", "/athlete", watching(strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"]))))
        strava.on("GET", "/gear/b1", watching(strava_factories.ok(strava_factories.gear_payload("b1"))))

        strava_gear_service.get_user_gear(user.id, rate_limits)

        assert open_connections == [0, 0]


class TestImportBikes:
    @pytest.fixture
    def user(self, db):
        return make_user(db)

    def test_the_listed_bikes_are_created_for_the_caller_and_audited_with_type_and_count(self, user, db):
        count = strava_gear_service.import_gear(
            _csv_saver(_bikes("Commuter,Trek,Domane", "Gravel,Canyon,Grail")), user.id, BIKE, db
        )

        assert count == 2
        assert sorted((g.nickname, g.brand, g.model, g.gear_type) for g in _gear_of(user.id)) == [
            ("Commuter", "Trek", "Domane", BIKE),
            ("Gravel", "Canyon", "Grail", BIKE),
        ]
        (row,) = db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == _GEAR_IMPORT)).all()
        assert (row.actor_id, row.target_owner_id, row.details) == (
            None,
            str(user.id),
            {"gear_type": "bikes", "count": 2},
        )

    def test_names_are_stripped_blank_brands_are_none_and_the_last_of_two_rows_with_one_name_wins(self, user, db):
        strava_gear_service.import_gear(
            _csv_saver(_bikes(" Road , Giant ,  Defy ", "Road,Trek,", "MTB,,", "  ,Giant,Anthem")), user.id, BIKE, db
        )

        assert sorted((g.nickname, g.brand, g.model) for g in _gear_of(user.id)) == [
            ("MTB", None, None),
            ("Road", "Trek", None),
        ]

    def test_a_file_listing_no_gear_creates_and_audits_nothing(self, user, db):
        count = strava_gear_service.import_gear(_csv_saver(_bikes()), user.id, BIKE, db)

        assert count == 0
        assert _gear_of(user.id) == []
        assert (
            db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == _GEAR_IMPORT)).all() == []
        )

    @pytest.mark.parametrize("content", [b"Name,Brand\nCommuter,Trek\n", _shoes("Pegasus,Nike,Peg")])
    def test_a_file_without_the_bike_columns_is_refused_and_not_audited(self, user, db, content):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_gear_service.import_gear(_csv_saver(content), user.id, BIKE, db)

        assert _gear_of(user.id) == []
        assert (
            db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == _GEAR_IMPORT)).all() == []
        )

    def test_a_file_that_is_not_text_is_refused_as_bad_input(self, user, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_gear_service.import_gear(
                _csv_saver(b"Bike Name,Bike Brand,Bike Model\n\xff\xfe\x00\x81\n"), user.id, BIKE, db
            )

    def test_an_oversized_upload_is_refused(self, user, db):
        big = _bikes() + b"x," * strava_constants.GEAR_CSV_MAX_BYTES

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            strava_gear_service.import_gear(_csv_saver(big), user.id, BIKE, db)

    @pytest.mark.parametrize("content", [_bikes("Commuter,Trek,Domane"), b"not a csv"])
    def test_the_temporary_file_is_removed_whether_or_not_the_file_is_accepted(self, user, db, content):
        seen: list[str] = []

        with contextlib.suppress(core_exceptions.InvalidInputError):
            strava_gear_service.import_gear(_csv_saver(content, seen), user.id, BIKE, db)

        assert len(seen) == 1
        assert not os.path.exists(seen[0])


class TestImportShoes:
    @pytest.fixture
    def user(self, db):
        return make_user(db)

    def test_the_listed_shoes_are_created_and_audited_as_shoes(self, user, db):
        count = strava_gear_service.import_gear(_csv_saver(_shoes(" Pegasus ,Nike, Peg 40 ")), user.id, SHOES, db)

        assert count == 1
        (shoe,) = _gear_of(user.id)
        assert (shoe.nickname, shoe.brand, shoe.model, shoe.gear_type) == ("Pegasus", "Nike", "Peg 40", SHOES)
        (row,) = db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == _GEAR_IMPORT)).all()
        assert row.details == {"gear_type": "shoes", "count": 1}

    def test_a_trailing_plus_in_a_shoe_name_is_kept(self, user, db):
        strava_gear_service.import_gear(_csv_saver(_shoes("Pegasus+ ,Nike,Peg")), user.id, SHOES, db)

        assert [g.nickname for g in _gear_of(user.id)] == ["Pegasus+"]

    @pytest.mark.parametrize("blank", ["", "  ", "+", "+ +"])
    def test_a_nameless_shoe_gets_the_default_name(self, user, db, blank):
        strava_gear_service.import_gear(_csv_saver(_shoes(f'"{blank}",Nike,Peg')), user.id, SHOES, db)

        assert [(g.nickname, g.brand) for g in _gear_of(user.id)] == [("Unnamed Shoe 1", "Nike")]

    def test_nameless_shoes_avoid_the_gear_the_user_has_and_each_other(self, user, db):
        gears_integration.create_multiple_gears([gear_payload("Unnamed Shoe 1", user_id=user.id)], user.id, db)

        strava_gear_service.import_gear(_csv_saver(_shoes(",,", ",,", "Speed,,")), user.id, SHOES, db)

        assert sorted(g.nickname for g in _gear_of(user.id)) == [
            "Speed",
            "Unnamed Shoe 1",
            "Unnamed Shoe 2",
            "Unnamed Shoe 3",
        ]
