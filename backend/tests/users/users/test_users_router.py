"""Tests for the users management router endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.security import SecurityScopes
from fastapi.testclient import TestClient

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.constants as auth_constants
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.users.users.dependencies as users_dependencies
import modules.users.users.schema as users_schema

_SID_9 = uuid.UUID(int=109)
_JOB_ID = uuid.UUID(int=501)
_SERVICE = "modules.users.users.router.users_service"
_PHOTO = "modules.users.users.router.users_photo_service"
_STEP_UP_STORE = MagicMock()
_U1, _U4, _U9, _U42 = (uuid.UUID(int=n) for n in (1, 4, 9, 42))
_IDP_ID = uuid.UUID(int=2)
_STEP_UP = {"current_password": "admin-password"}


@pytest.fixture
def mock_db():
    return MagicMock()


def _app_client(mock_db, scopes: frozenset[str]) -> TestClient:
    from modules.users.users.router import router

    app = FastAPI()
    app.include_router(router, prefix="/users")
    app.add_api_route("/jobs/{job_id}", lambda job_id: None, name="read_job")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_current_user_id] = lambda: _U9
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: _SID_9
    app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: _STEP_UP_STORE
    app.dependency_overrides[auth_dependencies.get_current_scopes] = lambda: scopes
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_dependencies.get_storage] = lambda: MagicMock()
    app.dependency_overrides[users_dependencies.get_user_deletion_state_store] = lambda: MagicMock()
    return TestClient(app)


@pytest.fixture
def client(mock_db):
    """A client whose token holds both read scopes, like an administrator's."""
    return _app_client(mock_db, frozenset({"users:read", "users:read-all"}))


@pytest.fixture
def regular_client(mock_db):
    """A client whose token holds only ``users:read``, like a regular user's."""
    return _app_client(mock_db, frozenset({"users:read"}))


