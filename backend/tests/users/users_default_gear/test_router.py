from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.users.users_default_gear.router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/user_default_gear")

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadUserDefaultGear:
    @patch("modules.users.users_default_gear.router.user_default_gear_service.get_default_gear")
    def test_read_success(self, mock_get, mock_db):
        from modules.users.users_default_gear.schema import UsersDefaultGearRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = UsersDefaultGearRead(id=1, user_id=1)

        response = client.get("/user_default_gear", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestEditUserDefaultGear:
    @patch("modules.users.users_default_gear.router.user_default_gear_service.edit_default_gear")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.users.users_default_gear.schema import UsersDefaultGearRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = UsersDefaultGearRead(id=1, user_id=1, run_gear_id=2, ride_gear_id=1)

        response = client.patch(
            "/user_default_gear",
            json={"run_gear_id": 2},
            headers={**{"Authorization": "Bearer x"}, "If-Match": '"1"'},
        )
        assert response.status_code == 200


class TestEditNeedsIfMatch:
    def test_an_edit_without_if_match_is_428(self, mock_db):
        response = TestClient(_build_app(mock_db)).patch(
            "/user_default_gear", json={}, headers={"Authorization": "Bearer mock_token"}
        )

        assert response.status_code == 428


class TestReadSendsTheETag:
    @patch("modules.users.users_default_gear.router.user_default_gear_service.get_default_gear")
    def test_the_settings_carry_their_version(self, mock_get, mock_db):
        from modules.users.users_default_gear.schema import UsersDefaultGearRead

        mock_get.return_value = UsersDefaultGearRead(id=1, user_id=1, version=6)

        response = TestClient(_build_app(mock_db)).get("/user_default_gear", headers={"Authorization": "Bearer x"})

        assert response.headers["ETag"] == '"6"'
