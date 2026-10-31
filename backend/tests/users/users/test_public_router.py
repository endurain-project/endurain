from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions


def _build_app(mock_db):
    import core.database as core_db
    import modules.users.users.public_router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/public/users")

    def _mock():
        return None

    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadUsersById:
    @patch("modules.users.users.public_router.users_service.get_public_user")
    def test_success(self, mock_get, mock_db):
        from modules.users.users.schema import UserPublicRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = UserPublicRead(id=1, name="Test User", username="testuser")

        response = client.get("/public/users/id/1")
        assert response.status_code == 200
        assert set(response.json()) == {"id", "name", "username", "city", "photo_path"}

    @patch("modules.users.users.public_router.users_service.get_public_user")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.side_effect = core_exceptions.NotFoundError("User not found")

        response = client.get("/public/users/id/999")
        assert response.status_code == 404
