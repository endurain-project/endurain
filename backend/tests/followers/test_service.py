"""The follow rules: who may see a network, who may follow, accept and remove, and what each change records."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import core.event_metadata as core_event_metadata
import core.exceptions as core_exceptions
import modules.followers.audit_actions as followers_audit_actions
import modules.followers.constants as followers_constants
import modules.followers.crud as followers_crud
import modules.followers.events as followers_events
import modules.followers.models as followers_models
import modules.followers.service as followers_service
from tests._factories.followers import make_block, make_decline, make_follow, make_follow_at
from tests._factories.users import make_user
from tests.followers.conftest import audited

_PENDING = followers_constants.FollowStatus.PENDING
_ACCEPTED = followers_constants.FollowStatus.ACCEPTED
_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)


def _stored(db, follower_id: uuid.UUID, followee_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(followers_models.Follower.status).where(
            followers_models.Follower.follower_id == follower_id,
            followers_models.Follower.followee_id == followee_id,
        )
    )


class TestNetworkPrivacy:
    @pytest.mark.parametrize("listing", ["list_followers", "list_following"])
    def test_a_stranger_is_answered_as_if_the_user_did_not_exist(self, db, alice, bob, listing):
        with pytest.raises(core_exceptions.AccessConcealedError):
            getattr(followers_service, listing)(alice.id, bob.id, db)

    @pytest.mark.parametrize("listing", ["list_followers", "list_following"])
    def test_a_requester_still_pending_is_a_stranger(self, db, alice, bob, listing):
        make_follow(db, bob.id, alice.id, accepted=False)

        with pytest.raises(core_exceptions.AccessConcealedError):
            getattr(followers_service, listing)(alice.id, bob.id, db)

    def test_the_owner_sees_pending_requests_unless_they_ask_for_accepted_only(self, db, alice, bob, carol):
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=False)

        everyone = followers_service.list_followers(alice.id, alice.id, db)
        accepted = followers_service.list_followers(alice.id, alice.id, db, accepted_only=True)

        assert (everyone.total, {row.follower_id for row in everyone.items}) == (2, {bob.id, carol.id})
        assert (accepted.total, [row.follower_id for row in accepted.items]) == (1, [bob.id])

    def test_an_accepted_follower_sees_only_accepted_relationships_and_their_count(self, db, alice, bob, carol):
        viewer = make_user(db)
        make_follow(db, viewer.id, alice.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=False)
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=False)

        followers = followers_service.list_followers(alice.id, viewer.id, db, accepted_only=False)
        following = followers_service.list_following(alice.id, viewer.id, db, accepted_only=False)

        assert (followers.total, {row.follower_id for row in followers.items}) == (2, {viewer.id, bob.id})
        assert (following.total, [row.followee_id for row in following.items]) == (1, [bob.id])

    def test_the_total_counts_every_row_of_the_filter_not_just_the_page(self, db, alice):
        for _ in range(3):
            make_follow(db, make_user(db).id, alice.id, accepted=True)

        page = followers_service.list_followers(alice.id, alice.id, db, page_number=2, num_records=2)

        assert (len(page.items), page.total, page.page, page.next) == (1, 3, 2, None)

    def test_profile_counts_are_the_accepted_relationships_for_the_owner_and_accepted_followers(
        self, db, alice, bob, carol
    ):
        viewer = make_user(db)
        make_follow(db, viewer.id, alice.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=False)
        make_follow(db, alice.id, carol.id, accepted=True)
        make_follow(db, alice.id, viewer.id, accepted=False)

        for requester in (alice.id, viewer.id):
            counts = followers_service.get_profile_follow_counts(alice.id, requester, db)
            assert counts is not None
            assert (counts.followers, counts.following) == (1, 1)

    def test_profile_counts_are_absent_when_the_network_is_private_to_the_viewer(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)

        assert followers_service.get_profile_follow_counts(alice.id, bob.id, db) is None
        assert followers_service.get_profile_follow_counts(alice.id, make_user(db).id, db) is None


class TestListsCarryTheOtherUsersProfile:
    def test_followers_carry_the_follower_profile(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=True)

        page = followers_service.list_followers(alice.id, alice.id, db)

        assert set(page.users) == {bob.id}
        assert (page.users[bob.id].username, page.users[bob.id].name) == (bob.username, bob.name)

    def test_following_carries_the_followee_profile(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=True)

        page = followers_service.list_following(alice.id, alice.id, db)

        assert set(page.users) == {bob.id}

    def test_pending_requests_carry_the_requester_profile(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)

        page = followers_service.list_pending_requests(alice.id, db)

        assert [row.follower_id for row in page.items] == [bob.id]
        assert set(page.users) == {bob.id}

    @pytest.mark.parametrize("state", ["inactive", "pending"])
    def test_a_user_without_a_public_profile_has_a_row_but_no_entry(self, db, alice, bob, carol, hide, state):
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=True)
        hide(db, bob.id, state)

        page = followers_service.list_followers(alice.id, alice.id, db)

        assert {row.follower_id for row in page.items} == {bob.id, carol.id}
        assert set(page.users) == {carol.id}

    def test_an_empty_list_has_no_users(self, db, alice):
        page = followers_service.list_followers(alice.id, alice.id, db)

        assert (page.items, page.users, page.total) == ([], {}, 0)

    def test_pending_requests_page_with_a_total_of_all_of_them(self, db, alice):
        for index in range(3):
            make_follow_at(db, make_user(db).id, alice.id, _NOW + timedelta(minutes=index), accepted=False)

        first = followers_service.list_pending_requests(alice.id, db, page_number=1, num_records=2)

        assert (len(first.items), first.total, first.next) == (2, 3, 2)


class TestFollowUser:
    def test_a_follow_is_stored_pending_and_announced_to_the_target(self, db, alice, bob, published):
        created = followers_service.follow_user(alice.id, bob.id, db)

        assert (created.follower_id, created.followee_id, created.status) == (alice.id, bob.id, _PENDING)
        assert _stored(db, alice.id, bob.id) == "pending"
        [event] = published
        assert event.event_type == followers_events.FOLLOWER_REQUESTED
        assert event.source == "api:follow_user"
        assert event.payload == {"requester_user_id": str(alice.id), "target_user_id": str(bob.id)}
        assert event.metadata[core_event_metadata.META_USER_ID] == str(bob.id)
        assert event.schema_version == followers_events.FollowerRequestedPayload.SCHEMA_VERSION

    def test_a_request_is_not_audited(self, db, alice, bob):
        followers_service.follow_user(alice.id, bob.id, db)

        assert audited(db) == []

    def test_following_yourself_is_refused(self, db, alice, published):
        with pytest.raises(core_exceptions.InvalidInputError):
            followers_service.follow_user(alice.id, alice.id, db)

        assert published == []

    def test_asking_twice_is_a_conflict_and_announces_nothing_more(self, db, alice, bob, published):
        followers_service.follow_user(alice.id, bob.id, db)

        with pytest.raises(core_exceptions.ConflictError):
            followers_service.follow_user(alice.id, bob.id, db)

        assert len(published) == 1

    @pytest.mark.parametrize("state", ["missing", "inactive", "pending"])
    def test_a_target_that_cannot_be_followed_is_not_found_even_when_its_requests_are_full(
        self, db, alice, bob, hide, published, monkeypatch, state
    ):
        monkeypatch.setattr(followers_constants, "MAX_PENDING_REQUESTS", 1)
        make_follow(db, make_user(db).id, bob.id, accepted=False)
        target = bob.id
        if state == "missing":
            target = uuid.uuid4()
        else:
            hide(db, bob.id, state)

        with pytest.raises(core_exceptions.NotFoundError) as refused:
            followers_service.follow_user(alice.id, target, db)

        assert (refused.value.status_code, refused.value.detail) == (404, "User not found")
        assert published == []

    def test_a_target_with_too_many_pending_requests_is_a_conflict(self, db, alice, bob, published, monkeypatch):
        monkeypatch.setattr(followers_constants, "MAX_PENDING_REQUESTS", 2)
        for _ in range(2):
            make_follow(db, make_user(db).id, bob.id, accepted=False)

        with pytest.raises(core_exceptions.ConflictError) as refused:
            followers_service.follow_user(alice.id, bob.id, db)

        assert refused.value.detail == "This user has too many pending follow requests"
        assert _stored(db, alice.id, bob.id) is None
        assert published == []

    def test_accepted_followers_do_not_count_against_the_pending_cap(self, db, alice, bob, monkeypatch):
        monkeypatch.setattr(followers_constants, "MAX_PENDING_REQUESTS", 1)
        make_follow(db, make_user(db).id, bob.id, accepted=True)

        followers_service.follow_user(alice.id, bob.id, db)

        assert _stored(db, alice.id, bob.id) == "pending"

    def test_a_blocked_requester_is_told_what_a_hidden_target_is_told(self, db, alice, bob, hide):
        make_block(db, bob.id, alice.id)
        with pytest.raises(core_exceptions.NotFoundError) as blocked:
            followers_service.follow_user(alice.id, bob.id, db)
        hide(db, bob.id, "inactive")
        with pytest.raises(core_exceptions.NotFoundError) as hidden:
            followers_service.follow_user(alice.id, bob.id, db)

        assert (blocked.value.status_code, blocked.value.detail) == (hidden.value.status_code, hidden.value.detail)

    def test_the_blocker_cannot_follow_the_user_they_blocked(self, db, alice, bob, published):
        make_block(db, alice.id, bob.id)

        with pytest.raises(core_exceptions.ConflictError) as refused:
            followers_service.follow_user(alice.id, bob.id, db)

        assert (refused.value.status_code, refused.value.detail) == (409, "Unblock this user first")
        assert _stored(db, alice.id, bob.id) is None
        assert published == []

    def test_a_declined_requester_waits_seven_days(self, db, alice, bob, published):
        declined_at = datetime.now(UTC) - timedelta(days=1)
        make_decline(db, alice.id, bob.id, declined_at)

        with pytest.raises(core_exceptions.TooManyRequestsError) as refused:
            followers_service.follow_user(alice.id, bob.id, db)

        assert refused.value.status_code == 429
        assert refused.value.scope == core_exceptions.TooManyRequestsScope.FOLLOW_REQUEST
        assert refused.value.retry_at == declined_at + followers_constants.FOLLOW_REQUEST_COOLDOWN
        assert _stored(db, alice.id, bob.id) is None
        assert published == []

    def test_the_cooldown_ends_after_seven_days(self, db, alice, bob):
        make_decline(
            db, alice.id, bob.id, datetime.now(UTC) - followers_constants.FOLLOW_REQUEST_COOLDOWN - timedelta(minutes=1)
        )

        followers_service.follow_user(alice.id, bob.id, db)

        assert _stored(db, alice.id, bob.id) == "pending"

    def test_a_decline_by_someone_else_does_not_hold_the_requester_back(self, db, alice, bob, carol):
        make_decline(db, alice.id, carol.id, datetime.now(UTC))

        followers_service.follow_user(alice.id, bob.id, db)

        assert _stored(db, alice.id, bob.id) == "pending"


class TestAcceptFollowRequest:
    def test_accepting_stores_it_audits_it_and_tells_the_requester(self, db, alice, bob, published):
        make_follow(db, bob.id, alice.id, accepted=False)

        accepted = followers_service.accept_follow_request(alice.id, bob.id, db)

        assert (accepted.follower_id, accepted.followee_id, accepted.status) == (bob.id, alice.id, _ACCEPTED)
        assert _stored(db, bob.id, alice.id) == "accepted"
        assert audited(db) == [(followers_audit_actions.FOLLOW_ACCEPT.id, str(bob.id), str(alice.id))]
        [event] = published
        assert event.event_type == followers_events.FOLLOWER_ACCEPTED
        assert event.source == "api:accept_follow_request"
        assert event.payload == {"accepter_user_id": str(alice.id), "requester_user_id": str(bob.id)}
        assert event.metadata[core_event_metadata.META_USER_ID] == str(bob.id)

    def test_a_request_that_does_not_exist_is_not_found_and_leaves_no_trace(self, db, alice, bob, published):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.accept_follow_request(alice.id, bob.id, db)

        assert (audited(db), published) == ([], [])

    def test_accepting_twice_is_not_found_the_second_time_and_audits_once(self, db, alice, bob, published):
        make_follow(db, bob.id, alice.id, accepted=False)
        followers_service.accept_follow_request(alice.id, bob.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.accept_follow_request(alice.id, bob.id, db)

        assert len(audited(db)) == 1
        assert len(published) == 1

    def test_a_follower_at_the_followee_cap_cannot_be_accepted(self, db, alice, bob, carol, published, monkeypatch):
        monkeypatch.setattr(followers_constants, "MAX_ACCEPTED_FOLLOWEES", 1)
        make_follow(db, bob.id, carol.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=False)

        with pytest.raises(core_exceptions.ConflictError) as refused:
            followers_service.accept_follow_request(alice.id, bob.id, db)

        assert refused.value.detail == "This user already follows the maximum number of users"
        assert _stored(db, bob.id, alice.id) == "pending"
        assert (audited(db), published) == ([], [])

    def test_pending_requests_do_not_count_against_the_followee_cap(self, db, alice, bob, carol, monkeypatch):
        monkeypatch.setattr(followers_constants, "MAX_ACCEPTED_FOLLOWEES", 1)
        make_follow(db, bob.id, carol.id, accepted=False)
        make_follow(db, bob.id, alice.id, accepted=False)

        followers_service.accept_follow_request(alice.id, bob.id, db)

        assert _stored(db, bob.id, alice.id) == "accepted"

    def test_a_request_from_a_blocked_user_cannot_be_accepted(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)
        followers_service.block_user(alice.id, bob.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.accept_follow_request(alice.id, bob.id, db)


class TestRejectFollowRequest:
    def test_declining_removes_the_request_records_the_decline_and_tells_the_target(self, db, alice, bob, published):
        make_follow(db, bob.id, alice.id, accepted=False)

        followers_service.reject_follow_request(alice.id, bob.id, db)

        assert _stored(db, bob.id, alice.id) is None
        declined_at = followers_crud.get_last_decline_at(bob.id, alice.id, db)
        assert declined_at is not None and datetime.now(UTC) - declined_at < timedelta(minutes=1)
        [event] = published
        assert event.event_type == followers_events.FOLLOWER_REQUEST_REMOVED
        assert event.source == "api:reject_follow_request"
        assert event.payload == {"requester_user_id": str(bob.id), "target_user_id": str(alice.id)}
        assert event.metadata[core_event_metadata.META_USER_ID] == str(alice.id)
        assert audited(db) == []

    def test_declining_cannot_remove_an_accepted_follower(self, db, alice, bob, published):
        make_follow(db, bob.id, alice.id, accepted=True)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.reject_follow_request(alice.id, bob.id, db)

        assert _stored(db, bob.id, alice.id) == "accepted"
        assert followers_crud.get_last_decline_at(bob.id, alice.id, db) is None
        assert published == []

    def test_declining_a_request_that_does_not_exist_is_not_found(self, db, alice, bob):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.reject_follow_request(alice.id, bob.id, db)


class TestDeleteRelationship:
    @pytest.mark.parametrize("caller", ["follower", "followee"])
    def test_either_party_ends_an_accepted_relationship_and_it_is_audited(self, db, alice, bob, published, caller):
        make_follow(db, alice.id, bob.id, accepted=True)
        requester = alice.id if caller == "follower" else bob.id

        followers_service.delete_relationship(bob.id, alice.id, requester, db)

        assert _stored(db, alice.id, bob.id) is None
        assert audited(db) == [(followers_audit_actions.FOLLOW_REMOVE.id, str(alice.id), str(bob.id))]
        assert published == []
        assert followers_crud.get_last_decline_at(alice.id, bob.id, db) is None

    def test_a_follower_withdrawing_a_pending_request_takes_back_its_notification_and_is_not_a_decline(
        self, db, alice, bob, published
    ):
        make_follow(db, alice.id, bob.id, accepted=False)

        followers_service.delete_relationship(bob.id, alice.id, alice.id, db)

        assert _stored(db, alice.id, bob.id) is None
        assert followers_crud.get_last_decline_at(alice.id, bob.id, db) is None
        assert audited(db) == []
        [event] = published
        assert event.event_type == followers_events.FOLLOWER_REQUEST_REMOVED
        assert event.source == "api:delete_follow_relationship"
        assert event.payload == {"requester_user_id": str(alice.id), "target_user_id": str(bob.id)}

    def test_the_followee_removing_a_pending_request_also_records_the_decline(self, db, alice, bob, published):
        make_follow(db, alice.id, bob.id, accepted=False)

        followers_service.delete_relationship(bob.id, alice.id, bob.id, db)

        assert followers_crud.get_last_decline_at(alice.id, bob.id, db) is not None
        assert len(published) == 1

    def test_a_third_party_is_answered_as_if_the_relationship_did_not_exist(self, db, alice, bob, carol, published):
        make_follow(db, alice.id, bob.id, accepted=True)

        with pytest.raises(core_exceptions.AccessConcealedError):
            followers_service.delete_relationship(bob.id, alice.id, carol.id, db)

        assert _stored(db, alice.id, bob.id) == "accepted"
        assert (audited(db), published) == ([], [])

    def test_a_relationship_that_does_not_exist_is_not_found(self, db, alice, bob):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.delete_relationship(bob.id, alice.id, alice.id, db)


class TestRelationshipBetweenTwoUsers:
    def test_both_directions_and_the_callers_block_are_reported(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=False)
        make_block(db, alice.id, bob.id)

        mine = followers_service.get_user_relationship(bob.id, alice.id, db)
        theirs = followers_service.get_user_relationship(alice.id, bob.id, db)

        assert (mine.outgoing.status, mine.incoming.status, mine.is_blocked) == (_ACCEPTED, _PENDING, True)
        assert (theirs.outgoing.status, theirs.incoming.status, theirs.is_blocked) == (_PENDING, _ACCEPTED, False)

    def test_unrelated_users_have_no_relationship(self, db, alice, bob):
        relationship = followers_service.get_user_relationship(bob.id, alice.id, db)

        assert (relationship.outgoing, relationship.incoming, relationship.is_blocked) == (None, None, False)


class TestStateChangesAreLogged:
    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda a, b, db: followers_service.follow_user(a, b, db), "Follow requested"),
            (lambda a, b, db: followers_service.accept_follow_request(b, a, db), "Follow request accepted"),
            (lambda a, b, db: followers_service.reject_follow_request(b, a, db), "Follow request rejected"),
            (lambda a, b, db: followers_service.delete_relationship(b, a, a, db), "Deleted a follow relationship"),
        ],
        ids=["follow", "accept", "reject", "delete"],
    )
    def test_a_completed_change_is_logged_once_at_info(self, db, alice, bob, caplog, change, message):
        if message != "Follow requested":
            make_follow(db, alice.id, bob.id, accepted=False)

        with caplog.at_level(logging.INFO, logger=followers_service.logger.name):
            change(alice.id, bob.id, db)

        records = [r for r in caplog.records if r.name == followers_service.logger.name and r.getMessage() == message]
        assert [r.levelno for r in records] == [logging.INFO]


def test_a_relationships_whole_life_is_audited_in_order(db, alice, bob):
    make_follow(db, bob.id, alice.id, accepted=False)
    followers_service.accept_follow_request(alice.id, bob.id, db)
    followers_service.delete_relationship(alice.id, bob.id, bob.id, db)
    followers_service.block_user(alice.id, bob.id, db)
    followers_service.unblock_user(alice.id, bob.id, db)

    assert [action for action, _target, _owner in audited(db)] == [
        followers_audit_actions.FOLLOW_ACCEPT.id,
        followers_audit_actions.FOLLOW_REMOVE.id,
        followers_audit_actions.BLOCK_ADD.id,
        followers_audit_actions.BLOCK_REMOVE.id,
    ]
