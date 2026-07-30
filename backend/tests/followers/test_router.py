from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.followers.router as router
    import modules.users.users.dependencies as users_deps

    app = FastAPI()
    app.include_router(router.router)

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[users_deps.validate_user_id] = _mock
    app.dependency_overrides[users_deps.validate_target_user_id] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestGetUserFollowers:
    @patch("modules.followers.router.followers_crud.get_all_followers_by_user_id")
    def test_all_success(self, mock_get, mock_db):
        from modules.followers.schema import Follower

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [Follower(follower_id=1, following_id=2, is_accepted=True)]

        response = client.get("/user/1/followers/all", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestGetUserFollowerCount:
    @patch("modules.followers.router.followers_crud.count_followers_by_user_id")
    def test_count_all(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 5

        response = client.get("/user/1/followers/count/all", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 5

    @patch("modules.followers.router.followers_crud.count_followers_by_user_id")
    def test_count_accepted(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 3

        response = client.get("/user/1/followers/count/accepted", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 3


class TestGetUserFollowing:
    @patch("modules.followers.router.followers_crud.get_all_following_by_user_id")
    def test_all_success(self, mock_get, mock_db):
        from modules.followers.schema import Follower

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [Follower(follower_id=1, following_id=2, is_accepted=True)]

        response = client.get("/user/1/following/all", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestGetUserFollowingCount:
    @patch("modules.followers.router.followers_crud.count_following_by_user_id")
    def test_count_all(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 5

        response = client.get("/user/1/following/count/all", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 5

    @patch("modules.followers.router.followers_crud.count_following_by_user_id")
    def test_count_accepted(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 3

        response = client.get("/user/1/following/count/accepted", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 3


class TestReadFollowerSpecificUser:
    @patch("modules.followers.router.followers_crud.get_follower_for_user_id_and_target_user_id")
    def test_success(self, mock_get, mock_db):
        from modules.followers.schema import Follower

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = Follower(follower_id=1, following_id=2, is_accepted=True)

        response = client.get("/user/1/targetUser/2", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.followers.router.followers_crud.get_follower_for_user_id_and_target_user_id")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/user/1/targetUser/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestCreateFollow:
    @patch("modules.followers.router.websocket_manager.get_websocket_manager")
    @patch("modules.followers.router.followers_crud.create_follower")
    async def test_create_success(self, mock_create, mock_ws, mock_db):
        from modules.followers.schema import Follower

        client = TestClient(_build_app(mock_db))
        mock_create.return_value = Follower(follower_id=1, following_id=2, is_accepted=False)

        response = client.post("/create/targetUser/2", headers={"Authorization": "Bearer x"})
        assert response.status_code == 201


class TestAcceptFollow:
    @patch("modules.followers.router.websocket_manager.get_websocket_manager")
    @patch("modules.followers.router.followers_crud.accept_follower")
    async def test_accept_success(self, mock_accept, mock_ws, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.put("/accept/targetUser/2", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["detail"] == "Follower accepted successfully"


class TestDeleteFollower:
    @patch("modules.followers.router.followers_crud.delete_follower")
    def test_delete_follower_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/delete/follower/targetUser/2", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.followers.router.followers_crud.delete_follower")
    def test_delete_following_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/delete/following/targetUser/2", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
