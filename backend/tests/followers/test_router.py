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
    @patch("modules.followers.crud.count_followers_by_user_id")
    @patch("modules.followers.crud.get_all_followers_by_user_id")
    def test_self_success(self, mock_get, mock_count, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=3, followee_id=1, status="accepted")]
        mock_count.return_value = 1

        # Requester (1) == target (1): always allowed.
        response = client.get("/users/1/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        # The list is a page envelope, matching the activities list endpoints.
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["next"] is None
        assert len(body["items"]) == 1

    @patch("modules.followers.crud.count_followers_by_user_id")
    @patch("modules.followers.crud.get_all_followers_by_user_id")
    def test_pagination_is_passed_through_and_next_is_derived(self, mock_get, mock_count, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=3, followee_id=1, status="accepted")]
        mock_count.return_value = 40

        response = client.get(
            "/users/1/followers?page_number=2&num_records=10",
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 200
        assert mock_get.call_args.kwargs == {"page_number": 2, "num_records": 10, "accepted_only": False}
        # 2 * 10 < 40, so another page exists.
        assert response.json()["next"] == 3

    def test_page_size_is_capped(self, mock_db):
        response = TestClient(_build_app(mock_db)).get(
            "/users/1/followers?num_records=5000",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 422

    @patch("modules.followers.crud.get_all_followers_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_stranger_forbidden(self, mock_rel, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None  # requester is not an accepted follower of the target

        response = client.get("/users/2/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_get.assert_not_called()

    @patch("modules.followers.crud.count_followers_by_user_id")
    @patch("modules.followers.crud.get_all_followers_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_accepted_follower_allowed(self, mock_rel, mock_get, mock_count, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        # Requester (1) is an accepted follower of target (2).
        mock_rel.return_value = FollowRelationship(follower_id=1, followee_id=2, status="accepted")
        mock_get.return_value = []
        mock_count.return_value = 0

        response = client.get("/users/2/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestGetUserFollowing:
    @patch("modules.followers.crud.count_following_by_user_id")
    @patch("modules.followers.crud.get_all_following_by_user_id")
    def test_self_success(self, mock_get, mock_count, mock_db):
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=1, followee_id=2, status="accepted")]
        mock_count.return_value = 1

        # Requester (1) == target (1): always allowed.
        response = client.get("/users/1/following", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch("modules.followers.crud.get_all_following_by_user_id")
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_stranger_forbidden(self, mock_rel, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_rel.return_value = None

        response = client.get("/users/2/following", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
        mock_get.assert_not_called()


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

        response = client.post("/users/2/followers", headers={"Authorization": "Bearer x"})
        assert response.status_code == 201
        mock_follow.assert_called_once_with(1, 2, mock_db)


class TestListFollowRequests:
    @patch("modules.followers.crud.count_pending_requests_for_user_id")
    @patch("modules.followers.crud.get_pending_requests_for_user_id")
    def test_lists_only_the_callers_requests(self, mock_get, mock_count, mock_db):
        """There is no user id in the path, so no other inbox is addressable."""
        from modules.followers.schema import FollowRelationship

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [FollowRelationship(follower_id=3, followee_id=1, status="pending")]
        mock_count.return_value = 1

        response = client.get("/follow-requests", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert mock_get.call_args.args[0] == 1


class TestDecideFollowRequest:
    @patch("modules.followers.service.accept_follow_request")
    def test_accept(self, mock_accept, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.patch(
            "/follow-requests/2", json={"status": "accepted"}, headers={"Authorization": "Bearer x"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        mock_accept.assert_called_once_with(1, 2, mock_db)

    @patch("modules.followers.service.accept_follow_request")
    def test_rejects_an_unsupported_transition(self, mock_accept, mock_db):
        """``pending`` is not a decision; only ``accepted`` may be written."""
        client = TestClient(_build_app(mock_db))

        response = client.patch("/follow-requests/2", json={"status": "pending"}, headers={"Authorization": "Bearer x"})

        assert response.status_code == 422
        mock_accept.assert_not_called()


class TestRejectFollowRequest:
    @patch("modules.followers.service.reject_follow_request")
    def test_success(self, mock_reject, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/follow-requests/2", headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_reject.assert_called_once_with(1, 2, mock_db)


class TestDeleteFollowRelationship:
    @patch("modules.followers.service.delete_relationship")
    def test_unfollowing_is_the_caller_as_follower(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/users/2/followers/1", headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_delete.assert_called_once_with(2, 1, 1, mock_db)

    @patch("modules.followers.service.delete_relationship")
    def test_removing_a_follower_is_the_caller_as_followee(self, mock_delete, mock_db):
        """Same route, opposite direction — previously two endpoints told apart
        only by a singular/plural path segment."""
        client = TestClient(_build_app(mock_db))

        response = client.delete("/users/1/followers/2", headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 2, 1, mock_db)

    def test_a_third_party_cannot_delete_someone_elses_relationship(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/users/2/followers/3", headers={"Authorization": "Bearer x"})

        assert response.status_code == 403


class TestRemovedCountEndpoints:
    def test_counts_are_gone(self, mock_db):
        """``total`` on the page envelope replaced them, for the same filter."""
        client = TestClient(_build_app(mock_db))

        for path in ("/users/1/followers/count", "/users/1/following/count"):
            # 405 rather than 404 for the followers path: it now matches the
            # DELETE relationship route, which does not serve GET.
            assert client.get(path, headers={"Authorization": "Bearer x"}).status_code in {404, 405}
