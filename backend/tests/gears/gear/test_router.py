from unittest.mock import patch

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_deps
    import modules.auth.dependencies as auth_deps
    import modules.gears.gear.dependencies as gear_deps
    import modules.gears.gear.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/gears")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_deps.validate_pagination_values_on_query] = _mock
    app.dependency_overrides[gear_deps.validate_gear_id] = _mock
    app.dependency_overrides[gear_deps.validate_gear_type] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadGearsUserAllPagination:
    @patch("modules.gears.gear.router.gears_crud.get_gears_number")
    @patch("modules.gears.gear.router.gears_crud.get_gear_users_with_pagination")
    def test_list_success(self, mock_paginated, mock_number, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_paginated.return_value = [GearRead(id=1, user_id=1, nickname="Bike", gear_type=1)]
        mock_number.return_value = 1

        response = client.get("/gears", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @patch("modules.gears.gear.router.gears_crud.get_gears_number")
    @patch("modules.gears.gear.router.gears_crud.get_gear_users_with_pagination")
    def test_list_empty(self, mock_paginated, mock_number, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_paginated.return_value = []
        mock_number.return_value = 0

        response = client.get("/gears", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadGearById:
    @patch("modules.gears.gear.router.gears_crud.get_gear_components_total_cost")
    @patch("modules.gears.gear.router.gears_crud.get_gear_activity_stats")
    @patch("modules.gears.gear.router.gears_crud.get_gear_user_by_id")
    def test_success(self, mock_get, mock_stats, mock_cost, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        gear = GearRead(id=1, user_id=1, nickname="Bike", gear_type=1, initial_kms=100.0)
        mock_get.return_value = gear
        mock_stats.return_value = {"total_distance": 50000, "total_time": 3600}
        mock_cost.return_value = 1500.0

        response = client.get("/gears/id/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.gears.gear.router.gears_crud.get_gear_user_by_id")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/gears/id/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestReadGearByNickname:
    @patch("modules.gears.gear.router.gears_crud.get_gear_user_contains_nickname")
    def test_contains_success(self, mock_get, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [GearRead(id=1, user_id=1, nickname="Mountain Bike", gear_type=1)]

        response = client.get("/gears/nickname/contains/Mountain", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.gears.gear.router.gears_crud.get_gear_user_by_nickname")
    def test_exact_success(self, mock_get, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = GearRead(id=1, user_id=1, nickname="Bike", gear_type=1)

        response = client.get("/gears/nickname/Bike", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.gears.gear.router.gears_crud.get_gear_user_by_nickname")
    def test_exact_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/gears/nickname/Unknown", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestReadGearByType:
    @patch("modules.gears.gear.router.gears_crud.get_gear_by_type_and_user")
    def test_success(self, mock_get, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [GearRead(id=1, user_id=1, nickname="Bike", gear_type=1)]

        response = client.get("/gears/type/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestCreateGear:
    @patch("modules.gears.gear.router.gears_crud.create_gear")
    def test_create_success(self, mock_create, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_create.return_value = GearRead(id=1, user_id=1, nickname="New Bike", gear_type=1)

        response = client.post(
            "/gears",
            json={"nickname": "New Bike", "gear_type": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201


class TestEditGear:
    @patch("modules.gears.gear.router.gears_crud.edit_gear")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.gears.gear.schema import GearRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = GearRead(id=1, user_id=1, nickname="Updated Bike", gear_type=1)

        response = client.put(
            "/gears",
            json={"id": 1, "nickname": "Updated Bike", "gear_type": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200

    @patch("modules.gears.gear.router.gears_crud.edit_gear")
    def test_edit_not_found(self, mock_edit, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear not found",
        )

        response = client.put(
            "/gears",
            json={"id": 999, "nickname": "Ghost", "gear_type": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 404


class TestDeleteGear:
    @patch("modules.gears.gear.router.gears_crud.delete_gear")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.return_value = None

        response = client.delete("/gears/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204

    @patch("modules.gears.gear.router.gears_crud.delete_gear")
    def test_delete_not_found(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear not found",
        )

        response = client.delete("/gears/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404
