from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
from modules.activities.activity.constants import ActivityType


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity.router as activity_router
    import modules.activities.activity.user_router as activity_user_router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    # Same boundary the production app registers, so a DomainError raised by the
    # service is asserted as the response a client actually receives.
    core_exceptions.register_exception_handlers(app)
    app.include_router(activity_router.router, prefix="/activities")
    app.include_router(activity_user_router.router, prefix="/users")
    app.add_api_route("/jobs/{job_id}", lambda job_id: None, name="read_job")

    def _mock():
        return None

    for dep in [
        auth_deps.check_scopes,
        auth_deps.get_sub_from_access_token,
        auth_deps.get_user_id_from_auth,
        auth_deps.check_auth_scopes,
    ]:
        app.dependency_overrides[dep] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


@pytest.fixture(autouse=True)
def visible_owner():
    """Treat another user's activities as readable; the owner check itself is a service rule."""
    with patch("modules.activities.activity.service.users_integration.get_public_profile") as mock:
        yield mock


def _valid_activity(**kw):
    from modules.activities.activity.schema import ActivityRead

    data = dict(
        distance=10000,
        name="Test",
        activity_type=1,
        start_time="2024-01-15T08:00:00Z",
        end_time="2024-01-15T09:00:00Z",
        timezone="UTC",
        total_elapsed_time=3600.0,
        total_timer_time=3600.0,
        calories=500,
        visibility=0,
        elevation_gain=50,
        elevation_loss=45,
        pace=300.0,
        average_hr=145,
        max_hr=175,
        average_speed=2.78,
        max_speed=5.0,
        city="City",
        town="Town",
        country="Country",
        description="desc",
        gear_id=1,
        id=1,
        user_id=1,
    )
    data.update(kw)
    return ActivityRead(**data)


def _feed_entry(**kw):
    from modules.activities.activity.contracts import ActivityFeedEntry

    activity = _valid_activity(**kw)
    return ActivityFeedEntry(
        activity=activity,
        cursor_sort_value=datetime(2024, 1, 15, 8, tzinfo=UTC),
        cursor_id=activity.id or 1,
    )


