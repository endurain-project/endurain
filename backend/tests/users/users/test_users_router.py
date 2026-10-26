"""Tests for the users management router endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.constants as auth_constants
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_service as auth_identity_service
import modules.auth.principal as auth_principal
import modules.users.users.schema as users_schema

_SERVICE = "modules.users.users.router.users_service"
_PHOTO = "modules.users.users.router.users_photo_service"


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def identity_service():
    return MagicMock()


@pytest.fixture
def client(mock_db, identity_service):
    from modules.users.users.router import router

    app = FastAPI()
    app.include_router(router, prefix="/users")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 9
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_dependencies.get_storage] = lambda: MagicMock()
    app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: identity_service
    return TestClient(app)


def _user(user_id: int, **overrides) -> users_schema.UsersRead:
    fields = {
        "id": user_id,
        "name": f"User {user_id}",
        "username": f"user{user_id}",
        "email": f"user{user_id}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UsersRead(**fields)


class TestReadUsers:
    @patch(f"{_SERVICE}.list_users")
    def test_list_passes_the_query_through(self, mock_list, client, mock_db, identity_service):
        mock_list.return_value = core_pagination.Page(items=[_user(1, name="Alice")], total=1, page=1, num_records=10)

        response = client.get("/users?page_number=1&num_records=10&show_external_auth=false")

        assert response.status_code == 200
        assert response.json()["items"][0]["name"] == "Alice"
        mock_list.assert_called_once()
        assert mock_list.call_args.args == (identity_service, mock_db)
        assert mock_list.call_args.kwargs["page_number"] == 1
        assert mock_list.call_args.kwargs["show_external_auth"] is False

    @patch(f"{_SERVICE}.search_public_users")
    def test_contains_username(self, mock_search, client):
        mock_search.return_value = [
            users_schema.UserPublicRead(id=1, name="A", username="testuser1"),
            users_schema.UserPublicRead(id=2, name="B", username="testuser2"),
        ]

        response = client.get("/users/username/contains/test")

        assert response.status_code == 200
        assert [u["username"] for u in response.json()] == ["testuser1", "testuser2"]

    @patch(f"{_SERVICE}.require_user_by_username")
    def test_exact_username_not_found_is_404(self, mock_get, client):
        mock_get.side_effect = core_exceptions.NotFoundError("User not found")

        response = client.get("/users/username/nonexistent")

        assert response.status_code == 404

    @patch(f"{_SERVICE}.require_user_by_email")
    def test_email_found(self, mock_get, client):
        mock_get.return_value = _user(1, email="test@example.com")

        response = client.get("/users/email/test@example.com")

        assert response.json()["email"] == "test@example.com"

    @patch(f"{_SERVICE}.require_user")
    def test_full_record_by_id_is_served_on_the_admin_route(self, mock_get, client):
        mock_get.return_value = _user(42, name="ID User")

        response = client.get("/users/42")

        assert response.status_code == 200
        assert response.json()["email"] == "user42@example.com"

    @patch(f"{_SERVICE}.get_public_profile")
    def test_id_found(self, mock_get, client):
        mock_get.return_value = users_schema.UserPublicRead(id=42, name="ID User", username="u42")

        response = client.get("/users/id/42")

        assert response.status_code == 200
        assert response.json()["id"] == 42

    @patch(f"{_SERVICE}.get_public_profile")
    def test_id_not_found_is_404(self, mock_get, client):
        mock_get.side_effect = core_exceptions.NotFoundError("User not found")

        assert client.get("/users/id/42").status_code == 404

    def test_id_must_be_positive(self, client):
        assert client.get("/users/id/0").status_code == 422


class TestCreateUser:
    @patch(f"{_SERVICE}.create_user")
    def test_creates_through_the_service(self, mock_create, client, identity_service, mock_db):
        mock_create.return_value = _user(1, name="New User", username="newuser", email="new@example.com")

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
        assert response.json()["username"] == "newuser"
        assert mock_create.call_args.args[1:] == (identity_service, mock_db)

    @patch(f"{_SERVICE}.create_user")
    def test_duplicate_is_a_conflict(self, mock_create, client):
        mock_create.side_effect = core_exceptions.ConflictError("Duplicate entry error")

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

        assert response.status_code == 409


class TestUploadUserImage:
    @patch(f"{_SERVICE}.require_user")
    @patch(f"{_PHOTO}.upload_photo")
    def test_returns_the_resolved_photo_url(self, mock_upload, mock_get, client):
        mock_upload.return_value = "1.jpg"
        mock_get.return_value = _user(1, photo_path="/users/1/photo?t=x")

        response = client.post("/users/1/image", files={"file": ("avatar.jpg", b"fake-image-data", "image/jpeg")})

        assert response.status_code == 201
        assert response.json() == {"photo_path": "/users/1/photo?t=x"}
        mock_upload.assert_called_once()


class TestEditUserNeedsIfMatch:
    @patch(f"{_SERVICE}.edit_user")
    def test_an_edit_without_if_match_is_428(self, mock_edit, client):
        response = client.put(
            "/users/1",
            json={"name": "U", "username": "u", "email": "u@example.com", "active": True, "access_type": "regular"},
        )

        assert response.status_code == 428
        mock_edit.assert_not_called()


class TestEditUser:
    @pytest.mark.parametrize("read_only", [{"id": 1}, {"external_auth_count": 2}])
    def test_a_read_only_field_is_not_accepted_in_the_body(self, read_only, client):
        response = client.put(
            "/users/1",
            json={"name": "U", "username": "u", "email": "u@example.com", "active": True, "access_type": "regular"}
            | read_only,
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 422

    @patch(f"{_SERVICE}.edit_user")
    def test_returns_the_edited_user(self, mock_edit, client, identity_service, mock_db):
        mock_edit.return_value = _user(1, name="Updated User", external_auth_count=2)

        response = client.put(
            "/users/1",
            json={
                "name": "Updated User",
                "username": "updated",
                "email": "updated@example.com",
                "active": True,
                "access_type": "regular",
            },
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert response.json()["external_auth_count"] == 2
        assert mock_edit.call_args.args[0] == 1
        assert mock_edit.call_args.args[2:] == (9, identity_service, mock_db)


class TestApproveUser:
    @patch(f"{_SERVICE}.approve_user")
    def test_approves_with_the_notice_in_the_same_unit_of_work(self, mock_approve, client, identity_service, mock_db):
        response = client.put("/users/1/approve", headers={"If-Match": '"1"'})

        assert response.status_code == 204
        assert response.content == b""
        mock_approve.assert_called_once_with(1, identity_service, mock_db)

    @patch(f"{_SERVICE}.approve_user")
    def test_unverified_email_is_refused(self, mock_approve, client):
        mock_approve.side_effect = core_exceptions.InvalidInputError("User email is not verified")

        response = client.put("/users/1/approve", headers={"If-Match": '"1"'})

        assert response.status_code == 400


class TestEditUserPassword:
    def test_success(self, client, identity_service):
        response = client.post("/users/1/password/change", json={"password": "newpassword123"})

        assert response.status_code == 204
        assert response.content == b""
        identity_service.change_managed_user_password.assert_called_once_with(1, "newpassword123")


class TestDeleteUserPhoto:
    @patch(f"{_PHOTO}.delete_photo")
    def test_success(self, mock_delete, client, mock_db):
        response = client.delete("/users/1/photo")

        assert response.status_code == 204
        assert mock_delete.call_args.args[0] == 1
        assert mock_delete.call_args.args[2] == mock_db


class TestDeleteUser:
    @patch(f"{_SERVICE}.delete_user")
    def test_success(self, mock_delete, client, mock_db):
        response = client.delete("/users/1")

        assert response.status_code == 204
        assert mock_delete.call_args.args[0] == 1
        assert mock_delete.call_args.args[2] == mock_db

    @patch(f"{_SERVICE}.delete_user")
    def test_unknown_user_is_not_found(self, mock_delete, client):
        mock_delete.side_effect = core_exceptions.NotFoundError("User not found")

        assert client.delete("/users/1").status_code == 404


class TestReadScopes:
    """Which scope each read route demands: the full record is admin-only."""

    @staticmethod
    def _scopes(path: str) -> set[str]:
        from modules.users.users.router import router

        route = next(r for r in router.routes if r.path == path and "GET" in r.methods)
        return {scope for dep in route.dependant.dependencies for scope in dep.own_oauth_scopes or []}

    @pytest.mark.parametrize(
        "path",
        ["", "/email/{email}", "/username/{username}", "/{user_id}", "/{user_id}/identity-providers"],
    )
    def test_full_records_need_the_admin_read_scope(self, path):
        assert self._scopes(path) == {"users:read_all"}

    @pytest.mark.parametrize("path", ["/id/{user_id}", "/username/contains/{username}"])
    def test_public_projections_need_only_the_regular_read_scope(self, path):
        assert self._scopes(path) == {"users:read"}

    @patch(f"{_SERVICE}.get_public_profile")
    def test_id_lookup_never_returns_personal_fields(self, mock_get, client):
        mock_get.return_value = users_schema.UserPublicRead(id=4, name="Dee", username="dee", city="Rome")

        body = client.get("/users/id/4").json()

        assert set(body) == {"id", "name", "username", "city", "photo_path"}


class TestReadScopeEnforcement:
    """The real scope check, run with the scopes a regular and an admin token carry."""

    @staticmethod
    def _client(scopes: tuple[str, ...]) -> TestClient:
        from modules.users.users.router import router

        identity = auth_identity_service.DefaultIdentityService(MagicMock(), MagicMock(), MagicMock())
        principal = auth_principal.Principal(
            user_id=9,
            username="member",
            email="member@example.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(scopes),
            credential=auth_principal.AccessTokenCred(session_id="sid"),
        )
        identity.resolve_from_access_token = lambda _token: principal

        app = FastAPI()
        app.include_router(router, prefix="/users")
        core_exceptions.register_exception_handlers(app)
        app.dependency_overrides[auth_dependencies.get_access_token] = lambda: "token"
        app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: identity
        app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
        return TestClient(app)

    @pytest.mark.parametrize(
        "path",
        [
            "/users",
            "/users/email/admin@example.com",
            "/users/username/admin",
            "/users/1",
            "/users/1/identity-providers",
        ],
    )
    def test_regular_token_cannot_read_full_records(self, path):
        response = self._client(auth_constants.REGULAR_ACCESS_SCOPE).get(path)

        assert response.status_code == 403
        assert "users:read_all" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("path", "target"),
        [
            ("/users", "list_users"),
            ("/users/email/admin@example.com", "require_user_by_email"),
            ("/users/username/admin", "require_user_by_username"),
            ("/users/1", "require_user"),
        ],
    )
    def test_admin_token_passes_the_scope_check(self, path, target):
        with patch(f"{_SERVICE}.{target}", side_effect=core_exceptions.NotFoundError("stop")) as mock_target:
            response = self._client(auth_constants.ADMIN_ACCESS_SCOPE).get(path)

        assert response.status_code != 403
        mock_target.assert_called_once()

    @patch(f"{_SERVICE}.get_public_profile")
    def test_regular_token_reads_only_the_public_projection(self, mock_get):
        mock_get.return_value = users_schema.UserPublicRead(id=4, name="Dee", username="dee")

        response = self._client(auth_constants.REGULAR_ACCESS_SCOPE).get("/users/id/4")

        assert response.status_code == 200
        assert set(response.json()) == {"id", "name", "username", "city", "photo_path"}


class TestReadSendsTheETag:
    @pytest.mark.parametrize(
        ("path", "service"),
        [
            ("/users/42", "require_user"),
            ("/users/username/someone", "require_user_by_username"),
            ("/users/email/someone@example.com", "require_user_by_email"),
        ],
    )
    def test_a_full_record_carries_its_version(self, path, service, client):
        with patch(f"{_SERVICE}.{service}", return_value=_user(42, version=7)):
            response = client.get(path)

        assert response.headers["ETag"] == '"7"'
