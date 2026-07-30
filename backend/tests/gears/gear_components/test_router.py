from unittest.mock import patch

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.gears.gear.dependencies as gear_deps
    import modules.gears.gear_components.dependencies as gc_deps
    import modules.gears.gear_components.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/gear_components")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[gear_deps.validate_gear_id] = _mock
    app.dependency_overrides[gc_deps.validate_gear_component_type] = _mock
    app.dependency_overrides[gc_deps.validate_gear_component_id] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadGearComponentTypes:
    def test_types_success(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/gear_components/types", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert "bike" in data
        assert "shoes" in data


class TestReadGearComponents:
    @patch("modules.gears.gear_components.router.gear_components_crud.get_gear_components_user")
    def test_all_success(self, mock_get, mock_db):
        from modules.gears.gear_components.schema import GearComponentRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [
            GearComponentRead(id=1, user_id=1, gear_id=1, type="chain", brand="Shimano", model="Ultegra")
        ]

        response = client.get("/gear_components", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.gears.gear_components.router.gear_components_crud.get_gear_components_user")
    def test_all_empty(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/gear_components", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestReadGearComponentsByGearId:
    @patch("modules.gears.gear_components.router.gear_components_crud.get_components_activity_stats")
    @patch("modules.gears.gear_components.router.gear_components_crud.get_gear_components_user_by_gear_id")
    def test_with_components(self, mock_get_components, mock_get_stats, mock_db):
        from modules.gears.gear_components.schema import GearComponentRead

        client = TestClient(_build_app(mock_db))
        comp = GearComponentRead(id=1, user_id=1, gear_id=1, type="chain", brand="Shimano", model="Ultegra")
        mock_get_components.return_value = [comp]
        mock_get_stats.return_value = {1: {"distance": 1000, "time": 3600}}

        response = client.get("/gear_components/gear_id/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["current_distance"] == 1000

    @patch("modules.gears.gear_components.router.gear_components_crud.get_gear_components_user_by_gear_id")
    def test_no_components(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/gear_components/gear_id/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestCreateGearComponent:
    @patch("modules.gears.gear_components.router.gear_components_crud.create_gear_component")
    def test_create_success(self, mock_create, mock_db):
        from modules.gears.gear_components.schema import GearComponentRead

        client = TestClient(_build_app(mock_db))
        mock_create.return_value = GearComponentRead(
            id=1, user_id=1, gear_id=1, type="chain", brand="Shimano", model="Ultegra"
        )

        response = client.post(
            "/gear_components",
            json={
                "gear_id": 1,
                "type": "chain",
                "brand": "Shimano",
                "model": "Ultegra",
            },
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201


class TestEditGearComponent:
    @patch("modules.gears.gear_components.router.gear_components_crud.edit_gear_component")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.gears.gear_components.schema import GearComponentRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = GearComponentRead(
            id=1, user_id=1, gear_id=1, type="chain", brand="Shimano", model="Ultegra"
        )

        response = client.put(
            "/gear_components",
            json={
                "id": 1,
                "gear_id": 1,
                "type": "chain",
                "brand": "Shimano",
                "model": "Ultegra",
            },
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200

    @patch("modules.gears.gear_components.router.gear_components_crud.edit_gear_component")
    def test_edit_not_found(self, mock_edit, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear component not found",
        )

        response = client.put(
            "/gear_components",
            json={
                "id": 999,
                "gear_id": 1,
                "type": "chain",
                "brand": "Shimano",
                "model": "Ultegra",
            },
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 404

    def test_edit_retired_before_purchase(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.put(
            "/gear_components",
            json={
                "id": 1,
                "gear_id": 1,
                "type": "chain",
                "brand": "Shimano",
                "model": "Ultegra",
                "purchase_date": "2024-06-15",
                "retired_date": "2024-01-15",
            },
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 400


class TestDeleteGearComponent:
    @patch("modules.gears.gear_components.router.gear_components_crud.delete_gear_component")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.return_value = None

        response = client.delete("/gear_components/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204

    @patch("modules.gears.gear_components.router.gear_components_crud.delete_gear_component")
    def test_delete_not_found(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear component not found",
        )

        response = client.delete("/gear_components/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404
