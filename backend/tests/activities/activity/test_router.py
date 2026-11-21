"""The activity routes, through the production application: real authentication, scopes, handlers and database."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest
from sqlalchemy import select

import core.config as core_config
import modules.activities.activity.bulk_edit_job_service as bulk_edit_job_service
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.events as activity_events
import modules.activities.activity.models as activity_models
from tests._factories.activities import make_activity, make_activity_at
from tests._factories.followers import make_follow
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/activities"
_USERS = f"{core_config.ROOT_PATH}/users"
_DAY = datetime(2026, 7, 15, 9, tzinfo=UTC)
_Visibility = activity_constants.ActivityVisibility
_ANY_ID = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


def _stored(committed_sessions, activity_id) -> activity_models.Activity | None:
    """Read an activity back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(activity_models.Activity, activity_id)
        if row is not None:
            db.expunge(row)
        return row


class TestListOwnActivities:
    def test_the_page_envelope_holds_summaries_newest_first(self, me, owner, make_committed_activity):
        old = make_committed_activity(owner, start_time=_DAY, end_time=_DAY + timedelta(hours=1), name="Old")
        new = make_committed_activity(
            owner,
            start_time=_DAY + timedelta(days=1),
            end_time=_DAY + timedelta(days=1, hours=1),
            name="New",
            private_notes="secret",
        )

        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert "private_notes" not in body["items"][0] and "import_info" not in body["items"][0]
        assert body["items"][0]["visibility"] == "private"

    def test_a_page_names_the_next_one_until_the_last(self, me, owner, arrange):
        arrange(lambda db: [make_activity_at(db, owner.id, _DAY + timedelta(days=n)) for n in range(5)])

        first = me.client.get(_URL, params={"page_number": 1, "num_records": 2}).json()
        last = me.client.get(_URL, params={"page_number": 3, "num_records": 2}).json()

        assert (len(first["items"]), first["total"], first["next"]) == (2, 5, 2)
        assert (len(last["items"]), last["next"]) == (1, None)

    def test_no_activities_is_an_empty_page_not_a_bare_list(self, me):
        assert me.client.get(_URL).json()["items"] == []

    def test_another_users_activities_are_not_listed(self, me, other, make_committed_activity):
        make_committed_activity(other, visibility=_Visibility.PUBLIC)

        assert me.client.get(_URL).json()["total"] == 0

    def test_the_filters_narrow_the_page_and_its_total(self, me, owner, arrange):
        run, _ = arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, name="Tempo run", activity_type=1),
                make_activity_at(db, owner.id, _DAY + timedelta(days=1), name="Easy ride", activity_type=4),
            )
        )

        by_type = me.client.get(_URL, params={"type": "run"}).json()
        by_name = me.client.get(_URL, params={"name_contains": "easy"}).json()
        by_date = me.client.get(_URL, params={"start_date": "2026-07-15", "end_date": "2026-07-15"}).json()

        assert [i["id"] for i in by_type["items"]] == [str(run.id)] and by_type["total"] == 1
        assert by_name["total"] == 1 and by_name["items"][0]["name"] == "Easy ride"
        assert [i["id"] for i in by_date["items"]] == [str(run.id)]

    def test_the_list_sorts_by_the_key_and_direction_asked_for(self, me, owner, arrange):
        arrange(
            lambda db: [
                make_activity_at(db, owner.id, _DAY + timedelta(days=n), distance=distance)
                for n, distance in enumerate((300, 100, 200))
            ]
        )

        ascending = me.client.get(_URL, params={"sort_by": "distance", "sort_order": "asc"}).json()

        assert [item["distance"] for item in ascending["items"]] == [100, 200, 300]

    def test_a_gear_filter_keeps_the_activities_recorded_with_that_gear(self, me, owner, arrange):
        gear = arrange(lambda db: make_gear(db, owner.id))
        on_gear, _ = arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, gear_id=gear.id),
                make_activity_at(db, owner.id, _DAY + timedelta(days=1)),
            )
        )

        body = me.client.get(_URL, params={"gear_id": str(gear.id)}).json()

        assert [i["id"] for i in body["items"]] == [str(on_gear.id)] and body["total"] == 1

    @pytest.mark.parametrize(
        "params",
        [
            {"start_date": "2026-07-20", "end_date": "2026-07-10"},
            {"name_contains": ""},
            {"type": "unicycle"},
            {"sort_by": "mood"},
            {"sort_order": "sideways"},
            {"gear_id": "not-a-uuid"},
            {"page_number": 0},
            {"num_records": 201},
            {"start_date": "9999-12-31"},
            {"end_date": "0001-01-01"},
        ],
    )
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422