def _user(user_id: uuid.UUID, **overrides) -> users_schema.UserRead:
    fields = {
        "id": user_id,
        "name": f"User {user_id.int}",
        "username": f"user{user_id.int}",
        "email": f"user{user_id.int}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UserRead(**fields)


class TestReadUsers:
    @pytest.fixture
    def page_size_setting(self):
        """The server's ``num_records_per_page``, which the user list takes as its page size."""
        with patch("modules.users.users.dependencies.server_settings_integration.get_server_settings") as mock:
            mock.return_value = MagicMock(num_records_per_page=20)
            yield mock

    @patch(f"{_SERVICE}.list_users")
    def test_list_passes_the_query_through(self, mock_list, client, mock_db, page_size_setting):
        mock_list.return_value = core_pagination.Page(items=[_user(_U1, name="Alice")], total=1, page=1, num_records=10)

        response = client.get(
            "/users?page_number=1&num_records=10&external_auth=false&active=true&email_verified=false"
            "&pending_approval=false&username=alice&username_contains=ali"
        )

        assert response.status_code == 200
        assert response.json()["items"][0]["name"] == "Alice"
        mock_list.assert_called_once()
        assert mock_list.call_args.args == (mock_db,)
        assert mock_list.call_args.kwargs == {
            "page_number": 1,
            "num_records": 10,
            "active": True,
            "email_verified": False,
            "pending_approval": False,
            "external_auth": False,
            "username": "alice",
            "username_contains": "ali",
        }

    @patch(f"{_SERVICE}.list_users")
    def test_the_page_size_above_the_server_setting_is_refused(self, mock_list, client, page_size_setting):
        response = client.get("/users?num_records=21")

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "query.num_records"
        mock_list.assert_not_called()

    @patch(f"{_SERVICE}.list_users")
    def test_a_search_term_shorter_than_three_characters_is_refused(self, mock_list, client, page_size_setting):
        assert client.get("/users?username_contains=ab").status_code == 422
        mock_list.assert_not_called()

    @patch(f"{_SERVICE}.list_users")
    def test_an_exact_username_keeps_accepting_short_names(self, mock_list, client, page_size_setting):
        mock_list.return_value = core_pagination.Page(items=[_user(_U1)], total=1, page=1, num_records=20)

        assert client.get("/users?username=ab").status_code == 200
        assert mock_list.call_args.kwargs["username"] == "ab"

    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_gets_the_public_projection(self, mock_search, regular_client, page_size_setting):
        mock_search.return_value = users_schema.UserPublicPage.build(
            [
                users_schema.UserPublicRead(id=_U1, name="A", username="testuser1"),
                users_schema.UserPublicRead(id=uuid.UUID(int=2), name="B", username="testuser2"),
            ],
            2,
            1,
            20,
        )

        response = regular_client.get("/users?username_contains=test&page_number=1&num_records=20")

        assert response.status_code == 200
        body = response.json()
        assert [u["username"] for u in body["items"]] == ["testuser1", "testuser2"]
        assert set(body["items"][0]) == {"id", "name", "username", "city", "photo_path"}
        assert (body["total"], body["next"]) == (2, None)
        assert mock_search.call_args.args[0] == core_pagination.PageParams(1, 20)
        assert mock_search.call_args.kwargs == {"username": None, "username_contains": "test"}

    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_looks_a_user_up_by_exact_username(self, mock_search, regular_client, page_size_setting):
        mock_search.return_value = users_schema.UserPublicPage.build([], 0, 1, 20)

        assert regular_client.get("/users?username=dee").status_code == 200
        assert mock_search.call_args.kwargs == {"username": "dee", "username_contains": None}

    @pytest.mark.parametrize("username", ["a", "ab"])
    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_looks_a_user_up_by_a_short_exact_username(
        self, mock_search, username, regular_client, page_size_setting
    ):
        mock_search.return_value = users_schema.UserPublicPage.build([], 0, 1, 20)

        assert regular_client.get(f"/users?username={username}").status_code == 200
        assert mock_search.call_args.kwargs == {"username": username, "username_contains": None}

    @pytest.mark.parametrize("query", ["", "page_number=2"])
    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_without_a_search_term_is_refused(
        self, mock_search, query, regular_client, page_size_setting
    ):
        response = regular_client.get(f"/users?{query}")

        assert response.status_code == 422
        error = response.json()["errors"][0]
        assert error["field"] == "query.username"
        mock_search.assert_not_called()

    @patch(f"{_SERVICE}.list_public_users")
    def test_a_short_username_contains_is_refused_as_too_short(self, mock_search, regular_client, page_size_setting):
        response = regular_client.get("/users?username_contains=ab")

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "query.username_contains"
        mock_search.assert_not_called()

    @patch(f"{_SERVICE}.list_users")
    def test_an_administrator_lists_every_user_without_a_filter(self, mock_list, client, page_size_setting):
        mock_list.return_value = core_pagination.Page(items=[_user(_U1)], total=1, page=1, num_records=20)

        assert client.get("/users").status_code == 200

    @pytest.mark.parametrize(
        "query",
        ["active=true", "email_verified=true", "pending_approval=false", "external_auth=true"],
    )
    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_cannot_use_a_state_filter(self, mock_search, query, regular_client, page_size_setting):
        response = regular_client.get(f"/users?{query}")

        assert response.status_code == 403
        assert response.json()["missing_scopes"] == ["users:read-all"]
        mock_search.assert_not_called()

    @patch(f"{_SERVICE}.list_public_users")
    def test_a_regular_token_page_size_above_the_server_setting_is_refused(
        self, mock_search, regular_client, page_size_setting
    ):
        assert regular_client.get("/users?username_contains=test&num_records=21").status_code == 422
        mock_search.assert_not_called()

    @pytest.mark.parametrize("path", ["/users/id/42", "/users/username/someone", "/users/username/contains/test"])
    def test_the_old_lookup_paths_are_gone(self, path, client):
        assert client.get(path).status_code == 404

    def test_the_email_lookup_route_is_gone(self, client):
        assert client.post("/users/email/lookup", json={"email": "test@example.com"}).status_code in (404, 405)

    def test_the_email_is_not_a_path_segment(self, client):
        assert client.get("/users/email/test@example.com").status_code in (404, 405)

    @patch(f"{_SERVICE}.require_user_with_pending_email")
    def test_an_admin_reads_the_full_record_with_its_version(self, mock_get, client):
        mock_get.return_value = _user(_U42, name="ID User", version=7)

        response = client.get(f"/users/{_U42}")

        assert response.status_code == 200
        assert response.json()["email"] == "user42@example.com"
        assert response.headers["ETag"] == '"7"'

    @patch(f"{_SERVICE}.require_user_with_pending_email")
    def test_a_read_carries_mfa_enabled(self, mock_get, client):
        mock_get.return_value = _user(_U42, mfa_enabled=True)

        assert client.get(f"/users/{_U42}").json()["mfa_enabled"] is True

    @patch(f"{_SERVICE}.require_user_with_pending_email")
    def test_a_read_carries_pending_admin_approval(self, mock_get, client):
        mock_get.return_value = _user(_U42, pending_admin_approval=True)

        assert client.get(f"/users/{_U42}").json()["pending_admin_approval"] is True

    @patch(f"{_SERVICE}.get_public_profile")
    def test_a_regular_token_reads_the_public_projection(self, mock_get, regular_client):
        mock_get.return_value = users_schema.UserPublicRead(id=_U42, name="ID User", username="u42")

        response = regular_client.get(f"/users/{_U42}")

        assert response.status_code == 200
        assert response.json() == {
            "id": str(_U42),
            "name": "ID User",
            "username": "u42",
            "city": None,
            "photo_path": None,
        }
        assert "ETag" not in response.headers

    @patch(f"{_SERVICE}.get_public_profile")
    def test_a_regular_token_reading_an_unknown_user_is_404(self, mock_get, regular_client):
        mock_get.side_effect = core_exceptions.NotFoundError("User not found")

        assert regular_client.get(f"/users/{_U42}").status_code == 404

    def test_a_malformed_id_is_422(self, client):
        assert client.get("/users/0").status_code == 422
        assert client.get("/users/not-a-uuid").status_code == 422


class TestCreateUser:
    @patch(f"{_SERVICE}.create_user")
    def test_pending_admin_approval_is_not_accepted_in_the_body(self, mock_create, client):
        response = client.post(
            "/users",
            json={
                "name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "active": True,
                "access_type": "regular",
                "password": "testpass123",
                "pending_admin_approval": True,
            },
        )

        assert response.status_code == 422
        mock_create.assert_not_called()

    @patch(f"{_SERVICE}.create_user")
    def test_mfa_enabled_is_not_accepted_in_the_body(self, mock_create, client):
        response = client.post(
            "/users",
            json={
                "name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "active": True,
                "access_type": "regular",
                "password": "testpass123",
                "mfa_enabled": True,
            },
        )

        assert response.status_code == 422
        mock_create.assert_not_called()

    @patch(f"{_SERVICE}.create_user")
    def test_creates_through_the_service(self, mock_create, client, mock_db):
        mock_create.return_value = _user(_U1, name="New User", username="newuser", email="new@example.com")

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
        assert response.headers["Location"] == f"/users/{_U1}"
        assert response.headers["ETag"] == '"1"'
        assert mock_create.call_args.args[1:] == (None, _U9, _SID_9, _STEP_UP_STORE, mock_db)

    @patch(f"{_SERVICE}.create_user")
    def test_the_step_up_travels_apart_from_the_user_fields(self, mock_create, client):
        mock_create.return_value = _user(_U1, access_type="admin")

        response = client.post(
            "/users",
            json={
                "name": "New Admin",
                "username": "newadmin",
                "email": "new@example.com",
                "active": True,
                "access_type": "admin",
                "password": "testpass123",
                "step_up": _STEP_UP,
            },
        )

        assert response.status_code == 201
        created, step_up = mock_create.call_args.args[:2]
        assert type(created) is users_schema.UserCreate
        assert "step_up" not in created.model_dump()
        assert step_up == auth_schema.StepUpVerification(current_password="admin-password")

    @patch(f"{_SERVICE}.create_user")
    def test_a_refused_step_up_is_the_uniform_403(self, mock_create, client):
        mock_create.side_effect = core_exceptions.StepUpFailedError()

        response = client.post(
            "/users",
            json={
                "name": "New Admin",
                "username": "newadmin",
                "email": "new@example.com",
                "active": True,
                "access_type": "admin",
                "password": "testpass123",
            },
        )

        assert response.status_code == 403

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


class TestShortPasswordIsTyped:
    """The administrator's password writes answer a too-short password with the typed 422 problem."""

    @patch(f"{_SERVICE}.create_user", side_effect=credentials_contracts.PasswordTooShortError("short"))
    def test_create_user(self, _create, client):
        response = client.post(
            "/users",
            json={
                "name": "New User",
                "username": "newuser",
                "email": "new@example.com",
                "active": True,
                "access_type": "regular",
                "password": "short",
            },
        )

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:password-too-short"

    @patch(f"{_SERVICE}.change_user_password", side_effect=credentials_contracts.PasswordTooShortError("short"))
    def test_set_password(self, _change, client):
        response = client.post(
            f"/users/{_U1}/password/change", json={"password": "short", "step_up": {"current_password": "pw"}}
        )

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:password-too-short"


class TestUploadUserImage:
    @pytest.mark.parametrize(("replaced", "status_code"), [(False, 201), (True, 200)])
    @patch(f"{_SERVICE}.require_user")
    @patch(f"{_PHOTO}.upload_photo")
    def test_returns_the_resolved_photo_url(self, mock_upload, mock_get, replaced, status_code, client):
        mock_upload.return_value = replaced
        mock_get.return_value = _user(_U1, photo_path=f"/users/{_U1}/photo?t=x")

        response = client.put(f"/users/{_U1}/photo", files={"file": ("avatar.jpg", b"fake-image-data", "image/jpeg")})

        assert response.status_code == status_code
        assert response.json() == {"photo_path": f"/users/{_U1}/photo?t=x"}
        mock_upload.assert_called_once()
        assert mock_upload.call_args.kwargs == {"audit": True}


class TestEditUserNeedsIfMatch:
    @patch(f"{_SERVICE}.edit_user")
    def test_an_edit_without_if_match_is_428(self, mock_edit, client):
        response = client.patch(
            f"/users/{_U1}",
            json={"name": "U", "username": "u", "email": "u@example.com", "active": True, "access_type": "regular"},
        )

        assert response.status_code == 428
        mock_edit.assert_not_called()


class TestEditUser:
    @patch(f"{_SERVICE}.edit_user")
    def test_demoting_the_only_administrator_is_a_last_administrator_conflict(self, mock_edit, client):
        mock_edit.side_effect = core_exceptions.LastAdministratorError("The only administrator cannot be demoted")

        response = client.patch(
            f"/users/{_U1}",
            json={"name": "U", "username": "u", "email": "u@example.com", "active": True, "access_type": "regular"},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:last-administrator"

    @pytest.mark.parametrize(
        "read_only",
        [{"id": str(_U1)}, {"external_auth_count": 2}, {"mfa_enabled": True}, {"pending_admin_approval": True}],
    )
    def test_a_read_only_field_is_not_accepted_in_the_body(self, read_only, client):
        response = client.patch(
            f"/users/{_U1}",
            json={"name": "U", "username": "u", "email": "u@example.com", "active": True, "access_type": "regular"}
            | read_only,
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 422

    @patch(f"{_SERVICE}.edit_user")
    def test_returns_the_edited_user(self, mock_edit, client, mock_db):
        mock_edit.return_value = _user(_U1, name="Updated User", external_auth_count=2)

        response = client.patch(
            f"/users/{_U1}",
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
        assert mock_edit.call_args.args[0] == _U1
        assert mock_edit.call_args.args[2:] == (None, _U9, _SID_9, _STEP_UP_STORE, mock_db)

    @patch(f"{_SERVICE}.edit_user")
    def test_the_step_up_travels_apart_from_the_user_fields(self, mock_edit, client):
        mock_edit.return_value = _user(_U1)

        response = client.patch(
            f"/users/{_U1}",
            json={
                "name": "Updated User",
                "username": "updated",
                "email": "updated@example.com",
                "active": True,
                "access_type": "regular",
                "step_up": _STEP_UP,
            },
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200
        edit, step_up = mock_edit.call_args.args[1:3]
        assert type(edit) is users_schema.UserEdit
        assert "step_up" not in edit.model_dump()
        assert step_up == auth_schema.StepUpVerification(current_password="admin-password")


class TestApproveUser:
    @patch(f"{_SERVICE}.approve_user")
    def test_approves_with_the_notice_in_the_same_unit_of_work(self, mock_approve, client, mock_db):
        response = client.post(f"/users/{_U1}/approve")

        assert response.status_code == 204
        assert response.content == b""
        mock_approve.assert_called_once_with(_U1, mock_db)

    @patch(f"{_SERVICE}.approve_user")
    def test_unverified_email_is_refused(self, mock_approve, client):
        mock_approve.side_effect = core_exceptions.ConflictError("User email is not verified")

        response = client.post(f"/users/{_U1}/approve")

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:conflict"


class TestEditUserPassword:
    @patch(f"{_SERVICE}.change_user_password")
    def test_changes_the_password_with_the_administrators_step_up(self, change_password, client, mock_db):
        response = client.post(
            f"/users/{_U1}/password/change",
            json={"password": "newpassword123", "step_up": {"current_password": "admin-password"}},
        )

        assert response.status_code == 204
        assert response.content == b""
        args = change_password.call_args.args
        assert args[0] == _U1
        assert (args[1].password, args[1].step_up.current_password) == ("newpassword123", "admin-password")
        assert args[2:] == (_U9, _SID_9, _STEP_UP_STORE, mock_db)

    @patch(f"{_SERVICE}.change_user_password")
    def test_a_refused_step_up_is_the_services_answer(self, change_password, client):
        change_password.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        response = client.post(f"/users/{_U1}/password/change", json={"password": "newpassword123", "step_up": {}})

        assert response.status_code == 403


class TestAdministratorCredentialActions:
    @pytest.mark.parametrize(
        ("path", "service_function"),
        [
            (f"/users/{_U1}/mfa/reset", "reset_user_mfa"),
            (f"/users/{_U1}/password/require-change", "require_user_password_change"),
        ],
    )
    def test_runs_with_the_administrators_step_up(self, path, service_function, client, mock_db):
        with patch(f"{_SERVICE}.{service_function}") as service:
            response = client.post(path, json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert response.content == b""
        args = service.call_args.args
        assert args[0] == _U1
        assert args[1].step_up.current_password == "admin-password"
        assert args[2:] == (_U9, _SID_9, _STEP_UP_STORE, mock_db)

    @pytest.mark.parametrize(
        ("path", "service_function", "error", "status_code"),
        [
            (f"/users/{_U1}/mfa/reset", "reset_user_mfa", core_exceptions.PermissionDeniedError("no"), 403),
            (f"/users/{_U1}/mfa/reset", "reset_user_mfa", core_exceptions.ConflictError("off"), 409),
            (
                f"/users/{_U1}/password/require-change",
                "require_user_password_change",
                core_exceptions.ConflictError(),
                409,
            ),
        ],
    )
    def test_a_refusal_is_the_services_answer(self, path, service_function, error, status_code, client):
        with patch(f"{_SERVICE}.{service_function}", side_effect=error):
            response = client.post(path, json={"step_up": _STEP_UP})

        assert response.status_code == status_code

    @pytest.mark.parametrize("path", [f"/users/{_U1}/mfa/reset", f"/users/{_U1}/password/require-change"])
    def test_a_body_without_the_step_up_is_422(self, path, client):
        assert client.post(path, json={}).status_code == 422


class TestDeleteUserPhoto:
    @patch(f"{_PHOTO}.delete_photo")
    def test_success(self, mock_delete, client, mock_db):
        response = client.delete(f"/users/{_U1}/photo")

        assert response.status_code == 204
        assert mock_delete.call_args.args[0] == _U1
        assert mock_delete.call_args.args[2] == mock_db
        assert mock_delete.call_args.kwargs == {"audit": True}


class TestDeleteUser:
    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_queues_the_deletion(self, mock_request, client, mock_db):
        mock_request.return_value = users_schema.UserDeletionStatus(
            id=_JOB_ID, kind="user_deletion", created_at=datetime(2026, 1, 1, tzinfo=UTC), status="queued"
        )

        response = client.post(f"/users/{_U1}/delete", json={"step_up": _STEP_UP}, headers={"If-Match": '"3"'})

        assert response.status_code == 202
        assert response.headers["Content-Location"] == f"/jobs/{_JOB_ID}"
        assert response.json() == {
            "id": str(_JOB_ID),
            "kind": "user_deletion",
            "created_at": "2026-01-01T00:00:00Z",
            "finished_at": None,
            "error_code": None,
            "status": "queued",
        }
        args = mock_request.call_args.args
        assert args[:3] == (_U1, _U9, _SID_9)
        assert args[3] == auth_schema.StepUpVerification(current_password="admin-password")
        assert args[4] is _STEP_UP_STORE
        assert args[5] is not None
        assert args[8] == mock_db
        assert mock_request.call_args.kwargs == {"if_match": '"3"'}

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_without_if_match_is_428(self, mock_request, client):
        assert client.post(f"/users/{_U1}/delete", json={"step_up": _STEP_UP}).status_code == 428
        mock_request.assert_not_called()

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_a_stale_if_match_is_412(self, mock_request, client):
        mock_request.side_effect = core_exceptions.PreconditionFailedError("stale")

        assert (
            client.post(f"/users/{_U1}/delete", json={"step_up": _STEP_UP}, headers={"If-Match": '"1"'}).status_code
            == 412
        )

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_unknown_user_is_not_found(self, mock_request, client):
        mock_request.side_effect = core_exceptions.NotFoundError("User not found")

        assert (
            client.post(f"/users/{_U1}/delete", json={"step_up": _STEP_UP}, headers={"If-Match": '"1"'}).status_code
            == 404
        )

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_the_only_administrator_is_refused(self, mock_request, client):
        mock_request.side_effect = core_exceptions.LastAdministratorError("The only administrator cannot be deleted")

        response = client.post(f"/users/{_U1}/delete", json={"step_up": _STEP_UP}, headers={"If-Match": '"1"'})

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:last-administrator"

    def test_the_delete_verb_is_gone(self, client):
        assert client.delete(f"/users/{_U1}", headers={"If-Match": '"1"'}).status_code == 405

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_a_refused_step_up_queues_nothing(self, mock_request, client):
        mock_request.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        assert client.post(f"/users/{_U1}/delete", json={"step_up": {}}, headers={"If-Match": '"1"'}).status_code == 403

    @patch("modules.users.users.router.users_deletion_job_service.request_deletion_by_administrator")
    def test_a_body_with_an_unknown_field_is_422(self, mock_request, client):
        response = client.post(f"/users/{_U1}/delete", json={"extra": 1}, headers={"If-Match": '"1"'})

        assert response.status_code == 422
        mock_request.assert_not_called()


class TestUnlinkUserIdentityProvider:
    @patch(f"{_SERVICE}.unlink_identity_provider")
    def test_unlinks_with_the_administrators_step_up(self, unlink, client, mock_db):
        response = client.post(f"/users/{_U4}/identity-providers/{_IDP_ID}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert response.content == b""
        unlink.assert_called_once_with(
            _U4,
            _IDP_ID,
            _U9,
            _SID_9,
            auth_schema.StepUpVerification(current_password="admin-password"),
            _STEP_UP_STORE,
            mock_db,
        )

    @patch(f"{_SERVICE}.unlink_identity_provider")
    def test_a_malformed_provider_id_is_422(self, unlink, client):
        response = client.post(f"/users/{_U4}/identity-providers/2/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 422
        unlink.assert_not_called()

    def test_the_delete_verb_is_gone(self, client):
        assert client.delete(f"/users/{_U4}/identity-providers/{_IDP_ID}").status_code in (404, 405)

    @patch(f"{_SERVICE}.unlink_identity_provider")
    def test_a_refused_step_up_is_the_services_answer(self, unlink, client):
        unlink.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        assert client.post(f"/users/{_U4}/identity-providers/{_IDP_ID}/unlink", json={"step_up": {}}).status_code == 403


class TestDeletionStatusRouteIsGone:
    def test_the_status_read_moved_to_the_jobs_route(self, client):
        assert client.get(f"/users/{_U1}/deletion").status_code in (404, 405)


class TestReadUserIdentityProviders:
    @patch("modules.users.users.router.account_security_integration.get_user_identity_provider_links")
    def test_returns_the_page_for_the_requested_window(self, mock_links, client, mock_db):
        mock_links.return_value = {"items": [], "total": 3, "page": 2, "num_records": 1, "next": 3}

        response = client.get(f"/users/{_U4}/identity-providers", params={"page_number": 2, "num_records": 1})

        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 3, "page": 2, "num_records": 1, "next": 3}
        mock_links.assert_called_once_with(_U4, core_pagination.PageParams(2, 1), mock_db)


class TestLookupParametersAreBounded:
    """A lookup key longer than the column can hold is refused before it reaches the database."""

    @pytest.mark.parametrize("name", ["username", "username_contains"])
    def test_a_value_longer_than_the_column_is_refused(self, client, name):
        with patch("modules.users.users.dependencies.server_settings_integration.get_server_settings") as settings:
            settings.return_value = MagicMock(num_records_per_page=20)
            assert client.get(f"/users?{name}=" + "a" * 251).status_code == 422

    def test_a_value_at_the_limit_reaches_the_service(self, client):
        with (
            patch("modules.users.users.dependencies.server_settings_integration.get_server_settings") as settings,
            patch(
                f"{_SERVICE}.list_users", return_value=core_pagination.Page(items=[], total=0, page=1, num_records=20)
            ),
        ):
            settings.return_value = MagicMock(num_records_per_page=20)
            assert client.get("/users?username=" + "a" * 250).status_code == 200


class TestReadScopes:
    """Which scope each read route demands: the full record is admin-only."""

    @staticmethod
    def _scopes(path: str) -> set[str]:
        from modules.users.users.router import router

        route = next(r for r in router.routes if r.path == path and "GET" in r.methods)
        return {scope for dep in route.dependant.dependencies for scope in dep.own_oauth_scopes or []}

    @pytest.mark.parametrize("path", ["/{user_id}/identity-providers"])
    def test_full_records_need_the_admin_read_scope(self, path):
        assert self._scopes(path) == {"users:read-all"}

    @pytest.mark.parametrize("path", ["", "/{user_id}"])
    def test_reads_that_serve_both_projections_need_only_the_regular_read_scope(self, path):
        assert self._scopes(path) == {"users:read"}


class TestReadScopeEnforcement:
    """The real scope check, run with the scopes a regular and an admin token carry."""

    @staticmethod
    def _client(scopes: tuple[str, ...]) -> TestClient:
        from modules.users.users.router import router

        app = FastAPI()
        app.include_router(router, prefix="/users")
        core_exceptions.register_exception_handlers(app)

        def check_scopes(security_scopes: SecurityScopes):
            missing = set(security_scopes.scopes) - set(scopes)
            if missing:
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail=f"Missing permissions: {missing}")

        app.dependency_overrides[auth_dependencies.check_scopes] = check_scopes
        app.dependency_overrides[auth_dependencies.get_current_scopes] = lambda: frozenset(scopes)
        app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
        return TestClient(app)

    @pytest.mark.parametrize(
        "path",
        [
            f"/users/{_U1}/identity-providers",
        ],
    )
    def test_regular_token_cannot_read_full_records(self, path):
        response = self._client(auth_constants.REGULAR_ACCESS_SCOPE).get(path)

        assert response.status_code == 403
        assert "users:read-all" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("path", "target"),
        [
            ("/users", "list_users"),
            (f"/users/{_U1}", "require_user_with_pending_email"),
        ],
    )
    def test_admin_token_passes_the_scope_check(self, path, target):
        with (
            patch(f"{_SERVICE}.{target}", side_effect=core_exceptions.NotFoundError("stop")) as mock_target,
            patch("modules.users.users.dependencies.server_settings_integration.get_server_settings") as settings,
        ):
            settings.return_value = MagicMock(num_records_per_page=25)
            response = self._client(auth_constants.ADMIN_ACCESS_SCOPE).get(path)

        assert response.status_code != 403
        mock_target.assert_called_once()

    @patch(f"{_SERVICE}.get_public_profile")
    def test_regular_token_reads_only_the_public_projection(self, mock_get):
        mock_get.return_value = users_schema.UserPublicRead(id=_U4, name="Dee", username="dee")

        response = self._client(auth_constants.REGULAR_ACCESS_SCOPE).get(f"/users/{_U4}")

        assert response.status_code == 200
        assert set(response.json()) == {"id", "name", "username", "city", "photo_path"}

    @patch(f"{_SERVICE}.list_public_users")
    def test_regular_token_lists_only_public_projections(self, mock_list):
        mock_list.return_value = users_schema.UserPublicPage.build(
            [users_schema.UserPublicRead(id=_U4, name="Dee", username="dee")], 1, 1, 25
        )
        with patch("modules.users.users.dependencies.server_settings_integration.get_server_settings") as settings:
            settings.return_value = MagicMock(num_records_per_page=25)
            response = self._client(auth_constants.REGULAR_ACCESS_SCOPE).get("/users?username_contains=dee")

        assert response.status_code == 200
        assert set(response.json()["items"][0]) == {"id", "name", "username", "city", "photo_path"}


class TestReadSendsTheETag:
    @pytest.mark.parametrize(
        ("path", "service"),
        [
            (f"/users/{_U42}", "require_user_with_pending_email"),
        ],
    )
    def test_a_full_record_carries_its_version(self, path, service, client):
        with patch(f"{_SERVICE}.{service}", return_value=_user(_U42, version=7)):
            response = client.get(path)

        assert response.headers["ETag"] == '"7"'