class TestListOwnActivities:
    """The list endpoint carries its own total, so no second /count call."""

    def test_list_returns_page_envelope(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=1),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities", headers={"Authorization": "Bearer x"})

            assert resp.status_code == 200
            body = resp.json()
            assert len(body["items"]) == 1
            assert body["total"] == 1
            assert body["page"] == 1
            assert body["next"] is None

    @pytest.mark.parametrize("path", ["/activities", "/users/2/activities"])
    def test_a_start_after_the_end_is_a_validation_error(self, mock_db, path):
        resp = TestClient(_build_app(mock_db)).get(
            f"{path}?start_date=2026-02-01&end_date=2026-01-01", headers={"Authorization": "Bearer x"}
        )

        assert resp.status_code == 422
        assert resp.json()["errors"][0]["field"].endswith("end_date")

    def test_the_name_filter_is_name_contains(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as rows,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=0),
        ):
            rows.return_value = []
            resp = TestClient(_build_app(mock_db)).get(
                "/activities?name_contains=Morning", headers={"Authorization": "Bearer x"}
            )

            assert resp.status_code == 200
            assert rows.call_args.kwargs["name_search"] == "Morning"

    def test_next_points_to_the_following_page(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=45),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities?page_number=2&num_records=20", headers={"Authorization": "Bearer x"}
            )

            body = resp.json()
            assert body["total"] == 45
            assert body["page"] == 2
            assert body["next"] == 3

    def test_last_page_has_no_next(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=40),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities?page_number=2&num_records=20", headers={"Authorization": "Bearer x"}
            )

            assert resp.json()["next"] is None

    def test_empty_result_is_a_page_not_a_bare_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=0),
        ):
            m.return_value = []
            resp = TestClient(_build_app(mock_db)).get("/activities", headers={"Authorization": "Bearer x"})

            assert resp.status_code == 200
            assert resp.json() == {"items": [], "total": 0, "page": 1, "num_records": 25, "next": None}

    def test_count_endpoint_is_gone(self, mock_db):
        # 422, not 404: with /count removed the path now falls through to
        # GET /activities/{activity_id}, where "count" fails int validation.
        resp = TestClient(_build_app(mock_db)).get("/activities/count", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 422


class TestTypes:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.service.activity_crud.get_distinct_activity_types_for_user") as m:
            m.return_value = [ActivityType.RUN, ActivityType.TRAIL_RUN]
            resp = TestClient(_build_app(mock_db)).get("/activities/types", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert resp.json() == {"run": "Run", "trail_run": "Trail run"}


class TestFeed:
    def test_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after") as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = [_feed_entry()]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert len(resp.json()["items"]) == 1

    def test_scope_defaults_to_following(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after", return_value=[]) as m,
            patch("modules.activities.activity.service.activity_crud.get_own_feed_after") as own,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})

        assert resp.status_code == 200
        m.assert_called_once()
        own.assert_not_called()

    def test_scope_mine_lists_the_callers_own_activities(self, mock_db):
        from modules.users.users.schema import UserPublicRead

        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after") as following,
            patch("modules.activities.activity.service.activity_crud.get_own_feed_after") as own,
            patch("modules.activities.activity.service.users_integration.list_public_profiles") as profiles,
        ):
            own.return_value = [_feed_entry(id=4, user_id=1)]
            profiles.return_value = {1: UserPublicRead(id=1, name="Me", username="me")}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/feed?scope=mine", headers={"Authorization": "Bearer x"}
            )

        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["items"]] == [4]
        assert list(resp.json()["users"]) == ["1"]
        own.assert_called_once()
        following.assert_not_called()
        f.list_accepted_followee_ids.assert_not_called()

    def test_an_unknown_scope_is_rejected(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get("/activities/feed?scope=all", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 422

    def test_users_carries_each_distinct_owner_once(self, mock_db):
        from modules.users.users.schema import UserPublicRead

        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after") as m,
            patch("modules.activities.activity.service.users_integration.list_public_profiles") as profiles,
        ):
            f.list_accepted_followee_ids.return_value = [5, 6]
            m.return_value = [
                _feed_entry(id=1, user_id=5),
                _feed_entry(id=2, user_id=6),
                _feed_entry(id=3, user_id=5),
            ]
            profiles.return_value = {5: UserPublicRead(id=5, name="Ada", username="ada")}
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})

        assert resp.status_code == 200
        profiles.assert_called_once()
        assert profiles.call_args.args[0] == {5, 6}
        assert resp.json()["users"] == {
            "5": {"id": 5, "name": "Ada", "username": "ada", "city": None, "photo_path": None}
        }

    def test_an_empty_feed_has_an_empty_users_object(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after", return_value=[]),
        ):
            f.list_accepted_followee_ids.return_value = [5]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})

        assert resp.json()["users"] == {}

    def test_last_slice_has_no_next_cursor(self, mock_db):
        """A short slice means the end; emitting a cursor would loop the client."""
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after") as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = [_feed_entry()]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})
            assert resp.json()["next_cursor"] is None

    def test_hidden_start_time_still_emits_a_next_cursor(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as followers,
            patch("modules.activities.activity.service.activity_crud.get_following_feed_after") as get_feed,
        ):
            followers.list_accepted_followee_ids.return_value = [5]
            get_feed.return_value = [
                _feed_entry(hide_start_time=True, start_time=None, end_time=None),
                _feed_entry(id=2),
            ]

            response = TestClient(_build_app(mock_db)).get(
                "/activities/feed?num_records=1",
                headers={"Authorization": "Bearer x"},
            )

            assert response.status_code == 200
            assert response.json()["items"][0]["start_time"] is None
            assert response.json()["next_cursor"] is not None

    def test_rejects_a_malformed_cursor(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/activities/feed?cursor=not-a-cursor", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 400

    def test_count_endpoint_is_gone(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get("/activities/feed/count", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 404


class TestGearFilter:
    def test_gear_id_filters_the_callers_own_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as page,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=0) as count,
        ):
            page.return_value = []
            resp = TestClient(_build_app(mock_db)).get("/activities?gear_id=5", headers={"Authorization": "Bearer x"})

        assert resp.status_code == 200
        assert page.call_args.kwargs["gear_id"] == 5
        assert count.call_args.kwargs["gear_id"] == 5

    def test_no_gear_id_leaves_the_list_unfiltered(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as page,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=0),
        ):
            page.return_value = []
            TestClient(_build_app(mock_db)).get("/activities", headers={"Authorization": "Bearer x"})

        assert page.call_args.kwargs["gear_id"] is None

    def test_a_non_positive_gear_id_is_rejected(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get("/activities?gear_id=0", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 422

    def test_another_users_list_has_no_gear_filter(self, mock_db):
        """Filtering by gear there would reveal a gear its owner hides."""
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as page,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=0),
            patch("modules.activities.activity.service._require_visible_owner"),
        ):
            page.return_value = []
            TestClient(_build_app(mock_db)).get("/users/2/activities?gear_id=5", headers={"Authorization": "Bearer x"})

        assert page.call_args.kwargs["gear_id"] is None

    def test_the_gear_activities_route_is_gone(self):
        from fastapi import FastAPI

        from api import router

        app = FastAPI()
        app.include_router(router)

        assert not any(path.endswith("/gears/{gear_id}/activities") for path in app.openapi()["paths"])


