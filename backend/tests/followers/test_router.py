"""The followers routes through the production application: real authentication, scopes, handlers and database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

import core.config as core_config
import modules.followers.models as followers_models
import modules.users.users.models as users_models
from tests._factories.followers import make_block, make_decline, make_follow, make_follow_at
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
_ANY_ID = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


@pytest.fixture
def make_person(committed_sessions):
    """Return a function that commits an active user and returns it."""

    def make(**fields):
        with committed_sessions() as db:
            created = make_user(db, **fields)
            db.commit()
        return created

    return make


@pytest.fixture
def arrange(committed_sessions):
    """Return a function that commits what ``build(db)`` stages."""

    def run(build):
        with committed_sessions() as db:
            build(db)
            db.commit()

    return run


@pytest.fixture
def alice(make_person):
    return make_person()


@pytest.fixture
def bob(make_person):
    return make_person()


@pytest.fixture
def carol(make_person):
    return make_person()


@pytest.fixture
def me(sign_in, alice):
    return sign_in(alice)


@pytest.fixture
def stored(committed_sessions):
    """Return a function that reads a follow row's status back in a new session, or ``None`` when it is gone."""

    def read(follower_id, followee_id):
        with committed_sessions() as db:
            return db.scalar(
                select(followers_models.Follower.status).where(
                    followers_models.Follower.follower_id == follower_id,
                    followers_models.Follower.followee_id == followee_id,
                )
            )

    return read


def _count(committed_sessions, model) -> int:
    with committed_sessions() as db:
        return db.scalar(select(func.count()).select_from(model))


class TestListFollowers:
    def test_the_owner_lists_followers_with_their_profiles_and_the_total(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow_at(db, bob.id, alice.id, _NOW, accepted=True))
        arrange(lambda db: make_follow_at(db, carol.id, alice.id, _NOW + timedelta(hours=1), accepted=False))

        response = me.client.get(f"{_API}/users/{alice.id}/followers")

        assert response.status_code == 200
        body = response.json()
        assert [(row["follower_id"], row["followee_id"], row["status"]) for row in body["items"]] == [
            (str(bob.id), str(alice.id), "accepted"),
            (str(carol.id), str(alice.id), "pending"),
        ]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert body["users"][str(bob.id)] == {
            "id": str(bob.id),
            "name": bob.name,
            "username": bob.username,
            "city": None,
            "photo_path": None,
        }
        assert set(body["users"]) == {str(bob.id), str(carol.id)}

    def test_accepted_only_leaves_out_pending_requests(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=True))
        arrange(lambda db: make_follow(db, carol.id, alice.id, accepted=False))

        body = me.client.get(f"{_API}/users/{alice.id}/followers", params={"accepted_only": "true"}).json()

        assert [row["follower_id"] for row in body["items"]] == [str(bob.id)]
        assert body["total"] == 1

    def test_a_page_holds_its_slice_and_names_the_next_one(self, me, alice, arrange, make_person):
        followers = [make_person() for _ in range(3)]
        for index, follower in enumerate(followers):
            arrange(
                lambda db, f=follower, i=index: make_follow_at(
                    db, f.id, alice.id, _NOW + timedelta(hours=i), accepted=True
                )
            )

        first = me.client.get(f"{_API}/users/{alice.id}/followers", params={"page_number": 1, "num_records": 2}).json()
        last = me.client.get(f"{_API}/users/{alice.id}/followers", params={"page_number": 2, "num_records": 2}).json()

        assert ([row["follower_id"] for row in first["items"]], first["total"], first["next"]) == (
            [str(followers[0].id), str(followers[1].id)],
            3,
            2,
        )
        assert ([row["follower_id"] for row in last["items"]], last["next"]) == ([str(followers[2].id)], None)

    def test_a_page_size_over_the_cap_is_refused(self, me, alice):
        assert me.client.get(f"{_API}/users/{alice.id}/followers", params={"num_records": 5000}).status_code == 422

    def test_a_stranger_is_answered_not_found(self, me, bob, carol, arrange):
        arrange(lambda db: make_follow(db, carol.id, bob.id, accepted=True))

        response = me.client.get(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 404

    def test_a_requester_still_pending_is_answered_not_found(self, me, alice, bob, arrange):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=False))

        assert me.client.get(f"{_API}/users/{bob.id}/followers").status_code == 404

    def test_an_accepted_follower_sees_the_accepted_followers_only(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))
        arrange(lambda db: make_follow(db, carol.id, bob.id, accepted=False))

        response = me.client.get(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 200
        body = response.json()
        assert [row["follower_id"] for row in body["items"]] == [str(alice.id)]
        assert body["total"] == 1

    def test_an_empty_list_has_an_empty_users_object(self, me, alice):
        body = me.client.get(f"{_API}/users/{alice.id}/followers").json()

        assert (body["items"], body["users"], body["total"]) == ([], {}, 0)

    def test_a_follower_without_a_public_profile_has_a_row_but_no_user_entry(
        self, me, alice, bob, arrange, committed_sessions
    ):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=True))
        with committed_sessions() as db:
            db.get(users_models.Users, bob.id).active = False
            db.commit()

        body = me.client.get(f"{_API}/users/{alice.id}/followers").json()

        assert [row["follower_id"] for row in body["items"]] == [str(bob.id)]
        assert body["users"] == {}


