from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity.dependencies as act_dep
    import modules.activities.activity.router as activity_router
    import modules.auth.dependencies as auth_deps
    import modules.gears.gear.dependencies as gear_dep
    import modules.users.users.dependencies as users_dep

    app = FastAPI()
    # Same boundary the production app registers, so a DomainError raised by the
    # service is asserted as the response a client actually receives.
    core_exceptions.register_exception_handlers(app)
    app.include_router(activity_router.router, prefix="/activities")

    def _mock():
        return None

    for dep in [
        auth_deps.check_scopes,
        auth_deps.get_sub_from_access_token,
        auth_deps.get_user_id_from_auth,
        auth_deps.check_auth_scopes,
        users_dep.validate_user_id,
        act_dep.validate_activity_type,
        act_dep.validate_sort_by,
        act_dep.validate_sort_order,
        act_dep.validate_activity_id,
        gear_dep.validate_gear_id,
    ]:
        app.dependency_overrides[dep] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


def _valid_activity(**kw):
    from modules.activities.activity.schema import Activity

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
    return Activity(**data)


def _feed_entry(**kw):
    from modules.activities.activity.contracts import ActivityFeedEntry

    activity = _valid_activity(**kw)
    return ActivityFeedEntry(
        activity=activity,
        cursor_start_time=datetime(2024, 1, 15, 8, tzinfo=UTC),
        cursor_id=activity.id or 1,
    )


class TestListOwnActivities:
    """The list endpoint carries its own total, so no second /count call."""

    def test_list_returns_page_envelope(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activities_crud.count_user_activities", return_value=1),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities", headers={"Authorization": "Bearer x"})

            assert resp.status_code == 200
            body = resp.json()
            assert len(body["items"]) == 1
            assert body["total"] == 1
            assert body["page"] == 1
            assert body["next"] is None

    def test_next_points_to_the_following_page(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activities_crud.count_user_activities", return_value=45),
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
            patch("modules.activities.activity.service.activities_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activities_crud.count_user_activities", return_value=40),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities?page_number=2&num_records=20", headers={"Authorization": "Bearer x"}
            )

            assert resp.json()["next"] is None

    def test_empty_result_is_a_page_not_a_bare_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activities_crud.count_user_activities", return_value=0),
        ):
            m.return_value = None
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
        with patch("modules.activities.activity.service.activities_crud.get_distinct_activity_types_for_user") as m:
            m.return_value = {1: "Run"}
            resp = TestClient(_build_app(mock_db)).get("/activities/types", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200


class TestFeed:
    def test_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activities_crud.get_following_feed_after") as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = [_feed_entry()]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert len(resp.json()["items"]) == 1

    def test_last_slice_has_no_next_cursor(self, mock_db):
        """A short slice means the end; emitting a cursor would loop the client."""
        with (
            patch("modules.activities.activity.service.followers_integration") as f,
            patch("modules.activities.activity.service.activities_crud.get_following_feed_after") as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = [_feed_entry()]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})
            assert resp.json()["next_cursor"] is None

    def test_hidden_start_time_still_emits_a_next_cursor(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_integration") as followers,
            patch("modules.activities.activity.service.activities_crud.get_following_feed_after") as get_feed,
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


class TestGear:
    def test_list(self, mock_db):
        with patch(
            "modules.activities.activity.service.activities_crud.get_user_activities_by_gear_id_and_user_id"
        ) as m:
            m.return_value = [_valid_activity()]
            with patch(
                "modules.activities.activity.service.activities_crud.get_gear_activities_count_by_user_id",
                return_value=1,
            ):
                resp = TestClient(_build_app(mock_db)).get("/activities/gears/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    def test_list_paginated(self, mock_db):
        with patch(
            "modules.activities.activity.service.activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination"
        ) as m:
            m.return_value = [_valid_activity()]
            with patch(
                "modules.activities.activity.service.activities_crud.get_gear_activities_count_by_user_id",
                return_value=1,
            ):
                resp = TestClient(_build_app(mock_db)).get(
                    "/activities/gears/1?page_number=1&num_records=10", headers={"Authorization": "Bearer x"}
                )
            assert resp.status_code == 200

    def test_count_endpoint_is_gone(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get("/activities/gears/1/count", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 404


class TestUserStats:
    @pytest.fixture(autouse=True)
    def _stub_user_local_today(self):
        """Pin the fallback anchor.

        Without a ``date`` query param the service resolves today in the
        requester's timezone, which is a DB read the mocked session cannot serve.
        """
        from datetime import date

        with patch(
            "modules.activities.activity.service.users_integration_service.local_today",
            return_value=date(2026, 3, 12),
        ):
            yield

    def test_week(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_per_timeframe") as g,
            patch("modules.activities.activity.service.activities_stats.calculate_activity_stats") as s,
        ):
            g.return_value = [_valid_activity()]
            s.return_value = {}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/users/1/stats?period=week", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_month(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_per_timeframe") as g,
            patch("modules.activities.activity.service.activities_stats.calculate_activity_stats") as s,
        ):
            g.return_value = [_valid_activity()]
            s.return_value = {}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/users/1/stats?period=month", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_empty(self, mock_db):
        with patch("modules.activities.activity.service.activities_crud.get_user_activities_per_timeframe") as g:
            g.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/users/1/stats?period=week", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_invalid_period(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/activities/users/1/stats?period=bogus", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 422


class TestListUserActivities:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.get_user_activities_with_pagination") as m,
            patch("modules.activities.activity.service.activities_crud.count_user_activities", return_value=1),
        ):
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/users/2", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert resp.json()["total"] == 1


class TestReadByID:
    def test_success(self, mock_db):
        with patch(
            "modules.activities.activity.service.activities_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).get("/activities/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_not_found(self, mock_db):
        with patch(
            "modules.activities.activity.service.activities_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get("/activities/999", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 404


class TestEdit:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.service.activities_crud.edit_activity") as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={"Authorization": "Bearer x"},
                json={"name": "Run", "activity_type": 1, "visibility": 2},
            )
            assert resp.status_code == 200

    def test_partial_update_single_field(self, mock_db):
        # A true PATCH: only the sent field is forwarded to crud.
        with patch("modules.activities.activity.service.activities_crud.edit_activity") as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={"Authorization": "Bearer x"},
                json={"visibility": 2},
            )
            assert resp.status_code == 200

    def test_path_id_is_passed_to_crud(self, mock_db):
        # The activity id comes from the path (not the body) and is passed to crud.
        with patch("modules.activities.activity.service.activities_crud.edit_activity") as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/7",
                headers={"Authorization": "Bearer x"},
                json={"name": "Run", "visibility": 2},
            )
            assert resp.status_code == 200
            # edit_activity(token_user_id, activity_id, activity_attributes, db)
            assert m.call_args.args[1] == 7

    def test_rejects_id_in_body(self, mock_db):
        # id is not a body field; extra="forbid" rejects it.
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities/1",
            headers={"Authorization": "Bearer x"},
            json={"id": 1, "name": "Run"},
        )
        assert resp.status_code == 422