class TestUserStats:
    @pytest.fixture(autouse=True)
    def _stub_user_local_today(self):
        """Pin the fallback anchor.

        Without a ``date`` query param the service resolves today in the
        requester's timezone, which is a DB read the mocked session cannot serve.
        """
        from datetime import date

        with (
            patch(
                "modules.activities.activity.service.users_integration.local_today",
                return_value=date(2026, 3, 12),
            ),
            patch(
                "modules.activities.activity.service.core_timezone.today_in",
                return_value=date(2026, 3, 12),
            ),
            patch(
                "modules.activities.activity.service.users_integration.get_user",
                return_value=SimpleNamespace(first_day_of_week="monday", timezone="UTC"),
            ),
        ):
            yield

    @pytest.mark.parametrize("period", ["week", "month"])
    def test_the_totals_become_per_sport_stats(self, mock_db, period):
        from modules.activities.activity.contracts import ActivityTypeTotals

        with patch(
            "modules.activities.activity.service.activity_crud.sum_user_activities_per_timeframe_by_type"
        ) as totals:
            totals.return_value = [ActivityTypeTotals(1, distance=5000.0, time=1800.0, calories=250.0)]
            resp = TestClient(_build_app(mock_db)).get(
                f"/users/1/activities/stats?period={period}", headers={"Authorization": "Bearer x"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["run"] == {"distance": 5000.0, "time": 1800.0, "calories": 250.0}
        assert body["bike"] == {"distance": 0.0, "time": 0.0, "calories": 0.0}

    def test_empty(self, mock_db):
        with patch(
            "modules.activities.activity.service.activity_crud.sum_user_activities_per_timeframe_by_type",
            return_value=[],
        ):
            resp = TestClient(_build_app(mock_db)).get(
                "/users/1/activities/stats?period=week", headers={"Authorization": "Bearer x"}
            )

        assert resp.status_code == 200
        assert resp.json()["run"]["distance"] == 0.0

    def test_invalid_period(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/users/1/activities/stats?period=bogus", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422


class TestListUserActivities:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activity_crud.count_user_activities", return_value=1),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/users/2/activities", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert resp.json()["total"] == 1


class TestAnotherUsersActivitiesOfAnInactiveOwner:
    @pytest.mark.parametrize("path", ["/users/2/activities", "/users/2/activities/stats"])
    def test_an_inactive_or_pending_owner_is_not_found(self, mock_db, visible_owner, path):
        visible_owner.side_effect = core_exceptions.NotFoundError("User not found")

        resp = TestClient(_build_app(mock_db)).get(path, headers={"Authorization": "Bearer x"})

        assert resp.status_code == 404


class TestReadByID:
    def test_success(self, mock_db):
        with patch(
            "modules.activities.activity.service.activity_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).get("/activities/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_not_found(self, mock_db):
        with patch(
            "modules.activities.activity.service.activity_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get("/activities/999", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 404


class TestEdit:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.edit_activity") as m,
            patch(
                "modules.activities.activity.service.activity_crud.get_activity_by_id_from_user_id",
                return_value=_valid_activity(),
            ),
        ):
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={**{"Authorization": "Bearer x"}, "If-Match": '"1"'},
                json={"name": "Run", "activity_type": "run", "visibility": "private"},
            )
            assert resp.status_code == 200

    def test_partial_update_single_field(self, mock_db):
        # A true PATCH: only the sent field is forwarded to crud.
        with (
            patch("modules.activities.activity.service.activity_crud.edit_activity") as m,
            patch(
                "modules.activities.activity.service.activity_crud.get_activity_by_id_from_user_id",
                return_value=_valid_activity(),
            ),
        ):
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={**{"Authorization": "Bearer x"}, "If-Match": '"1"'},
                json={"visibility": "private"},
            )
            assert resp.status_code == 200

    def test_path_id_is_passed_to_crud(self, mock_db):
        # The activity id comes from the path (not the body) and is passed to crud.
        with (
            patch("modules.activities.activity.service.activity_crud.edit_activity") as m,
            patch(
                "modules.activities.activity.service.activity_crud.get_activity_by_id_from_user_id",
                return_value=_valid_activity(),
            ),
        ):
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/7",
                headers={**{"Authorization": "Bearer x"}, "If-Match": '"1"'},
                json={"name": "Run", "visibility": "private"},
            )
            assert resp.status_code == 200
            # edit_activity(token_user_id, activity_id, activity_attributes, db)
            assert m.call_args.args[1] == 7

    def test_rejects_id_in_body(self, mock_db):
        # id is not a body field; extra="forbid" rejects it.
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities/1",
            headers={**{"Authorization": "Bearer x"}, "If-Match": '"1"'},
            json={"id": 1, "name": "Run"},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("body", [{"activity_type": 1}, {"visibility": 2}])
    def test_edit_refuses_the_stored_integers(self, mock_db, body):
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities/1", headers={"Authorization": "Bearer x", "If-Match": '"1"'}, json=body
        )
        assert resp.status_code == 422


