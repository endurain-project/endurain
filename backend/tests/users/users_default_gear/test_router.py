from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.users.users_default_gear.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/user_default_gear")

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadUserDefaultGear:
    @patch("modules.users.users_default_gear.router.user_default_gear_crud.get_user_default_gear_by_user_id")
    def test_read_success(self, mock_get, mock_db):
        from modules.users.users_default_gear.schema import UsersDefaultGearRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = UsersDefaultGearRead(id=1, user_id=1)

        response = client.get("/user_default_gear", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestEditUserDefaultGear:
    @patch("modules.users.users_default_gear.router.user_default_gear_crud.edit_user_default_gear")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.users.users_default_gear.schema import UsersDefaultGearRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = UsersDefaultGearRead(id=1, user_id=1, run_gear_id=2, ride_gear_id=1)

        response = client.put(
            "/user_default_gear",
            json={"id": 1, "user_id": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200
