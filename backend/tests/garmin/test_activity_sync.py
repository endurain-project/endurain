"""The Garmin Connect activity sync on the real database: the window, the downloads and what ingestion stores."""

import tempfile
from datetime import UTC, datetime

import garminconnect
import pytest
from sqlalchemy import select

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.garmin.activity_service as garmin_activity_service
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.gear_service as garmin_gear_service
import modules.gears.gear.models as gear_models
from tests._factories import garmin as garmin_factories
from tests._factories.tokens import audit_rows
from tests.garmin.conftest import notifications_of, stored_access_token, stored_token

_START = datetime(2026, 1, 14, tzinfo=UTC)
_END = datetime(2026, 1, 16, tzinfo=UTC)


def _sync(user, rate_limits):
    return garmin_activity_service.get_user_garminconnect_activities_by_dates(user.id, _START, _END, rate_limits)


def _activities(sessions, user):
    with sessions() as db:
        return list(
            db.scalars(
                select(activity_models.Activity)
                .where(activity_models.Activity.user_id == user.id)
                .order_by(activity_models.Activity.garminconnect_activity_id)
            )
        )


class TestStoringTheWindow:
    def test_a_new_activity_is_downloaded_and_stored_with_its_garmin_id_and_name(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(555, name="Lunch run")

        stored = _sync(linked, rate_limits)

        [activity] = _activities(committed_sessions, linked)
        assert [row.garminconnect_activity_id for row in stored] == [555]
        assert (activity.garminconnect_activity_id, activity.name) == (555, "Lunch run")
        assert account.called("download_activity") == [(555,)]

    def test_an_activity_already_stored_is_not_downloaded_again(self, account, linked, rate_limits, committed_sessions):
        account.add_activity(555)
        _sync(linked, rate_limits)
        account.calls.clear()

        assert _sync(linked, rate_limits) is None

        assert account.called("download_activity") == []
        assert len(_activities(committed_sessions, linked)) == 1

    def test_an_activity_of_another_user_with_the_same_garmin_id_does_not_hide_this_ones(
        self, account, linked, make_linked, rate_limits, committed_sessions
    ):
        account.add_activity(555)
        _sync(make_linked(), rate_limits)

        assert _sync(linked, rate_limits) is not None
        assert len(_activities(committed_sessions, linked)) == 1

    def test_a_window_with_nothing_new_stores_nothing(self, account, linked, rate_limits, committed_sessions):
        assert _sync(linked, rate_limits) is None

        assert _activities(committed_sessions, linked) == []

    def test_an_unlinked_user_is_not_synced(self, account, unlinked, rate_limits):
        account.add_activity(555)

        assert _sync(unlinked, rate_limits) is None

        assert account.calls == []

    def test_the_gear_of_a_synced_gear_is_assigned_to_the_activity(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.gear = [garmin_factories.gear_payload("g-1", gearTypeName="Bike", displayName="Gravel")]
        account.activity_gear[555] = [{"uuid": "g-1"}]
        assert garmin_gear_service.get_user_gear(linked.id, rate_limits) is True
        account.add_activity(555)

        _sync(linked, rate_limits)

        [activity] = _activities(committed_sessions, linked)
        with committed_sessions() as db:
            gear = db.scalars(select(gear_models.Gear).where(gear_models.Gear.garminconnect_gear_id == "g-1")).one()
        assert (activity.gear_id, activity.garminconnect_gear_id) == (gear.id, "g-1")

    def test_without_gear_sync_the_garmin_gear_id_is_recorded_but_no_local_gear_is_assigned(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.activity_gear[555] = [{"uuid": "g-1"}]
        account.add_activity(555)

        _sync(linked, rate_limits)

        [activity] = _activities(committed_sessions, linked)
        assert (activity.garminconnect_gear_id, activity.gear_id) == ("g-1", None)

    def test_a_gear_answer_that_is_not_a_list_fails_the_activity_and_the_sync(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.activity_gear[555] = {"uuid": "g-1"}
        account.add_activity(555)

        with pytest.raises(core_exceptions.DependencyFailedError):
            _sync(linked, rate_limits)

        assert _activities(committed_sessions, linked) == []


class TestAnActivityThatFails:
    def test_one_failing_download_does_not_stop_the_next_activity_but_fails_the_sync(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(1, name="Broken")
        account.add_activity(2, name="Fine")
        account.fail("download_activity", RuntimeError("garmin 500"), key=1)

        with pytest.raises(RuntimeError, match="garmin 500"):
            _sync(linked, rate_limits)

        assert [row.garminconnect_activity_id for row in _activities(committed_sessions, linked)] == [2]
        assert account.called("download_activity") == [(1,), (2,)]

    def test_a_failed_window_fetch_fails_the_sync(self, account, linked, rate_limits):
        account.fail("get_activities_by_date", RuntimeError("garmin 500"))

        with pytest.raises(RuntimeError, match="garmin 500"):
            _sync(linked, rate_limits)

    def test_a_download_that_is_not_a_zip_skips_the_activity(self, account, linked, rate_limits, committed_sessions):
        account.add_activity(555)
        account.archives[555] = b"not a zip"

        assert _sync(linked, rate_limits) is None

        assert _activities(committed_sessions, linked) == []

    def test_a_zip_with_no_activity_file_in_it_skips_the_activity(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(555)
        account.archives[555] = garmin_factories.zip_of({"555_ACTIVITY.txt": b"hello"})

        assert _sync(linked, rate_limits) is None

        assert _activities(committed_sessions, linked) == []

    def test_a_zip_that_escapes_its_directory_is_refused(self, account, linked, rate_limits, committed_sessions):
        account.add_activity(555)
        account.archives[555] = garmin_factories.zip_of({"../555_ACTIVITY.gpx": garmin_factories.activity_gpx()})

        assert _sync(linked, rate_limits) is None

        assert _activities(committed_sessions, linked) == []

    def test_a_zip_with_too_many_entries_to_extract_is_refused_and_logged_with_its_type(
        self, account, linked, rate_limits, committed_sessions, caplog
    ):
        account.add_activity(555)
        members = {f"555_{index}.gpx": b"<gpx/>" for index in range(1000)}
        members.update({f"555_{index}.tcx": b"<tcx/>" for index in range(1001)})
        account.archives[555] = garmin_factories.zip_of(members)

        assert _sync(linked, rate_limits) is None

        assert _activities(committed_sessions, linked) == []
        assert any("extraction failed" in record.getMessage() for record in caplog.records)

    def test_a_refused_file_of_a_multi_file_archive_does_not_stop_the_rest(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(555)
        account.archives[555] = garmin_factories.zip_of(
            {"555_a.gpx": garmin_factories.EMPTY_GPX, "555_b.gpx": garmin_factories.activity_gpx()}
        )

        stored = _sync(linked, rate_limits)

        assert [row.garminconnect_activity_id for row in stored] == [555]

    def test_an_answer_of_none_for_the_window_is_no_new_activities(self, account, linked, rate_limits):
        account.activities = None

        assert _sync(linked, rate_limits) is None

        assert account.called("download_activity") == []

    def test_a_file_ingestion_refuses_is_skipped_and_does_not_fail_the_window(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(1, name="Corrupt")
        account.add_activity(2, name="Fine")
        account.archives[1] = garmin_factories.zip_of({"1_ACTIVITY.gpx": garmin_factories.EMPTY_GPX})

        stored = _sync(linked, rate_limits)

        assert [row.garminconnect_activity_id for row in stored] == [2]
        assert [row.garminconnect_activity_id for row in _activities(committed_sessions, linked)] == [2]

    def test_a_failed_sync_still_stores_the_token_the_client_refreshed(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(555)
        account.fail("get_activities_by_date", RuntimeError("boom"))
        account.on_call = lambda method: setattr(account.clients[-1].client, "di_token", "access-rotated")

        with pytest.raises(RuntimeError):
            _sync(linked, rate_limits)

        assert stored_access_token(committed_sessions, linked.id) == "access-rotated"


class TestWorkDirectoryIsPrivate:
    def test_the_archive_and_extracted_files_live_in_a_removed_temp_directory(
        self, account, linked, rate_limits, tmp_path, monkeypatch
    ):
        """Nothing a failed attempt leaves behind can make the next sync fail (#750)."""
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(work))
        account.add_activity(555)
        account.add_activity(556)
        account.archives[556] = b"not a zip"

        _sync(linked, rate_limits)

        assert list(work.iterdir()) == []


class TestRoundTripsHoldNoSession:
    def test_garmin_is_called_with_no_database_connection_checked_out(self, account, linked, rate_limits):
        account.add_activity(555)
        checked_out: list[tuple[str, int]] = []
        account.on_call = lambda method: checked_out.append((method, core_database.engine.pool.checkedout()))

        _sync(linked, rate_limits)

        assert {method for method, _ in checked_out} == {
            "get_activities_by_date",
            "get_activity_gear",
            "download_activity",
        }
        assert {count for _, count in checked_out} == {0}


class TestRejectedToken:
    def test_a_rejection_on_the_window_unlinks_the_account_and_tells_the_user(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.fail("get_activities_by_date", garminconnect.GarminConnectAuthenticationError("401"))

        assert _sync(linked, rate_limits) is None

        assert stored_token(committed_sessions, linked.id) is None
        assert len(notifications_of(committed_sessions, linked.id)) == 1
        assert len(audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_REVOKE)) == 1

    def test_a_rejection_while_downloading_unlinks_the_account_and_stops_the_window(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.add_activity(1)
        account.add_activity(2)
        account.fail("download_activity", garminconnect.GarminConnectAuthenticationError("401"))

        _sync(linked, rate_limits)

        assert account.called("download_activity") == [(1,)]
        assert stored_token(committed_sessions, linked.id) is None
        assert len(notifications_of(committed_sessions, linked.id)) == 1
        assert _activities(committed_sessions, linked) == []


class TestRateLimit:
    """A Garmin Connect 429 defers the refresh instead of failing it, as for Strava."""

    def test_a_rate_limited_window_fetch_raises_with_when_the_limit_clears_and_records_it(
        self, account, linked, rate_limits
    ):
        account.fail("get_activities_by_date", garminconnect.GarminConnectTooManyRequestsError("429"))
        before = datetime.now(UTC)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            _sync(linked, rate_limits)

        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER
        assert raised.value.retry_at is not None and raised.value.retry_at > before
        assert rate_limits.rate_limited_until(linked.id) == raised.value.retry_at

    def test_a_rate_limited_download_stops_the_window(self, account, linked, rate_limits, committed_sessions):
        account.add_activity(1)
        account.add_activity(2)
        account.fail("download_activity", garminconnect.GarminConnectTooManyRequestsError("429"))

        with pytest.raises(core_exceptions.TooManyRequestsError):
            _sync(linked, rate_limits)

        assert account.called("download_activity") == [(1,)]
        assert rate_limits.rate_limited_until(linked.id) is not None

    def test_a_limited_account_is_refused_before_garmin_is_called(self, account, linked, rate_limits):
        until = rate_limits.mark_rate_limited(linked.id)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            _sync(linked, rate_limits)

        assert raised.value.retry_at == until
        assert account.clients == []