class TestEditVisibility:
    def test_success_queues_the_edit_and_answers_202(self, mock_db):
        with patch("modules.activities.activity.router.activity_bulk_edit_job_service.request_visibility_edit") as m:
            m.return_value = activity_schema.ActivitiesBulkEditStatus(
                id="job-1",
                kind="activities_bulk_edit",
                status="queued",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities", json={"visibility": "followers"}, headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 202
            assert resp.json() == {
                "id": "job-1",
                "kind": "activities_bulk_edit",
                "created_at": "2026-01-01T00:00:00Z",
                "finished_at": None,
                "error_code": None,
                "status": "queued",
            }
            assert resp.headers["Content-Location"] == "/jobs/job-1"
            assert m.call_args.args[1] == 1

    def test_an_empty_patch_is_invalid_input(self, mock_db):
        resp = TestClient(_build_app(mock_db)).patch("/activities", json={}, headers={"Authorization": "Bearer x"})
        assert resp.status_code == 400

    @pytest.mark.parametrize("visibility", [9, 1, "everyone"])
    def test_rejects_an_unknown_visibility_and_the_stored_integer(self, mock_db, visibility):
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities", json={"visibility": visibility}, headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422

    def test_rejects_an_unknown_field(self, mock_db):
        """A typo'd field must not look like a successful no-op."""
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities", json={"visibilty": 1}, headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422

    def test_rejects_an_empty_patch(self, mock_db):
        """An empty body is a client bug, not a successful no-op."""
        resp = TestClient(_build_app(mock_db)).patch("/activities", json={}, headers={"Authorization": "Bearer x"})
        assert resp.status_code == 400


_DELETE_HEADERS = {"Authorization": "Bearer x", "If-Match": '"3"'}


class TestDelete:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud.delete_activity") as mock_del,
            patch("modules.activities.activity.service.activity_event_publishers") as mock_pub,
        ):
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers=_DELETE_HEADERS)
            # 204 with no body: the resource is gone, and the status says so.
            assert resp.status_code == 204
            assert resp.content == b""
            # Ownership is in the delete's lookup, so the route passes the
            # requester through instead of pre-fetching.
            assert mock_del.call_args.args[0] == 1
            assert mock_del.call_args.args[1] == mock_pub.publish_activity_deleted.call_args.args[1]
            assert mock_del.call_args.kwargs == {"if_match": '"3"'}
            # The delete and the event are staged, then committed once, so the row
            # delete and the activity.deleted outbox row are atomic.
            mock_pub.publish_activity_deleted.assert_called_once()
            assert mock_pub.publish_activity_deleted.call_args.args[0] == 1
            assert "commit" not in mock_pub.publish_activity_deleted.call_args.kwargs

    def test_not_found(self, mock_db):
        """A missing activity — or one owned by someone else — 404s from the CRUD."""
        with (
            patch("modules.activities.activity.service.activity_crud.delete_activity") as mock_del,
            patch("modules.activities.activity.service.activity_event_publishers") as mock_pub,
        ):
            mock_del.side_effect = HTTPException(status_code=404, detail="Activity with id 999 not found")
            resp = TestClient(_build_app(mock_db)).delete("/activities/999", headers=_DELETE_HEADERS)
            assert resp.status_code == 404
            mock_pub.publish_activity_deleted.assert_not_called()

    def test_without_if_match_is_428(self, mock_db):
        with patch("modules.activities.activity.service.activity_crud") as crud:
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers={"Authorization": "Bearer x"})

        assert resp.status_code == 428
        crud.delete_activity.assert_not_called()

    def test_a_stale_if_match_is_412_and_publishes_nothing(self, mock_db):
        with (
            patch("modules.activities.activity.service.activity_crud") as crud,
            patch("modules.activities.activity.service.activity_event_publishers") as mock_pub,
        ):
            crud.delete_activity.side_effect = core_exceptions.PreconditionFailedError("stale")
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers=_DELETE_HEADERS)

        assert resp.status_code == 412
        mock_pub.publish_activity_deleted.assert_not_called()

    def test_a_delete_that_races_past_the_check_is_412(self, mock_db):
        from sqlalchemy.orm.exc import StaleDataError

        with patch("modules.activities.activity.service.activity_crud") as crud:
            crud.get_activity_by_id_from_user_id.return_value = _valid_activity()
            crud.delete_activity.side_effect = StaleDataError("row changed")
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers=_DELETE_HEADERS)

        assert resp.status_code == 412


