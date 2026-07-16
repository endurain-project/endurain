from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.auth.identity_providers.dependencies as idp_deps
    import modules.auth.identity_providers.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/auth/identity_providers")

    def _mock():
        return None

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[idp_deps.validate_idp_id] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestListIdentityProviders:
    @patch("modules.auth.identity_providers.router.idp_crud.get_all_identity_providers")
    def test_list_success(self, mock_get, mock_db):
        from modules.auth.identity_providers.schema import IdentityProvider

        client = TestClient(_build_app(mock_db))
        now = datetime.now()
        mock_get.return_value = [IdentityProvider(id=1, name="Google", slug="google", created_at=now, updated_at=now)]

        response = client.get("/auth/identity_providers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert len(response.json()) == 1

    @patch("modules.auth.identity_providers.router.idp_crud.get_all_identity_providers")
    def test_list_empty(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/auth/identity_providers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == []


class TestListIdpTemplates:
    @patch("modules.auth.identity_providers.router.idp_utils.get_idp_templates")
    def test_templates_success(self, mock_get, mock_db):
        from modules.auth.identity_providers.schema import IdentityProviderTemplate

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [
            IdentityProviderTemplate(
                template_id="google",
                name="Google",
                provider_type="oidc",
                scopes="openid profile email",
                description="Google OIDC provider",
            )
        ]

        response = client.get("/auth/identity_providers/templates", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestCreateIdentityProvider:
    @patch("modules.auth.identity_providers.router.idp_crud.create_identity_provider")
    def test_create_success(self, mock_create, mock_db):
        from modules.auth.identity_providers.schema import IdentityProvider

        client = TestClient(_build_app(mock_db))
        now = datetime.now()
        mock_create.return_value = IdentityProvider(id=1, name="Google", slug="google", created_at=now, updated_at=now)

        response = client.post(
            "/auth/identity_providers",
            json={
                "name": "Google",
                "slug": "google",
                "client_secret": "very-secret-key-here",
            },
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201


class TestUpdateIdentityProvider:
    @patch("modules.auth.identity_providers.router.idp_crud.update_identity_provider")
    def test_update_success(self, mock_update, mock_db):
        from modules.auth.identity_providers.schema import IdentityProvider

        client = TestClient(_build_app(mock_db))
        now = datetime.now()
        mock_update.return_value = IdentityProvider(
            id=1, name="Google Updated", slug="google", created_at=now, updated_at=now
        )

        response = client.put(
            "/auth/identity_providers/1",
            json={"name": "Google Updated", "slug": "google"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestDeleteIdentityProvider:
    @patch("modules.auth.identity_providers.router.idp_crud.delete_identity_provider")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
