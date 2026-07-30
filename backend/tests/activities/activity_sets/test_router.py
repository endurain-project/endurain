from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_sets.router as router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    app.include_router(router.router, prefix="/activities/{activity_id}")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadActivitySets:
    @patch("modules.activities.activity_sets.router.activity_sets_crud.get_activity_sets")
    def test_read_sets_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/activities/1/sets", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.activities.activity_sets.router.activity_sets_crud.get_activity_sets")
    def test_read_sets_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/activities/999/sets", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None