class TestTypes:
    def test_the_types_the_user_recorded_come_with_their_labels(self, me, owner, arrange):
        arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, activity_type=4),
                make_activity_at(db, owner.id, _DAY + timedelta(days=1), activity_type=1),
            )
        )

        assert me.client.get(f"{_URL}/types").json() == {"run": "Run", "ride": "Ride"}


class TestFeed:
    def test_the_following_feed_lists_the_followees_activities_with_their_profiles(self, me, owner, arrange):
        followee = arrange(lambda db: make_user(db, timezone="UTC"))
        arrange(lambda db: make_follow(db, owner.id, followee.id, accepted=True))
        public = arrange(lambda db: make_activity(db, followee.id, visibility=_Visibility.PUBLIC))
        arrange(lambda db: make_activity(db, followee.id, visibility=_Visibility.PRIVATE))
        arrange(lambda db: make_activity(db, owner.id, visibility=_Visibility.PUBLIC))

        body = me.client.get(f"{_URL}/feed").json()

        assert [item["id"] for item in body["items"]] == [str(public.id)]
        assert set(body["users"]) == {str(followee.id)}
        assert body["next_cursor"] is None

    def test_scope_mine_lists_the_callers_own_activities_of_every_visibility(self, me, owner, arrange):
        ids = arrange(
            lambda db: [
                make_activity_at(db, owner.id, _DAY + timedelta(hours=n * 3), visibility=v).id
                for n, v in enumerate((_Visibility.PRIVATE, _Visibility.PUBLIC))
            ]
        )

        body = me.client.get(f"{_URL}/feed", params={"scope": "mine"}).json()

        assert [item["id"] for item in body["items"]] == [str(i) for i in reversed(ids)]
        assert set(body["users"]) == {str(owner.id)}

    def test_the_cursor_continues_where_the_slice_ended(self, me, owner, arrange):
        ids = arrange(lambda db: [make_activity_at(db, owner.id, _DAY + timedelta(hours=n)).id for n in range(3)])

        first = me.client.get(f"{_URL}/feed", params={"scope": "mine", "num_records": 2}).json()
        second = me.client.get(
            f"{_URL}/feed", params={"scope": "mine", "num_records": 2, "cursor": first["next_cursor"]}
        ).json()

        assert [i["id"] for i in first["items"]] == [str(ids[2]), str(ids[1])]
        assert [i["id"] for i in second["items"]] == [str(ids[0])]
        assert second["next_cursor"] is None

    @pytest.mark.parametrize("params", [{"scope": "everyone"}, {"num_records": 0}, {"cursor": "not-a-cursor"}])
    def test_a_query_the_route_does_not_accept_is_refused(self, me, params):
        assert me.client.get(f"{_URL}/feed", params=params).status_code in (400, 422)

    def test_a_malformed_cursor_is_a_client_error_with_a_problem_document(self, me):
        response = me.client.get(f"{_URL}/feed", params={"cursor": "not-a-cursor"})

        assert response.status_code == 400
        assert response.headers["content-type"].startswith("application/problem+json")


class TestUserActivities:
    def test_another_user_lists_only_what_the_viewer_may_see(self, me, owner, other, arrange):
        public = arrange(lambda db: make_activity_at(db, other.id, _DAY, visibility=_Visibility.PUBLIC))
        followers = arrange(
            lambda db: make_activity_at(db, other.id, _DAY + timedelta(days=1), visibility=_Visibility.FOLLOWERS)
        )
        arrange(lambda db: make_activity_at(db, other.id, _DAY + timedelta(days=2)))

        before = me.client.get(f"{_USERS}/{other.id}/activities").json()
        arrange(lambda db: make_follow(db, owner.id, other.id, accepted=True))
        after = me.client.get(f"{_USERS}/{other.id}/activities").json()

        assert [i["id"] for i in before["items"]] == [str(public.id)] and before["total"] == 1
        assert [i["id"] for i in after["items"]] == [str(followers.id), str(public.id)]

    def test_the_activity_comes_without_what_its_owner_hid(self, me, other, arrange):
        arrange(
            lambda db: make_activity(
                db,
                other.id,
                visibility=_Visibility.PUBLIC,
                city="Porto",
                average_hr=150,
                hide_location=True,
                hide_hr=True,
                private_notes="n",
            )
        )

        [item] = me.client.get(f"{_USERS}/{other.id}/activities").json()["items"]

        assert (item["city"], item["timezone"], item["average_hr"]) == (None, None, None)

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    def test_the_activities_and_stats_of_an_inactive_or_pending_user_are_404(self, me, arrange, state):
        gone = arrange(lambda db: make_user(db, **state))

        assert me.client.get(f"{_USERS}/{gone.id}/activities").status_code == 404
        assert me.client.get(f"{_USERS}/{gone.id}/activities/stats").status_code == 404

    def test_a_user_that_does_not_exist_is_404(self, me):
        assert me.client.get(f"{_USERS}/{uuid.uuid4()}/activities").status_code == 404

    @pytest.mark.parametrize("param", ["start_date", "end_date"])
    @pytest.mark.parametrize("value", ["9999-12-31", "0001-01-01"])
    def test_a_bound_outside_the_supported_range_is_422(self, me, other, param, value):
        assert me.client.get(f"{_USERS}/{other.id}/activities", params={param: value}).status_code == 422


