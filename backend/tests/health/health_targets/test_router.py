from unittest.mock import MagicMock, patch

import core.exceptions as core_exceptions
import modules.health.health_targets.models as health_targets_models


class TestReadHealthTargetsAll:
    """
    Test suite for read_health_targets_all endpoint.
    """

    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets")
    def test_read_health_targets_all_success(self, mock_get_targets, fast_api_client, fast_api_app):
        """
        Test successful retrieval of health targets.
        """
        # Arrange
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_targets.id = 1
        mock_targets.user_id = 1
        mock_targets.version = 1
        mock_targets.weight = 75.5
        mock_targets.steps = 10000
        mock_targets.sleep = 28800
        mock_targets.fasting = None
        mock_targets.water_ml = None
        mock_targets.poop_count = None

        mock_get_targets.return_value = mock_targets

        # Act
        response = fast_api_client.get(
            "/health/targets/",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.5
        assert data["steps"] == 10000
        assert data["sleep"] == 28800

    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets")
    def test_read_health_targets_all_not_found(self, mock_get_targets, fast_api_client, fast_api_app):
        """
        Test retrieval when user has no health targets.
        """
        # Arrange
        mock_get_targets.return_value = None

        # Act
        response = fast_api_client.get(
            "/health/targets/",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        assert response.json() is None

    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets")
    def test_read_health_targets_all_partial_data(self, mock_get_targets, fast_api_client, fast_api_app):
        """
        Test retrieval when health targets have partial data.
        """
        # Arrange
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_targets.id = 1
        mock_targets.user_id = 1
        mock_targets.version = 1
        mock_targets.weight = 75.5
        mock_targets.steps = None
        mock_targets.sleep = None
        mock_targets.fasting = None
        mock_targets.water_ml = None
        mock_targets.poop_count = None

        mock_get_targets.return_value = mock_targets

        # Act
        response = fast_api_client.get(
            "/health/targets/",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.5
        assert data["steps"] is None
        assert data["sleep"] is None


class TestUpdateNeedsIfMatch:
    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_an_update_without_if_match_is_428(self, mock_update, fast_api_client):
        response = fast_api_client.patch(
            "/health/targets/", json={"weight": 80.0}, headers={"Authorization": "Bearer mock_token"}
        )

        assert response.status_code == 428
        mock_update.assert_not_called()


class TestUpdateHealthTargets:
    """
    Test suite for update_health_targets endpoint.
    """

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_update_health_targets_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful update of health targets.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.version = 1
        mock_updated_targets.weight = 80.0
        mock_updated_targets.steps = 12000
        mock_updated_targets.sleep = 32400
        mock_updated_targets.fasting = None
        mock_updated_targets.water_ml = None
        mock_updated_targets.poop_count = None

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.patch(
            "/health/targets/",
            json={
                "weight": 80.0,
                "steps": 12000,
                "sleep": 32400,
            },
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 80.0
        assert data["steps"] == 12000
        assert data["sleep"] == 32400

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_update_health_targets_partial_update(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test partial update of health targets.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.version = 1
        mock_updated_targets.weight = 75.0
        mock_updated_targets.steps = 10000
        mock_updated_targets.sleep = 28800
        mock_updated_targets.fasting = None
        mock_updated_targets.water_ml = None
        mock_updated_targets.poop_count = None

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.patch(
            "/health/targets/",
            json={
                "weight": 75.0,
            },
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.0

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_update_health_targets_clear_values(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test clearing health target values by setting to null.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.version = 1
        mock_updated_targets.weight = None
        mock_updated_targets.steps = None
        mock_updated_targets.sleep = None
        mock_updated_targets.fasting = None
        mock_updated_targets.water_ml = None
        mock_updated_targets.poop_count = None

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.patch(
            "/health/targets/",
            json={
                "weight": None,
                "steps": None,
                "sleep": None,
            },
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] is None
        assert data["steps"] is None
        assert data["sleep"] is None

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_update_health_targets_not_found(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test update when health targets not found.
        """
        # Arrange
        mock_edit.side_effect = core_exceptions.NotFoundError("Health targets not found")

        # Act
        response = fast_api_client.patch(
            "/health/targets/",
            json={
                "weight": 80.0,
            },
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 404

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_update_health_targets_with_all_fields(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test update with all fields provided.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.version = 1
        mock_updated_targets.weight = 85.5
        mock_updated_targets.steps = 15000
        mock_updated_targets.sleep = 36000
        mock_updated_targets.fasting = None
        mock_updated_targets.water_ml = None
        mock_updated_targets.poop_count = None

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.patch(
            "/health/targets/",
            json={
                "weight": 85.5,
                "steps": 15000,
                "sleep": 36000,
            },
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 85.5
        assert data["steps"] == 15000
        assert data["sleep"] == 36000


class TestReadSendsTheETag:
    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets")
    def test_the_targets_carry_their_version(self, mock_get_targets, fast_api_client):
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_targets.id = 1
        mock_targets.user_id = 1
        mock_targets.version = 4
        for field in ("weight", "steps", "sleep", "fasting", "water_ml", "poop_count"):
            setattr(mock_targets, field, None)
        mock_get_targets.return_value = mock_targets

        response = fast_api_client.get("/health/targets/", headers={"Authorization": "Bearer mock_token"})

        assert response.headers["ETag"] == '"4"'


class TestTargetsScopes:
    """The targets routes require the health targets scopes, not the generic health ones."""

    @staticmethod
    def _client(mock_db, scopes: set[str]):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.database as core_db
        import modules.auth.dependencies as auth_deps
        import modules.health.health_targets.router as targets_router

        app = FastAPI()
        core_exceptions.register_exception_handlers(app)
        app.include_router(targets_router.router, prefix="/health/targets")
        app.dependency_overrides[auth_deps.get_access_token] = lambda: "token"
        app.dependency_overrides[core_db.get_db] = lambda: mock_db
        principal = MagicMock(user_id=1, scopes=frozenset(scopes))
        return TestClient(app), patch.object(auth_deps, "_resolve_and_cache_principal", return_value=principal)

    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets", return_value=None)
    def test_read_with_only_health_read_is_refused(self, _get, mock_db):
        client, principal = self._client(mock_db, {"health:read", "health:write"})

        with principal:
            response = client.get("/health/targets")

        assert response.status_code == 403

    @patch("modules.health.health_targets.router.health_targets_service.get_health_targets", return_value=None)
    def test_read_with_health_targets_read_is_allowed(self, _get, mock_db):
        client, principal = self._client(mock_db, {"health_targets:read"})

        with principal:
            response = client.get("/health/targets")

        assert response.status_code == 200

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_write_with_only_health_write_is_refused(self, mock_update, mock_db):
        client, principal = self._client(mock_db, {"health:read", "health:write", "health_targets:read"})

        with principal:
            response = client.patch("/health/targets", json={"steps": 1}, headers={"If-Match": '"1"'})

        assert response.status_code == 403
        mock_update.assert_not_called()

    @patch("modules.health.health_targets.router.health_targets_service.update_health_targets")
    def test_write_with_health_targets_write_is_allowed(self, mock_update, mock_db):
        import modules.health.health_targets.schema as health_targets_schema

        mock_update.return_value = health_targets_schema.HealthTargetsRead(id=1, user_id=1, version=2, steps=1)
        client, principal = self._client(mock_db, {"health_targets:write"})

        with principal:
            response = client.patch("/health/targets", json={"steps": 1}, headers={"If-Match": '"1"'})

        assert response.status_code == 200
        mock_update.assert_called_once()
