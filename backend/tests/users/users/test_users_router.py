"""Tests for the users management router endpoints."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_dependencies
import auth.identity_service as auth_identity_service
import core.apprise as core_apprise
import core.database as core_database
import core.dependencies as core_dependencies
import users.users.dependencies as users_dependencies


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def auth_app(mock_db):
    app = FastAPI()
    from users.users.router import router

    app.include_router(router, prefix="/users")

    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_database.get_db] = lambda: mock_db

    return app


def _make_mock_user(user_id, **overrides):
    """Build a mock user object compatible with UsersRead.model_validate."""
    user = MagicMock()
    user.id = user_id
    user.name = overrides.get("name", f"User {user_id}")
    user.username = overrides.get("username", f"user{user_id}")
    user.email = overrides.get("email", f"user{user_id}@example.com")
    user.city = overrides.get("city")
    user.birthdate = overrides.get("birthdate")
    user.preferred_language = overrides.get("preferred_language", "en")
    user.gender = overrides.get("gender", "unspecified")
    user.units = overrides.get("units", "metric")
    user.height = overrides.get("height")
    user.max_heart_rate = overrides.get("max_heart_rate")
    user.first_day_of_week = overrides.get("first_day_of_week", "monday")
    user.currency = overrides.get("currency", "euro")
    user.photo_path = overrides.get("photo_path")
    user.active = overrides.get("active", True)
    user.access_type = overrides.get("access_type", "regular")
    user.mfa_enabled = overrides.get("mfa_enabled", False)
    user.email_verified = overrides.get("email_verified", True)
    user.pending_admin_approval = overrides.get("pending_admin_approval", False)
    user.external_auth_count = overrides.get("external_auth_count", 0)
    return user


class TestReadUsersAllPagination:
    @patch("users.users.router.users_crud.get_users_number")
    @patch("users.users.router.users_crud.get_users_with_pagination")
    def test_success(
        self,
        mock_get_paginated,
        mock_get_number,
        mock_db,
        auth_app,
    ):
        mock_identity_service = MagicMock()
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        auth_app.dependency_overrides[core_dependencies.validate_pagination_values_on_query] = lambda: None
        client = TestClient(auth_app)

        mock_get_number.return_value = 3
        mock_get_paginated.return_value = [
            _make_mock_user(1, name="Alice", email="alice@example.com"),
            _make_mock_user(2, name="Bob", email="bob@example.com"),
        ]
        mock_identity_service.get_identity_link_counts_for_users.return_value = {}
        mock_identity_service.get_mfa_enabled_for_users.return_value = {}

        response = client.get("/users?page_number=1&num_records=10")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["num_records"] == 10
        assert data["page_number"] == 1
        assert len(data["records"]) == 2
        assert data["records"][0]["name"] == "Alice"
        assert data["records"][1]["name"] == "Bob"

    @patch("users.users.router.users_crud.get_users_number")
    @patch("users.users.router.users_crud.get_users_with_pagination")
    def test_filter_external_auth_false(
        self,
        mock_get_paginated,
        mock_get_number,
        mock_db,
        auth_app,
    ):
        mock_identity_service = MagicMock()
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        auth_app.dependency_overrides[core_dependencies.validate_pagination_values_on_query] = lambda: None
        client = TestClient(auth_app)

        mock_get_number.return_value = 3
        mock_get_paginated.return_value = [
            _make_mock_user(1, name="Alice"),
            _make_mock_user(2, name="Bob"),
        ]
        # Alice (id=1) has 1 IdP link; Bob (id=2) has none
        mock_identity_service.get_identity_link_counts_for_users.return_value = {1: 1}
        mock_identity_service.get_mfa_enabled_for_users.return_value = {}

        response = client.get("/users?show_external_auth=false")

        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) == 1
        assert data["records"][0]["name"] == "Bob"

    @patch("users.users.router.users_crud.get_users_number")
    @patch("users.users.router.users_crud.get_users_with_pagination")
    def test_filter_local_auth_false(
        self,
        mock_get_paginated,
        mock_get_number,
        mock_db,
        auth_app,
    ):
        mock_identity_service = MagicMock()
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        auth_app.dependency_overrides[core_dependencies.validate_pagination_values_on_query] = lambda: None
        client = TestClient(auth_app)

        mock_get_number.return_value = 2
        mock_get_paginated.return_value = [
            _make_mock_user(1, name="Alice"),
            _make_mock_user(2, name="Bob"),
        ]
        # Alice (id=1) has 1 IdP link; Bob (id=2) has none
        mock_identity_service.get_identity_link_counts_for_users.return_value = {1: 1}
        mock_identity_service.get_mfa_enabled_for_users.return_value = {}

        response = client.get("/users?show_local_auth=false")

        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) == 1
        assert data["records"][0]["name"] == "Alice"


class TestReadUsersContainUsername:
    @patch("users.users.router.users_crud.get_user_by_username")
    def test_success(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = [
            _make_mock_user(1, username="testuser1"),
            _make_mock_user(2, username="testuser2"),
        ]

        response = client.get("/users/username/contains/test")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["username"] == "testuser1"

    @patch("users.users.router.users_crud.get_user_by_username")
    def test_empty(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = []

        response = client.get("/users/username/contains/unknown")

        assert response.status_code == 200
        assert response.json() == []


class TestReadUsersUsername:
    @patch("users.users.router.users_crud.get_user_by_username")
    def test_found(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = _make_mock_user(1, name="Found User")

        response = client.get("/users/username/founduser")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Found User"

    @patch("users.users.router.users_crud.get_user_by_username")
    def test_not_found(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = None

        response = client.get("/users/username/nonexistent")

        assert response.status_code == 200
        assert response.json() is None


class TestReadUsersEmail:
    @patch("users.users.router.users_crud.get_user_by_email")
    def test_found(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = _make_mock_user(1, email="test@example.com")

        response = client.get("/users/email/test@example.com")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"

    @patch("users.users.router.users_crud.get_user_by_email")
    def test_not_found(self, mock_get, mock_db, auth_app):
        client = TestClient(auth_app)

        mock_get.return_value = None

        response = client.get("/users/email/unknown@example.com")

        assert response.status_code == 200
        assert response.json() is None


class TestReadUsersId:
    @patch("users.users.router.users_crud.get_user_by_id")
    def test_found(self, mock_get, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_get.return_value = _make_mock_user(42, name="ID User")

        response = client.get("/users/id/42")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["name"] == "ID User"

    @patch("users.users.router.users_crud.get_user_by_id")
    def test_not_found(self, mock_get, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_get.return_value = None

        response = client.get("/users/id/999")

        assert response.status_code == 200
        assert response.json() is None


class TestCreateUser:
    @patch("users.users.router.users_crud.create_user")
    @patch("users.users.router.users_utils.create_user_default_data")
    def test_success(self, mock_default_data, mock_create, mock_db, auth_app):
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: MagicMock()
        client = TestClient(auth_app)

        mock_create.return_value = _make_mock_user(
            1,
            name="New User",
            username="newuser",
            email="new@example.com",
        )

        response = client.post(
            "/users",
            json={
                "name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "active": True,
                "access_type": "regular",
                "password": "testpass123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New User"
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        mock_default_data.assert_called_once_with(1, ANY, mock_db)


class TestUploadUserImage:
    @patch("users.users.router.users_utils.save_user_image_file", new_callable=AsyncMock)
    @patch("users.users.router.users_crud.get_user_by_id")
    def test_success(self, mock_get, mock_save, mock_db, auth_app):
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: MagicMock()
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_user = MagicMock()
        mock_user.photo_path = "data/user_images/1.jpg"
        mock_get.return_value = mock_user

        response = client.post(
            "/users/1/image",
            files={"file": ("avatar.jpg", b"fake-image-data", "image/jpeg")},
        )

        assert response.status_code == 201
        assert response.json() == "data/user_images/1.jpg"
        mock_save.assert_awaited_once()


class TestEditUser:
    @patch("users.users.router.users_crud.edit_user", new_callable=AsyncMock)
    def test_success(self, mock_edit, mock_db, auth_app):
        mock_identity_service = MagicMock()
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        mock_edit.return_value = _make_mock_user(
            1,
            name="Updated User",
            username="updated",
            email="updated@example.com",
        )
        mock_identity_service.get_identity_link_counts_for_users.return_value = {1: 2}
        mock_identity_service.get_mfa_enabled_for_users.return_value = {}

        response = client.put(
            "/users/1",
            json={
                "id": 1,
                "name": "Updated User",
                "username": "updated",
                "email": "updated@example.com",
                "active": True,
                "access_type": "regular",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated User"
        assert data["external_auth_count"] == 2
        mock_edit.assert_awaited_once()


class TestApproveUser:
    @patch("users.users.router.users_crud.approve_user")
    @patch("users.users.router.sign_up_tokens_utils.send_sign_up_approval_email", new_callable=AsyncMock)
    def test_success(self, mock_send_email, mock_approve, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        auth_app.dependency_overrides[core_apprise.get_email_service] = lambda: MagicMock()
        client = TestClient(auth_app)

        response = client.put("/users/1/approve")

        assert response.status_code == 200
        assert response.json() == {"message": "User ID 1 approved successfully."}
        mock_approve.assert_called_once_with(1, mock_db)
        mock_send_email.assert_awaited_once()


class TestEditUserPassword:
    def test_success(self, mock_db, auth_app):
        mock_identity_service = MagicMock()
        auth_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        response = client.put(
            "/users/1/password",
            json={"password": "newpassword123"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "User ID 1 password updated successfully"}
        mock_identity_service.change_managed_user_password.assert_called_once_with(
            1,
            "newpassword123",
        )


class TestDeleteUserPhoto:
    @patch("users.users.router.users_crud.update_user_photo", new_callable=AsyncMock)
    def test_success(self, mock_update, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        response = client.delete("/users/1/photo")

        assert response.status_code == 204
        mock_update.assert_awaited_once_with(1, mock_db)


class TestDeleteUser:
    @patch("users.users.router.users_crud.delete_user", new_callable=AsyncMock)
    def test_success(self, mock_delete, mock_db, auth_app):
        auth_app.dependency_overrides[users_dependencies.validate_user_id] = lambda: None
        client = TestClient(auth_app)

        response = client.delete("/users/1")

        assert response.status_code == 204
        mock_delete.assert_awaited_once_with(1, mock_db)