class TestUserStats:
    def test_the_totals_become_per_sport_stats_of_the_week_holding_the_date(self, me, owner, arrange):
        arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, activity_type=4, distance=30000, total_timer_time=5400.0),
                make_activity_at(db, owner.id, _DAY + timedelta(days=30), activity_type=1),
            )
        )

        body = me.client.get(f"{_USERS}/{owner.id}/activities/stats", params={"date": "2026-07-16"}).json()

        assert (body["bike"]["distance"], body["bike"]["time"], body["run"]["distance"]) == (30000.0, 5400.0, 0.0)

    def test_the_month_period_covers_the_whole_month(self, me, owner, arrange):
        arrange(lambda db: make_activity_at(db, owner.id, _DAY + timedelta(days=10), distance=7000))

        body = me.client.get(
            f"{_USERS}/{owner.id}/activities/stats", params={"period": "month", "date": "2026-07-01"}
        ).json()

        assert body["run"]["distance"] == 7000.0

    def test_without_a_date_the_period_is_the_one_of_the_users_today_on_the_platform_clock(self, me, owner, arrange):
        jasil_runtime.get_active_platform().clock.moment = _DAY
        arrange(lambda db: make_activity_at(db, owner.id, _DAY - timedelta(hours=2), distance=1234))

        assert me.client.get(f"{_USERS}/{owner.id}/activities/stats").json()["run"]["distance"] == 1234.0

    def test_another_users_stats_hold_only_their_public_activities(self, me, other, arrange):
        arrange(lambda db: make_activity_at(db, other.id, _DAY, visibility=_Visibility.PUBLIC, distance=1000))
        arrange(lambda db: make_activity_at(db, other.id, _DAY + timedelta(hours=3), distance=4000))

        body = me.client.get(f"{_USERS}/{other.id}/activities/stats", params={"date": "2026-07-15"}).json()

        assert body["run"]["distance"] == 1000.0

    def test_an_empty_period_is_all_zero(self, me, owner):
        body = me.client.get(f"{_USERS}/{owner.id}/activities/stats").json()

        assert body["run"] == {"distance": 0.0, "time": 0.0, "calories": 0.0}

    @pytest.mark.parametrize("params", [{"period": "year"}, {"date": "not-a-date"}])
    def test_a_query_the_route_does_not_accept_is_422(self, me, owner, params):
        assert me.client.get(f"{_USERS}/{owner.id}/activities/stats", params=params).status_code == 422

    @pytest.mark.parametrize("period", ["week", "month"])
    @pytest.mark.parametrize("anchor", ["9999-12-31", "0001-01-01"])
    def test_an_anchor_outside_the_supported_range_is_422(self, me, owner, period, anchor):
        response = me.client.get(f"{_USERS}/{owner.id}/activities/stats", params={"period": period, "date": anchor})

        assert response.status_code == 422

    @pytest.mark.parametrize("period", ["week", "month"])
    def test_the_last_supported_day_is_accepted(self, me, owner, period):
        response = me.client.get(
            f"{_USERS}/{owner.id}/activities/stats", params={"period": period, "date": "9998-12-31"}
        )

        assert response.status_code == 200


