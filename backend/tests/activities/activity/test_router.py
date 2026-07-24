from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity.dependencies as act_dep
    import modules.activities.activity.router as activity_router
    import modules.auth.dependencies as auth_deps
    import modules.gears.gear.dependencies as gear_dep
    import modules.users.users.dependencies as users_dep

    app = FastAPI()
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
        act_dep.validate_visibility,
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


class TestListOwnActivities:
    def test_list(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_with_pagination") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    def test_count(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.count_user_activities") as m:
            m.return_value = 1
            resp = TestClient(_build_app(mock_db)).get("/activities/count", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200 and resp.json() == {"count": 1}

    def test_count_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.count_user_activities") as m:
            m.return_value = 0
            resp = TestClient(_build_app(mock_db)).get("/activities/count", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200 and resp.json() == {"count": 0}


class TestTypes:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_distinct_activity_types_for_user") as m:
            m.return_value = {1: "Run"}
            resp = TestClient(_build_app(mock_db)).get("/activities/types", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200


class TestFeed:
    def test_list(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_service") as f,
            patch(
                "modules.activities.activity.router.activities_crud.get_user_following_activities_with_pagination"
            ) as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/feed", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_count(self, mock_db):
        with (
            patch("modules.activities.activity.service.followers_service") as f,
            patch("modules.activities.activity.router.activities_crud.count_user_following_activities") as m,
        ):
            f.list_accepted_followee_ids.return_value = [5]
            m.return_value = 2
            resp = TestClient(_build_app(mock_db)).get("/activities/feed/count", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200 and resp.json() == {"count": 2}


class TestGear:
    def test_list(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id"
        ) as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/gears/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_list_paginated(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination"
        ) as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/gears/1?page_number=1&num_records=10", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_count(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_gear_activities_count_by_user_id") as m:
            m.return_value = 3
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/gears/1/count", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() == {"count": 3}


class TestUserStats:
    def test_week(self, mock_db):
        with (
            patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as g,
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
            patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as g,
            patch("modules.activities.activity.service.activities_stats.calculate_activity_stats") as s,
        ):
            g.return_value = [_valid_activity()]
            s.return_value = {}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/users/1/stats?period=month", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as g:
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
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_with_pagination") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/users/2", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200


class TestReadByID:
    def test_success(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).get("/activities/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_not_found(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_activity_by_id_from_user_id_or_has_visibility"
        ) as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get("/activities/999", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 404


class TestEdit:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.edit_activity") as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={"Authorization": "Bearer x"},
                json={"name": "Run", "activity_type": 1, "visibility": 2},
            )
            assert resp.status_code == 200

    def test_partial_update_single_field(self, mock_db):
        # A true PATCH: only the sent field is forwarded to crud.
        with patch("modules.activities.activity.router.activities_crud.edit_activity") as m:
            m.return_value = _valid_activity()
            resp = TestClient(_build_app(mock_db)).patch(
                "/activities/1",
                headers={"Authorization": "Bearer x"},
                json={"visibility": 2},
            )
            assert resp.status_code == 200

    def test_path_id_is_passed_to_crud(self, mock_db):
        # The activity id comes from the path (not the body) and is passed to crud.
        with patch("modules.activities.activity.router.activities_crud.edit_activity") as m:
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
        with patch("modules.activities.activity.router.activities_crud.edit_user_activities_visibility") as m:
            m.return_value = 5
            resp = TestClient(_build_app(mock_db)).put(
                "/activities/visibility/1", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json()["updated"] == 5


class TestDelete:
    def test_success(self, mock_db):
        act = MagicMock()
        with (
            patch("modules.activities.activity.router.activities_crud.get_activity_by_id_from_user_id") as g,
            patch("modules.activities.activity.router.activities_crud.delete_activity") as mock_del,
            patch("modules.activities.activity.router.activity_event_publishers") as mock_pub,
        ):
            g.return_value = act
            resp = TestClient(_build_app(mock_db)).delete("/activities/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            # The delete is staged (commit=False) and the publish owns the single
            # commit, so the row delete + activity.deleted outbox row are atomic.
            assert mock_del.call_args.kwargs.get("commit") is False
            mock_pub.publish_activity_deleted.assert_called_once()
            assert mock_pub.publish_activity_deleted.call_args.args[0] == 1
            assert mock_pub.publish_activity_deleted.call_args.kwargs.get("commit") is not None

    def test_not_found(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_activity_by_id_from_user_id") as g:
            g.return_value = None
            resp = TestClient(_build_app(mock_db)).delete("/activities/999", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 404