class TestListFollowing:
    def test_the_owner_lists_who_they_follow_with_profiles(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))
        arrange(lambda db: make_follow(db, alice.id, carol.id, accepted=False))
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=True))

        body = me.client.get(f"{_API}/users/{alice.id}/following").json()

        assert {row["followee_id"] for row in body["items"]} == {str(bob.id), str(carol.id)}
        assert body["total"] == 2
        assert set(body["users"]) == {str(bob.id), str(carol.id)}

    def test_a_stranger_is_answered_not_found(self, me, bob):
        assert me.client.get(f"{_API}/users/{bob.id}/following").status_code == 404

    def test_an_accepted_follower_sees_only_the_accepted_ones(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))
        arrange(lambda db: make_follow(db, bob.id, carol.id, accepted=True))
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))

        body = me.client.get(f"{_API}/users/{bob.id}/following").json()

        assert [row["followee_id"] for row in body["items"]] == [str(carol.id)]


class TestReadRelationship:
    def test_both_directions_and_the_block_are_reported(self, me, alice, bob, arrange):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))
        arrange(lambda db: make_block(db, alice.id, bob.id))

        response = me.client.get(f"{_API}/users/{bob.id}/relationship")

        assert response.status_code == 200
        assert response.json() == {
            "outgoing": {"follower_id": str(alice.id), "followee_id": str(bob.id), "status": "accepted"},
            "incoming": {"follower_id": str(bob.id), "followee_id": str(alice.id), "status": "pending"},
            "is_blocked": True,
        }

    def test_unrelated_users_have_an_empty_relationship(self, me, bob):
        response = me.client.get(f"{_API}/users/{bob.id}/relationship")

        assert response.json() == {"outgoing": None, "incoming": None, "is_blocked": False}

    def test_a_relationship_between_two_other_users_is_not_visible(self, me, bob, carol, arrange):
        arrange(lambda db: make_follow(db, bob.id, carol.id, accepted=True))

        body = me.client.get(f"{_API}/users/{bob.id}/relationship").json()

        assert (body["outgoing"], body["incoming"]) == (None, None)