class TestEditVisibility:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.service.activities_crud.edit_user_activities_visibility") as m:
            m.return_value = [1, 2, 3, 4, 5]
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities", json={"visibility": 1}, headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json()["updated"] == 5
            assert m.call_args.args[1] == 1

    def test_rejects_an_out_of_range_visibility(self, mock_db):
        """Validation moved from a path dependency into the body schema."""
        resp = TestClient(_build_app(mock_db)).patch(
            "/activities", json={"visibility": 9}, headers={"Authorization": "Bearer x"}
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


class TestDelete:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.service.activities_crud.delete_activity") as mock_del,
            patch("modules.activities.activity.service.activity_event_publishers") as mock_pub,
        ):
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers={"Authorization": "Bearer x"})
            # 204 with no body: the resource is gone, and the status says so.
            assert resp.status_code == 204
            assert resp.content == b""
            # Ownership is in the delete's WHERE clause, so the route passes the
            # requester through instead of pre-fetching (no read-then-delete gap).
            assert mock_del.call_args.args[0] == 1
            assert mock_del.call_args.args[1] == mock_pub.publish_activity_deleted.call_args.args[1]
            # The delete is staged (commit=False) and the publish owns the single
            # commit, so the row delete + activity.deleted outbox row are atomic.
            assert mock_del.call_args.kwargs.get("commit") is False
            mock_pub.publish_activity_deleted.assert_called_once()
            assert mock_pub.publish_activity_deleted.call_args.args[0] == 1
            assert mock_pub.publish_activity_deleted.call_args.kwargs.get("commit") is not None

    def test_not_found(self, mock_db):
        """A missing activity — or one owned by someone else — 404s from the CRUD."""
        with (
            patch("modules.activities.activity.service.activities_crud.delete_activity") as mock_del,
            patch("modules.activities.activity.service.activity_event_publishers") as mock_pub,
        ):
            mock_del.side_effect = HTTPException(status_code=404, detail="Activity with id 999 not found")
            resp = TestClient(_build_app(mock_db)).delete("/activities/999", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 404
            mock_pub.publish_activity_deleted.assert_not_called()


class TestActivityConcurrency:
    """PATCH used to be last-writer-wins: the loser's edit vanished silently."""

    def test_read_returns_an_etag(self, mock_db):
        with patch("modules.activities.activity.service.get_activity") as m:
            m.return_value = _valid_activity()
            m.return_value.version = 3
            resp = TestClient(_build_app(mock_db)).get("/activities/1", headers={"Authorization": "Bearer x"})

        assert resp.headers["ETag"] == '"3"'

    def test_patch_without_if_match_still_works(self, mock_db):
        """Making the header mandatory would break every existing client."""
        with patch("modules.activities.activity.service.activities_crud") as crud:
            crud.edit_activity.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1", json={"name": "x"}, headers={"Authorization": "Bearer x"}
            )

        assert resp.status_code == 200

    def test_patch_with_a_stale_if_match_is_refused(self, mock_db):
        with patch("modules.activities.activity.service.activities_crud") as crud:
            current = _valid_activity()
            current.version = 5
            crud.get_activity_by_id_from_user_id.return_value = current
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                json={"name": "x"},
                headers={"Authorization": "Bearer x", "If-Match": '"4"'},
            )

        assert resp.status_code == 412
        crud.edit_activity.assert_not_called()

    def test_patch_with_a_current_if_match_succeeds(self, mock_db):
        with patch("modules.activities.activity.service.activities_crud") as crud:
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

        with patch("modules.activities.activity.service.activities_crud") as crud:
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