class TestRead:
    def test_the_activity_comes_with_its_version_as_the_etag_and_the_owners_private_fields(
        self, me, owner, make_committed_activity
    ):
        activity = make_committed_activity(owner, private_notes="mine", description="d")

        response = me.client.get(f"{_URL}/{activity.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert (body["id"], body["private_notes"], body["description"], body["version"]) == (
            str(activity.id),
            "mine",
            "d",
            1,
        )
        assert "map_thumbnail_path" not in body

    def test_a_public_activity_of_another_user_is_masked_and_a_private_one_is_404(
        self, me, other, make_committed_activity
    ):
        public = make_committed_activity(
            other, visibility=_Visibility.PUBLIC, private_notes="theirs", hide_hr=True, average_hr=1
        )
        private = make_committed_activity(other)

        body = me.client.get(f"{_URL}/{public.id}").json()

        assert (body["private_notes"], body["average_hr"]) == (None, None)
        assert me.client.get(f"{_URL}/{private.id}").status_code == 404

    def test_a_followers_activity_opens_for_an_accepted_follower_only(self, me, owner, other, arrange):
        followers = arrange(lambda db: make_activity(db, other.id, visibility=_Visibility.FOLLOWERS))
        arrange(lambda db: make_follow(db, owner.id, other.id, accepted=False))
        pending = me.client.get(f"{_URL}/{followers.id}").status_code

        with_follow = arrange(lambda db: make_user(db, timezone="UTC"))
        accepted_id = arrange(lambda db: make_activity(db, with_follow.id, visibility=_Visibility.FOLLOWERS).id)
        arrange(lambda db: make_follow(db, owner.id, with_follow.id, accepted=True))

        assert pending == 404
        assert me.client.get(f"{_URL}/{accepted_id}").status_code == 200

    def test_an_activity_that_does_not_exist_is_404_and_an_id_that_is_not_a_uuid_is_422(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404
        assert me.client.get(f"{_URL}/not-a-uuid").status_code == 422


class TestEdit:
    @pytest.fixture
    def activity(self, owner, make_committed_activity):
        return make_committed_activity(owner, name="Original", description="before")

    def _patch(self, client, activity_id, body, *, if_match='"1"'):
        headers = {} if if_match is None else {"If-Match": if_match}
        return client.patch(f"{_URL}/{activity_id}", json=body, headers=headers)

    def test_the_change_is_applied_and_the_version_and_etag_move_on(self, me, activity, committed_sessions):
        response = self._patch(me.client, activity.id, {"name": "Renamed", "visibility": "public"})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["name"], body["description"], body["visibility"], body["version"]) == (
            "Renamed",
            "before",
            "public",
            2,
        )
        row = _stored(committed_sessions, activity.id)
        assert (row.name, row.visibility, row.version) == ("Renamed", 0, 2)
        assert me.client.get(f"{_URL}/{activity.id}").headers["ETag"] == '"2"'

    def test_an_edit_publishes_updated_with_the_fields_sent(self, me, activity):
        delivered: list = []
        jasil_runtime.get_active_platform().events.subscribe(activity_events.ACTIVITY_UPDATED, delivered.append)

        self._patch(me.client, activity.id, {"description": "after"})

        [event] = delivered
        assert (event.payload["activity_id"], event.payload["changed_fields"]) == (str(activity.id), ["description"])

    def test_the_markdown_is_sanitised_before_it_is_stored(self, me, activity, committed_sessions):
        self._patch(me.client, activity.id, {"description": "<script>alert(1)</script>fine"})

        assert "<script" not in _stored(committed_sessions, activity.id).description

    def test_a_stale_version_is_412_and_the_activity_is_unchanged(self, me, activity, committed_sessions):
        assert self._patch(me.client, activity.id, {"name": "First"}).status_code == 200

        response = self._patch(me.client, activity.id, {"name": "Second"})

        assert response.status_code == 412
        assert _stored(committed_sessions, activity.id).name == "First"

    def test_a_missing_if_match_is_428_and_nothing_changes(self, me, activity, committed_sessions):
        response = self._patch(me.client, activity.id, {"name": "Nope"}, if_match=None)

        assert response.status_code == 428
        assert _stored(committed_sessions, activity.id).name == "Original"

    def test_a_gear_of_another_user_is_404_and_nothing_changes(self, me, activity, other, arrange, committed_sessions):
        theirs = arrange(lambda db: make_gear(db, other.id))

        response = self._patch(me.client, activity.id, {"name": "New", "gear_id": str(theirs.id)})

        assert response.status_code == 404
        assert _stored(committed_sessions, activity.id).name == "Original"

    def test_the_owners_own_gear_is_assigned(self, me, owner, activity, arrange, committed_sessions):
        gear = arrange(lambda db: make_gear(db, owner.id))

        assert self._patch(me.client, activity.id, {"gear_id": str(gear.id)}).status_code == 200
        assert _stored(committed_sessions, activity.id).gear_id == gear.id

    @pytest.mark.parametrize(
        "body",
        [
            {"id": _ANY_ID},
            {"user_id": _ANY_ID},
            {"version": 5},
            {"distance": 1},
            {"strava_activity_id": 1},
            {"visibility": 0},
            {"visibility": "everyone"},
            {"name": ""},
            {"name": None},
            {"hide_hr": "yes"},
            {"activity_type": 4},
        ],
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_changes(self, me, activity, committed_sessions, body):
        response = self._patch(me.client, activity.id, body)

        assert response.status_code == 422
        assert _stored(committed_sessions, activity.id).name == "Original"

    def test_the_activity_type_is_edited_by_its_name(self, me, activity, committed_sessions):
        assert self._patch(me.client, activity.id, {"activity_type": "ride"}).status_code == 200
        assert _stored(committed_sessions, activity.id).activity_type == activity_constants.ActivityType.RIDE.stored


class TestDelete:
    def test_the_activity_goes_with_a_204_and_leaves_a_tombstone(
        self, me, owner, make_committed_activity, committed_sessions
    ):
        activity = make_committed_activity(owner)

        response = me.client.delete(f"{_URL}/{activity.id}", headers={"If-Match": '"1"'})

        assert (response.status_code, response.content) == (204, b"")
        assert _stored(committed_sessions, activity.id) is None
        with committed_sessions() as db:
            assert db.scalars(select(activity_models.ActivityDeletion.record_id)).all() == [activity.id]

    def test_deleted_is_published_once(self, me, owner, make_committed_activity):
        activity = make_committed_activity(owner)
        delivered: list = []
        jasil_runtime.get_active_platform().events.subscribe(activity_events.ACTIVITY_DELETED, delivered.append)

        me.client.delete(f"{_URL}/{activity.id}", headers={"If-Match": '"1"'})

        assert [e.payload["activity_id"] for e in delivered] == [str(activity.id)]

    def test_a_stale_version_is_412_and_the_activity_stays(
        self, me, owner, make_committed_activity, committed_sessions
    ):
        activity = make_committed_activity(owner)

        response = me.client.delete(f"{_URL}/{activity.id}", headers={"If-Match": '"7"'})

        assert response.status_code == 412
        assert _stored(committed_sessions, activity.id) is not None

    def test_a_missing_if_match_is_428_and_the_activity_stays(
        self, me, owner, make_committed_activity, committed_sessions
    ):
        activity = make_committed_activity(owner)

        assert me.client.delete(f"{_URL}/{activity.id}").status_code == 428
        assert _stored(committed_sessions, activity.id) is not None

    def test_an_activity_that_does_not_exist_is_404(self, me):
        assert me.client.delete(f"{_URL}/{uuid.uuid4()}", headers={"If-Match": '"1"'}).status_code == 404


class TestBulkVisibilityEdit:
    def test_the_edit_is_accepted_with_a_job_and_changes_every_activity_of_the_caller(
        self, me, owner, other, arrange, committed_sessions
    ):
        mine = arrange(lambda db: [make_activity_at(db, owner.id, _DAY + timedelta(days=n)).id for n in range(2)])
        theirs = arrange(lambda db: make_activity(db, other.id).id)

        response = me.client.patch(_URL, json={"visibility": "followers"})
        bulk_edit_job_service.shutdown_pool(wait=True)

        assert response.status_code == 202
        body = response.json()
        assert (body["kind"], body["status"]) == ("activities_bulk_edit", "queued")
        assert response.headers["Content-Location"] == f"{core_config.ROOT_PATH}/jobs/{body['id']}"
        assert [_stored(committed_sessions, i).visibility for i in mine] == [1, 1]
        assert _stored(committed_sessions, theirs).visibility == 2
        assert me.client.get(f"{core_config.ROOT_PATH}/jobs/{body['id']}").json()["status"] == "succeeded"

    @pytest.mark.parametrize("body", [{}])
    def test_a_body_naming_nothing_to_change_is_400(self, me, body):
        assert me.client.patch(_URL, json=body).status_code == 400

    @pytest.mark.parametrize(
        "body",
        [
            {"visibility": None},
            {"visibility": 9},
            {"visibility": 1},
            {"visibility": "everyone"},
            {"visibilty": "public"},
        ],
    )
    def test_a_value_or_field_the_route_does_not_know_is_422(self, me, body):
        assert me.client.patch(_URL, json=body).status_code == 422

    def test_a_second_edit_while_one_is_pending_is_409(self, me, owner, make_committed_activity, monkeypatch):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        make_committed_activity(owner)
        first = me.client.patch(_URL, json={"visibility": "public"})

        second = me.client.patch(_URL, json={"visibility": "followers"})

        assert (first.status_code, second.status_code) == (202, 409)