class TestFollowUser:
    def test_a_follow_is_created_pending(self, me, alice, bob, stored):
        response = me.client.post(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 201
        assert response.json() == {"follower_id": str(alice.id), "followee_id": str(bob.id), "status": "pending"}
        assert stored(alice.id, bob.id) == "pending"

    def test_following_yourself_is_refused(self, me, alice, committed_sessions):
        response = me.client.post(f"{_API}/users/{alice.id}/followers")

        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot follow yourself"
        assert _count(committed_sessions, followers_models.Follower) == 0

    def test_following_twice_is_a_conflict(self, me, alice, bob, committed_sessions):
        assert me.client.post(f"{_API}/users/{bob.id}/followers").status_code == 201

        response = me.client.post(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 409
        assert _count(committed_sessions, followers_models.Follower) == 1

    def test_a_user_that_does_not_exist_is_not_found(self, me):
        assert me.client.post(f"{_API}/users/{uuid.uuid4()}/followers").status_code == 404

    @pytest.mark.parametrize("state", ["inactive", "pending"])
    def test_a_user_without_a_public_profile_is_not_found(self, me, make_person, committed_sessions, state):
        target = make_person(active=state != "inactive", pending_admin_approval=state == "pending")

        assert me.client.post(f"{_API}/users/{target.id}/followers").status_code == 404

    def test_a_user_who_blocked_the_caller_is_not_found(self, me, alice, bob, arrange, committed_sessions):
        arrange(lambda db: make_block(db, bob.id, alice.id))

        assert me.client.post(f"{_API}/users/{bob.id}/followers").status_code == 404
        assert _count(committed_sessions, followers_models.Follower) == 0

    def test_following_a_user_the_caller_blocked_is_a_conflict(self, me, alice, bob, arrange):
        arrange(lambda db: make_block(db, alice.id, bob.id))

        response = me.client.post(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 409

    def test_a_decline_makes_the_requester_wait_and_says_until_when(self, me, alice, bob, arrange, committed_sessions):
        declined_at = datetime.now(UTC) - timedelta(days=1)
        arrange(lambda db: make_decline(db, alice.id, bob.id, declined_at))

        response = me.client.post(f"{_API}/users/{bob.id}/followers")

        assert response.status_code == 429
        assert 5 * 86400 < int(response.headers["Retry-After"]) <= 6 * 86400
        assert _count(committed_sessions, followers_models.Follower) == 0


class TestListFollowRequests:
    def test_the_caller_lists_only_the_requests_addressed_to_them(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))
        arrange(lambda db: make_follow(db, carol.id, alice.id, accepted=True))
        arrange(lambda db: make_follow(db, alice.id, carol.id, accepted=False))
        arrange(lambda db: make_follow(db, carol.id, bob.id, accepted=False))

        response = me.client.get(f"{_API}/profile/follow-requests")

        assert response.status_code == 200
        body = response.json()
        assert [(row["follower_id"], row["followee_id"], row["status"]) for row in body["items"]] == [
            (str(bob.id), str(alice.id), "pending")
        ]
        assert body["total"] == 1
        assert set(body["users"]) == {str(bob.id)}

    def test_no_requests_is_an_empty_page(self, me):
        body = me.client.get(f"{_API}/profile/follow-requests").json()

        assert (body["items"], body["total"], body["users"]) == ([], 0, {})


class TestAcceptFollowRequest:
    def test_accepting_answers_with_the_stored_row(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))

        response = me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept")

        assert response.status_code == 200
        assert response.json() == {"follower_id": str(bob.id), "followee_id": str(alice.id), "status": "accepted"}
        assert stored(bob.id, alice.id) == "accepted"

    def test_a_request_that_does_not_exist_is_not_found(self, me, bob):
        assert me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept").status_code == 404

    def test_a_request_the_caller_sent_cannot_be_accepted_by_them(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=False))

        assert me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept").status_code == 404
        assert stored(alice.id, bob.id) == "pending"

    def test_accepting_twice_is_not_found_the_second_time(self, me, alice, bob, arrange):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))
        assert me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept").status_code == 200

        assert me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept").status_code == 404

    def test_a_request_from_a_blocked_user_cannot_be_accepted(self, me, alice, bob, arrange):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))
        assert me.client.put(f"{_API}/profile/blocked-users/{bob.id}").status_code == 204

        assert me.client.post(f"{_API}/profile/follow-requests/{bob.id}/accept").status_code == 404

    def test_the_old_patch_with_a_status_body_is_gone(self, me, bob):
        response = me.client.patch(f"{_API}/profile/follow-requests/{bob.id}", json={"status": "accepted"})

        assert response.status_code == 405


class TestRejectFollowRequest:
    def test_declining_removes_the_request_and_blocks_an_immediate_new_one(
        self, me, alice, bob, arrange, stored, sign_in
    ):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))

        response = me.client.delete(f"{_API}/profile/follow-requests/{bob.id}")

        assert response.status_code == 204
        assert response.content == b""
        assert stored(bob.id, alice.id) is None
        assert sign_in(bob).client.post(f"{_API}/users/{alice.id}/followers").status_code == 429

    def test_declining_cannot_remove_an_accepted_follower(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=True))

        assert me.client.delete(f"{_API}/profile/follow-requests/{bob.id}").status_code == 404
        assert stored(bob.id, alice.id) == "accepted"

    def test_a_request_that_does_not_exist_is_not_found(self, me, bob):
        assert me.client.delete(f"{_API}/profile/follow-requests/{bob.id}").status_code == 404


class TestDeleteFollowRelationship:
    def test_unfollowing_is_the_caller_as_follower(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))

        response = me.client.delete(f"{_API}/users/{bob.id}/followers/{alice.id}")

        assert response.status_code == 204
        assert stored(alice.id, bob.id) is None

    def test_removing_a_follower_is_the_caller_as_followee(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=True))

        response = me.client.delete(f"{_API}/users/{alice.id}/followers/{bob.id}")

        assert response.status_code == 204
        assert stored(bob.id, alice.id) is None

    def test_a_third_party_cannot_delete_someone_elses_relationship(self, me, bob, carol, arrange, stored):
        arrange(lambda db: make_follow(db, bob.id, carol.id, accepted=True))

        response = me.client.delete(f"{_API}/users/{carol.id}/followers/{bob.id}")

        assert response.status_code == 404
        assert stored(bob.id, carol.id) == "accepted"

    def test_a_relationship_that_does_not_exist_is_not_found(self, me, alice, bob):
        assert me.client.delete(f"{_API}/users/{bob.id}/followers/{alice.id}").status_code == 404


