from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.auth.dependencies as auth_deps
    import modules.followers.router as router
    import modules.users.users.dependencies as users_deps

    app = FastAPI()
    app.include_router(router.router)
    # Same domain-error boundary the real app registers, so these tests assert
    # the status codes clients actually receive.
    core_exceptions.register_exception_handlers(app)

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
    @patch("modules.followers.crud.get_all_followers_by_user_id")
    def test_self_success(self, mock_get, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=3, followee_id=1, status="accepted")]

        # Requester (1) == target (1): always allowed.
        response = client.get("/users/1/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.followers.crud.get_all_followers_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_stranger_forbidden(self, mock_rel, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None  # requester is not an accepted follower of the target

        response = client.get("/users/2/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_get.assert_not_called()

    @patch("modules.followers.crud.get_all_followers_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_accepted_follower_allowed(self, mock_rel, mock_get, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        # Requester (1) is an accepted follower of target (2).
        mock_rel.return_value = FollowRelationship(follower_id=1, followee_id=2, status="accepted")
        mock_get.return_value = []

        response = client.get("/users/2/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestGetUserFollowerCount:
    @patch("modules.followers.crud.count_followers_by_user_id")
    def test_count_self(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 5

        # Requester (1) == target (1): always allowed.
        response = client.get("/users/1/followers/count", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 5

    @patch("modules.followers.crud.count_followers_by_user_id")
    def test_count_accepted_only(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 3

        response = client.get("/users/1/followers/count?accepted_only=true", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 3
        assert mock_count.call_args.kwargs["accepted_only"] is True

    @patch("modules.followers.crud.count_followers_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_count_stranger_forbidden(self, mock_rel, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None

        response = client.get("/users/2/followers/count", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_count.assert_not_called()


class TestGetUserFollowing:
    @patch("modules.followers.crud.get_all_following_by_user_id")
    def test_self_success(self, mock_get, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=1, followee_id=2, status="accepted")]

        # Requester (1) == target (1): always allowed.
        response = client.get("/users/1/following", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.followers.crud.get_all_following_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_stranger_forbidden(self, mock_rel, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None

        response = client.get("/users/2/following", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_get.assert_not_called()


class TestGetUserFollowingCount:
    @patch("modules.followers.crud.count_following_by_user_id")
    def test_count_self(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 5

        response = client.get("/users/1/following/count", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 5

    @patch("modules.followers.crud.count_following_by_user_id")
    def test_count_accepted_only(self, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_count.return_value = 3

        response = client.get("/users/1/following/count?accepted_only=true", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 3
        assert mock_count.call_args.kwargs["accepted_only"] is True

    @patch("modules.followers.crud.count_following_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_count_stranger_forbidden(self, mock_rel, mock_count, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None

        response = client.get("/users/2/following/count", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_count.assert_not_called()


class TestReadUserRelationship:
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_success(self, mock_get, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = FollowRelationship(follower_id=1, followee_id=2, status="accepted")

        response = client.get("/users/2/relationship", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        body = response.json()
        assert body["outgoing"]["followee_id"] == 2
        assert body["incoming"]["followee_id"] == 2

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_no_relationship(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/users/2/relationship", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        body = response.json()
        assert body["outgoing"] is None
        assert body["incoming"] is None


class TestFollowUser:
    @patch("modules.followers.service.follow_user")
    def test_success(self, mock_follow, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_follow.return_value = FollowRelationship(follower_id=1, followee_id=2, status="pending")

        response = client.post("/users/2/follow", headers={"Authorization": "Bearer x"})
        assert response.status_code == 201
        mock_follow.assert_called_once_with(1, 2, mock_db)


class TestAcceptFollow:
    @patch("modules.followers.service.accept_follow_request")
    def test_success(self, mock_accept, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/users/2/follow/accept", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["detail"] == "Follower accepted successfully"
        mock_accept.assert_called_once_with(1, 2, mock_db)


class TestUnfollowUser:
    @patch("modules.followers.service.unfollow_user")
    def test_success(self, mock_unfollow, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/users/2/follow", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        mock_unfollow.assert_called_once_with(1, 2, mock_db)


class TestRemoveFollower:
    @patch("modules.followers.service.remove_follower")
    def test_success(self, mock_remove, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/users/2/follower", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        mock_remove.assert_called_once_with(1, 2, mock_db)