class TestActivityConcurrency:
    """PATCH used to be last-writer-wins: the loser's edit vanished silently."""

    def test_read_returns_an_etag(self, mock_db):
        with patch("modules.activities.activity.service.get_activity") as m:
            m.return_value = _valid_activity()
            m.return_value.version = 3
            resp = TestClient(_build_app(mock_db)).get("/activities/1", headers={"Authorization": "Bearer x"})

        assert resp.headers["ETag"] == '"3"'

    def test_patch_without_if_match_is_refused_as_precondition_required(self, mock_db):
        with patch("modules.activities.activity.service.activity_crud") as crud:
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1", json={"name": "x"}, headers={"Authorization": "Bearer x"}
            )

        assert resp.status_code == 428
        crud.edit_activity.assert_not_called()

    def test_patch_with_a_stale_if_match_is_refused(self, mock_db):
        with patch("modules.activities.activity.service.activity_crud") as crud:
            crud.edit_activity.side_effect = core_exceptions.PreconditionFailedError("stale")
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                json={"name": "x"},
                headers={"Authorization": "Bearer x", "If-Match": '"4"'},
            )

        assert resp.status_code == 412
        assert crud.edit_activity.call_args.kwargs["if_match"] == '"4"'

    def test_patch_with_a_current_if_match_succeeds(self, mock_db):
        with patch("modules.activities.activity.service.activity_crud") as crud:
            current = _valid_activity()
            current.version = 5
            crud.get_activity_by_id_from_user_id.return_value = current
            crud.edit_activity.return_value = current
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                json={"name": "x"},
                headers={"Authorization": "Bearer x", "If-Match": '"5"'},
            )

        assert resp.status_code == 200
        assert resp.headers["ETag"] == '"5"'

    def test_a_write_that_races_past_the_check_is_still_refused(self, mock_db):
        """The header check is read-then-write; the DB version guard closes it.

        Without translating StaleDataError, a row changed between the
        precondition passing and the flush would overwrite the other edit --
        exactly the bug If-Match is meant to prevent.
        """
        from sqlalchemy.orm.exc import StaleDataError

        with patch("modules.activities.activity.service.activity_crud") as crud:
            current = _valid_activity()
            current.version = 5
            crud.get_activity_by_id_from_user_id.return_value = current
            crud.edit_activity.side_effect = StaleDataError("row changed")
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                json={"name": "x"},
                headers={"Authorization": "Bearer x", "If-Match": '"5"'},
            )

        assert resp.status_code == 412


class TestDateWindowBounds:
    """A ``date`` whose window arithmetic leaves the representable range is a 422, not a 500."""

    @pytest.fixture(autouse=True)
    def _stub_requester(self):
        with patch(
            "modules.activities.activity.service.users_integration.get_user",
            return_value=SimpleNamespace(first_day_of_week="monday", timezone="UTC"),
        ):
            yield

    @pytest.mark.parametrize("period", ["week", "month"])
    @pytest.mark.parametrize("anchor", ["9999-12-31", "0001-01-01"])
    def test_stats_rejects_an_anchor_outside_the_supported_range(self, mock_db, period, anchor):
        resp = TestClient(_build_app(mock_db)).get(
            f"/users/1/activities/stats?period={period}&date={anchor}", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("param", ["start_date", "end_date"])
    @pytest.mark.parametrize("value", ["9999-12-31", "0001-01-01"])
    def test_user_list_rejects_a_bound_outside_the_supported_range(self, mock_db, param, value):
        resp = TestClient(_build_app(mock_db)).get(
            f"/users/2/activities?{param}={value}", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("period", ["week", "month"])
    def test_stats_accepts_the_last_supported_day(self, mock_db, period):
        with patch(
            "modules.activities.activity.service.activity_crud.sum_user_activities_per_timeframe_by_type",
            return_value=[],
        ):
            resp = TestClient(_build_app(mock_db)).get(
                f"/users/1/activities/stats?period={period}&date=9998-12-31", headers={"Authorization": "Bearer x"}
            )
        assert resp.status_code == 200
