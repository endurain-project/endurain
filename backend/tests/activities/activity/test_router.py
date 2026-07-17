from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_dep
    import modules.activities.activity.dependencies as act_dep
    import modules.activities.activity.router as activity_router
    import modules.auth.dependencies as auth_deps
    import modules.gears.gear.dependencies as gear_dep
    import modules.users.users.dependencies as users_dep

    app = FastAPI()
    app.include_router(activity_router.router, prefix="/activities")

    def _mock():
        return None

    def _uid():
        return 1

    for dep in [
        auth_deps.check_scopes,
        auth_deps.get_sub_from_access_token,
        auth_deps.get_user_id_from_auth,
        auth_deps.check_auth_scopes,
        core_dep.validate_pagination_values,
        users_dep.validate_user_id,
        act_dep.validate_week_number,
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


class TestReadActivitiesNumber:
    def test_number_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/number", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200 and resp.json() == 1

    def test_number_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities") as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get("/activities/number", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200 and resp.json() == 0


class TestReadWeek:
    def test_week_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/week/0", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_week_none(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/week/0", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() is None


class TestWeekStats:
    def test_stats_success(self, mock_db):
        with (
            patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m,
            patch("modules.activities.activity.router.activities_stats.calculate_activity_stats") as s,
        ):
            m.return_value = [_valid_activity()]
            s.return_value = {"bogus": {}}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thisweek/stats", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_stats_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thisweek/stats", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200


class TestMonthNumber:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = [_valid_activity(), _valid_activity(id=2)]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thismonth/number", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() == 2

    def test_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thismonth/number", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() == 0


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
            assert resp.status_code == 200 and resp.json() is None


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
            patch("modules.activities.activity.router.activities_crud.delete_activity"),
            patch("modules.activities.activity.router.activity_event_publishers") as mock_pub,
        ):
            g.return_value = act
            resp = TestClient(_build_app(mock_db)).delete("/activities/1/delete", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200
            # The route publishes the fact; subsystems (thumbnails) react on their own.
            mock_pub.publish_activity_deleted.assert_called_once()
            assert mock_pub.publish_activity_deleted.call_args.args[0] == 1

    def test_not_found(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_activity_by_id_from_user_id") as g:
            g.return_value = None
            resp = TestClient(_build_app(mock_db)).delete(
                "/activities/999/delete", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 404


class TestTypes:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_distinct_activity_types_for_user") as m:
            m.return_value = {1: "Run"}
            resp = TestClient(_build_app(mock_db)).get("/activities/types", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200


class TestGear:
    def test_list(self, mock_db):
        with (
            patch("modules.activities.activity.router.activities_crud.get_gear_activities_count_by_user_id") as c,
            patch(
                "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination"
            ) as mock_list,
        ):
            c.return_value = 1
            mock_list.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/gear/1/list", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_activities(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id"
        ) as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get("/activities/gear/1", headers={"Authorization": "Bearer x"})
            assert resp.status_code == 200

    def test_number(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id"
        ) as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/gear/1/number", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() == 1

    def test_number_empty(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id"
        ) as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/gear/1/number", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200 and resp.json() == 0


class TestContainName:
    def test_success(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_activities_if_contains_name") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/name/contains/Morning", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200


class TestFollowing:
    def test_other_user_forbidden(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/activities/user/2/followed/page_number/1/num_records/10", headers={"Authorization": "Bearer x"}
        )
        assert resp.status_code == 403


class TestPagination:
    def test_user(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_with_pagination") as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/page_number/1/num_records/10", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_gear(self, mock_db):
        with patch(
            "modules.activities.activity.router.activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination"
        ) as m:
            m.return_value = [_valid_activity()]
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/gear/1/page_number/1/num_records/10", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200


class TestThisMonthStats:
    def test_success(self, mock_db):
        with (
            patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as g,
            patch("modules.activities.activity.router.activities_stats.calculate_activity_stats") as s,
        ):
            g.return_value = [_valid_activity()]
            s.return_value = {}
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thismonth/stats", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200

    def test_empty(self, mock_db):
        with patch("modules.activities.activity.router.activities_crud.get_user_activities_per_timeframe") as m:
            m.return_value = None
            resp = TestClient(_build_app(mock_db)).get(
                "/activities/user/1/thismonth/stats", headers={"Authorization": "Bearer x"}
            )
            assert resp.status_code == 200