class TestMalformedIds:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/users/not-a-uuid/followers"),
            ("get", "/users/7/followers"),
            ("post", "/users/not-a-uuid/followers"),
            ("delete", f"/users/{_ANY_ID}/followers/not-a-uuid"),
            ("post", "/profile/follow-requests/not-a-uuid/accept"),
            ("delete", "/profile/follow-requests/not-a-uuid"),
            ("put", "/profile/blocked-users/not-a-uuid"),
            ("delete", "/profile/blocked-users/not-a-uuid"),
        ],
    )
    def test_a_path_id_that_is_not_a_uuid_is_refused(self, me, method, path):
        assert getattr(me.client, method)(f"{_API}{path}").status_code == 422


class TestRemovedCountEndpoints:
    @pytest.mark.parametrize("side", ["followers", "following"])
    def test_the_count_paths_are_gone(self, me, alice, side):
        assert me.client.get(f"{_API}/users/{alice.id}/{side}/count").status_code in {404, 405}


class TestBlockedUsers:
    def test_blocking_stores_the_block_and_answers_204(self, me, alice, bob, committed_sessions):
        response = me.client.put(f"{_API}/profile/blocked-users/{bob.id}")

        assert response.status_code == 204
        assert response.content == b""
        with committed_sessions() as db:
            assert db.scalar(select(func.count()).select_from(followers_models.FollowerBlock)) == 1

    def test_blocking_yourself_is_refused(self, me, alice, committed_sessions):
        response = me.client.put(f"{_API}/profile/blocked-users/{alice.id}")

        assert response.status_code == 422
        assert _count(committed_sessions, followers_models.FollowerBlock) == 0

    def test_blocking_a_user_that_does_not_exist_answers_as_for_one_that_does(self, me, committed_sessions):
        response = me.client.put(f"{_API}/profile/blocked-users/{uuid.uuid4()}")

        assert response.status_code == 204
        assert _count(committed_sessions, followers_models.FollowerBlock) == 0

    def test_blocking_removes_the_follows_between_the_two(self, me, alice, bob, arrange, stored):
        arrange(lambda db: make_follow(db, alice.id, bob.id, accepted=True))
        arrange(lambda db: make_follow(db, bob.id, alice.id, accepted=False))

        assert me.client.put(f"{_API}/profile/blocked-users/{bob.id}").status_code == 204

        assert (stored(alice.id, bob.id), stored(bob.id, alice.id)) == (None, None)

    def test_unblocking_removes_the_block(self, me, alice, bob, arrange, committed_sessions):
        arrange(lambda db: make_block(db, alice.id, bob.id))

        response = me.client.delete(f"{_API}/profile/blocked-users/{bob.id}")

        assert response.status_code == 204
        assert _count(committed_sessions, followers_models.FollowerBlock) == 0

    def test_unblocking_someone_not_blocked_is_not_found(self, me, bob):
        assert me.client.delete(f"{_API}/profile/blocked-users/{bob.id}").status_code == 404

    def test_the_list_holds_the_public_profiles_newest_block_first(self, me, alice, bob, carol, arrange):
        arrange(lambda db: make_block(db, alice.id, bob.id, created_at=_NOW))
        arrange(lambda db: make_block(db, alice.id, carol.id, created_at=_NOW + timedelta(hours=1)))
        arrange(lambda db: make_block(db, bob.id, alice.id))

        response = me.client.get(f"{_API}/profile/blocked-users")

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(carol.id), str(bob.id)]
        assert body["items"][0] == {
            "id": str(carol.id),
            "name": carol.name,
            "username": carol.username,
            "city": None,
            "photo_path": None,
        }
        assert (body["total"], body["next"]) == (2, None)

    def test_the_list_pages(self, me, alice, arrange, make_person):
        blocked = [make_person() for _ in range(3)]
        for index, user in enumerate(blocked):
            arrange(lambda db, u=user, i=index: make_block(db, alice.id, u.id, created_at=_NOW + timedelta(hours=i)))

        body = me.client.get(f"{_API}/profile/blocked-users", params={"page_number": 1, "num_records": 2}).json()

        assert ([item["id"] for item in body["items"]], body["total"], body["next"]) == (
            [str(blocked[2].id), str(blocked[1].id)],
            3,
            2,
        )

    def test_an_empty_list_is_an_empty_page(self, me):
        body = me.client.get(f"{_API}/profile/blocked-users").json()

        assert (body["items"], body["total"]) == ([], 0)
