"""Follow relationships, blocks and declines as the module stores and reads them, on the real database."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.followers.constants as followers_constants
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
import modules.users.users.models as users_models
from tests._factories.followers import make_block, make_decline, make_follow, make_follow_at
from tests._factories.users import make_user

_PENDING = followers_constants.FollowStatus.PENDING
_ACCEPTED = followers_constants.FollowStatus.ACCEPTED
_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)


class TestListingFollowers:
    def test_the_followers_of_a_user_are_the_rows_where_they_are_followed(self, db, alice, bob, carol):
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=True)

        rows = followers_crud.get_all_followers_by_user_id(alice.id, db)

        assert [(row.follower_id, row.followee_id) for row in rows] == [(bob.id, alice.id)]

    def test_accepted_only_leaves_out_pending_requests(self, db, alice, bob, carol):
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=False)

        everyone = followers_crud.get_all_followers_by_user_id(alice.id, db)
        accepted = followers_crud.get_all_followers_by_user_id(alice.id, db, accepted_only=True)

        assert {row.follower_id for row in everyone} == {bob.id, carol.id}
        assert [(row.follower_id, row.status) for row in accepted] == [(bob.id, _ACCEPTED)]

    def test_who_a_user_follows_are_the_rows_where_they_follow(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=False)
        make_follow(db, bob.id, alice.id, accepted=True)

        everyone = followers_crud.get_all_following_by_user_id(alice.id, db)
        accepted = followers_crud.get_all_following_by_user_id(alice.id, db, accepted_only=True)

        assert {row.followee_id for row in everyone} == {bob.id, carol.id}
        assert [row.followee_id for row in accepted] == [bob.id]

    def test_a_user_nobody_follows_has_an_empty_list(self, db, alice):
        assert followers_crud.get_all_followers_by_user_id(alice.id, db) == []
        assert followers_crud.get_all_following_by_user_id(alice.id, db) == []

    def test_the_lists_run_by_creation_time_whatever_the_ids(self, db, alice, bob, carol):
        make_follow_at(db, carol.id, alice.id, _NOW, accepted=True)
        make_follow_at(db, bob.id, alice.id, _NOW - timedelta(hours=1), accepted=True)
        make_follow_at(db, alice.id, bob.id, _NOW, accepted=True)
        make_follow_at(db, alice.id, carol.id, _NOW - timedelta(hours=1), accepted=True)

        followers = followers_crud.get_all_followers_by_user_id(alice.id, db)
        following = followers_crud.get_all_following_by_user_id(alice.id, db)

        assert [row.follower_id for row in followers] == [bob.id, carol.id]
        assert [row.followee_id for row in following] == [carol.id, bob.id]

    def test_a_page_holds_its_slice_in_a_stable_order(self, db, alice):
        followers = [make_user(db) for _ in range(5)]
        for index, follower in enumerate(followers):
            make_follow_at(db, follower.id, alice.id, _NOW + timedelta(minutes=index), accepted=True)

        first = followers_crud.get_all_followers_by_user_id(alice.id, db, page_number=1, num_records=2)
        last = followers_crud.get_all_followers_by_user_id(alice.id, db, page_number=3, num_records=2)

        assert [row.follower_id for row in first] == [followers[0].id, followers[1].id]
        assert [row.follower_id for row in last] == [followers[4].id]


class TestCounting:
    def test_counts_cover_one_side_and_honour_accepted_only(self, db, alice, bob, carol):
        make_follow(db, bob.id, alice.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=False)
        make_follow(db, alice.id, bob.id, accepted=True)

        assert followers_crud.count_followers_by_user_id(alice.id, db) == 2
        assert followers_crud.count_followers_by_user_id(alice.id, db, accepted_only=True) == 1
        assert followers_crud.count_following_by_user_id(alice.id, db) == 1
        assert followers_crud.count_following_by_user_id(carol.id, db) == 1
        assert followers_crud.count_following_by_user_id(carol.id, db, accepted_only=True) == 0

    def test_a_user_with_no_relationships_counts_zero(self, db, alice):
        assert followers_crud.count_followers_by_user_id(alice.id, db) == 0
        assert followers_crud.count_following_by_user_id(alice.id, db) == 0
        assert followers_crud.count_pending_requests_for_user_id(alice.id, db) == 0


class TestPendingRequests:
    def test_only_pending_requests_addressed_to_the_user_are_listed_and_counted(self, db, alice, bob, carol):
        make_follow(db, bob.id, alice.id, accepted=False)
        make_follow(db, carol.id, alice.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=False)

        pending = followers_crud.get_pending_requests_for_user_id(alice.id, db)

        assert [(row.follower_id, row.status) for row in pending] == [(bob.id, _PENDING)]
        assert followers_crud.count_pending_requests_for_user_id(alice.id, db) == 1

    def test_pending_requests_page_in_creation_order(self, db, alice):
        requesters = [make_user(db) for _ in range(3)]
        for index, requester in enumerate(requesters):
            make_follow_at(db, requester.id, alice.id, _NOW + timedelta(minutes=index), accepted=False)

        page = followers_crud.get_pending_requests_for_user_id(alice.id, db, page_number=2, num_records=2)

        assert [row.follower_id for row in page] == [requesters[2].id]


class TestReadingOneRelationship:
    def test_the_relationship_is_found_in_the_direction_asked(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=True)

        found = followers_crud.get_follower_for_user_id_and_target_user_id(alice.id, bob.id, db)
        reverse = followers_crud.get_follower_for_user_id_and_target_user_id(bob.id, alice.id, db)

        assert found is not None
        assert (found.follower_id, found.followee_id, found.status) == (alice.id, bob.id, _ACCEPTED)
        assert reverse is None


class TestAcceptedFolloweeIds:
    def test_only_accepted_followees_are_listed(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=False)
        make_follow(db, carol.id, alice.id, accepted=True)

        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [bob.id]
        assert followers_crud.list_accepted_followee_ids(bob.id, db) == []

    def test_a_session_answers_again_from_its_first_read(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [bob.id]

        # A row written behind the module's back is not seen: the list is read once per session.
        db.add(followers_models.Follower(follower_id=alice.id, followee_id=carol.id, status="accepted"))
        db.flush()

        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [bob.id]

    def test_each_user_is_read_separately(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, bob.id, carol.id, accepted=True)

        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [bob.id]
        assert followers_crud.list_accepted_followee_ids(bob.id, db) == [carol.id]

    def test_a_write_through_the_module_makes_the_next_read_see_it(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=False)
        assert followers_crud.list_accepted_followee_ids(alice.id, db) == []

        followers_crud.accept_follower(bob.id, alice.id, db)
        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [bob.id]

        followers_crud.create_follower(alice.id, carol.id, db)
        followers_crud.accept_follower(carol.id, alice.id, db)
        assert set(followers_crud.list_accepted_followee_ids(alice.id, db)) == {bob.id, carol.id}

        followers_crud.delete_follower(alice.id, bob.id, db)
        assert followers_crud.list_accepted_followee_ids(alice.id, db) == [carol.id]

        followers_crud.delete_follows_between(alice.id, carol.id, db)
        assert followers_crud.list_accepted_followee_ids(alice.id, db) == []

    def test_a_new_session_does_not_see_another_sessions_memo(self, committed_sessions):
        with committed_sessions() as arrange:
            first, second = make_user(arrange), make_user(arrange)
            make_follow(arrange, first.id, second.id, accepted=True)
            arrange.commit()
        with committed_sessions() as reader:
            assert followers_crud.list_accepted_followee_ids(first.id, reader) == [second.id]
        with committed_sessions() as writer:
            followers_crud.delete_follower(first.id, second.id, writer)
            writer.commit()

        with committed_sessions() as later:
            assert followers_crud.list_accepted_followee_ids(first.id, later) == []


class TestCreatingAFollow:
    def test_a_new_follow_is_pending_and_stored(self, db, alice, bob):
        created = followers_crud.create_follower(alice.id, bob.id, db)

        assert (created.follower_id, created.followee_id, created.status) == (alice.id, bob.id, _PENDING)
        stored = db.scalars(select(followers_models.Follower)).all()
        assert [(row.follower_id, row.followee_id, row.status) for row in stored] == [(alice.id, bob.id, "pending")]

    def test_asking_twice_is_a_conflict(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=False)

        with pytest.raises(core_exceptions.ConflictError):
            followers_crud.create_follower(alice.id, bob.id, db)

        assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 1

    def test_the_opposite_directions_are_independent_relationships(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=False)
        make_follow(db, bob.id, alice.id, accepted=True)

        assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 2


class TestAcceptingAFollow:
    def test_a_pending_request_becomes_accepted(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)

        accepted = followers_crud.accept_follower(alice.id, bob.id, db)

        assert (accepted.follower_id, accepted.followee_id, accepted.status) == (bob.id, alice.id, _ACCEPTED)
        assert db.scalar(select(followers_models.Follower.status)) == "accepted"

    def test_a_request_the_other_way_round_is_not_accepted(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.accept_follower(bob.id, alice.id, db)

        assert db.scalar(select(followers_models.Follower.status)) == "pending"

    def test_the_second_accept_of_a_request_finds_nothing_to_accept(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)
        followers_crud.accept_follower(alice.id, bob.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.accept_follower(alice.id, bob.id, db)

    def test_there_is_nothing_to_accept_without_a_request(self, db, alice, bob):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.accept_follower(alice.id, bob.id, db)


class TestDeletingAFollow:
    def test_the_row_goes_and_its_status_is_returned(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, alice.id, carol.id, accepted=False)

        assert followers_crud.delete_follower(alice.id, bob.id, db) == _ACCEPTED
        assert followers_crud.delete_follower(alice.id, carol.id, db) == _PENDING

        assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 0

    def test_a_missing_relationship_is_not_found(self, db, alice, bob):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.delete_follower(alice.id, bob.id, db)

    def test_deleting_one_direction_keeps_the_other(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=True)

        followers_crud.delete_follower(alice.id, bob.id, db)

        remaining = db.scalars(select(followers_models.Follower)).all()
        assert [(row.follower_id, row.followee_id) for row in remaining] == [(bob.id, alice.id)]

    def test_a_status_scoped_delete_cannot_remove_an_accepted_follower(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=True)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.delete_follower(alice.id, bob.id, db, status=_PENDING)

        assert db.scalar(select(followers_models.Follower.status)) == "accepted"

    def test_a_status_scoped_delete_removes_a_pending_request(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=False)

        assert followers_crud.delete_follower(alice.id, bob.id, db, status=_PENDING) == _PENDING

        assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 0

    def test_deleting_the_follows_between_two_users_covers_both_directions_only(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=False)
        make_follow(db, carol.id, alice.id, accepted=True)

        removed = followers_crud.delete_follows_between(alice.id, bob.id, db)

        assert {(row.follower_id, row.status) for row in removed} == {(alice.id, _ACCEPTED), (bob.id, _PENDING)}
        remaining = db.scalars(select(followers_models.Follower)).all()
        assert [row.follower_id for row in remaining] == [carol.id]

    def test_unrelated_users_have_no_follows_to_delete(self, db, alice, bob):
        assert followers_crud.delete_follows_between(alice.id, bob.id, db) == []


class TestDeclines:
    def test_a_user_who_was_never_declined_has_no_decline_time(self, db, alice, bob):
        assert followers_crud.get_last_decline_at(alice.id, bob.id, db) is None

    def test_the_decline_time_is_stored_in_utc(self, db, alice, bob):
        make_decline(db, alice.id, bob.id, _NOW)

        declined_at = followers_crud.get_last_decline_at(alice.id, bob.id, db)

        assert declined_at == _NOW
        assert declined_at is not None and declined_at.utcoffset() == timedelta(0)

    def test_a_later_decline_of_the_same_pair_replaces_the_earlier_one(self, db, alice, bob):
        make_decline(db, alice.id, bob.id, _NOW)
        make_decline(db, alice.id, bob.id, _NOW + timedelta(days=2))

        assert followers_crud.get_last_decline_at(alice.id, bob.id, db) == _NOW + timedelta(days=2)
        assert db.scalar(select(func.count()).select_from(followers_models.FollowRequestDecline)) == 1

    def test_a_decline_belongs_to_one_direction_of_the_pair(self, db, alice, bob):
        make_decline(db, alice.id, bob.id, _NOW)

        assert followers_crud.get_last_decline_at(bob.id, alice.id, db) is None


class TestBlocks:
    def test_a_block_is_the_blockers_and_one_directional(self, db, alice, bob):
        assert not followers_crud.is_blocked(alice.id, bob.id, db)

        assert followers_crud.create_block(alice.id, bob.id, db) is True

        assert followers_crud.is_blocked(alice.id, bob.id, db)
        assert not followers_crud.is_blocked(bob.id, alice.id, db)

    def test_blocking_again_changes_nothing(self, db, alice, bob):
        make_block(db, alice.id, bob.id)

        assert followers_crud.create_block(alice.id, bob.id, db) is False

        assert db.scalar(select(func.count()).select_from(followers_models.FollowerBlock)) == 1

    def test_deleting_a_block_removes_it(self, db, alice, bob):
        make_block(db, alice.id, bob.id)

        followers_crud.delete_block(alice.id, bob.id, db)

        assert not followers_crud.is_blocked(alice.id, bob.id, db)

    def test_deleting_a_block_that_does_not_exist_is_not_found(self, db, alice, bob):
        make_block(db, bob.id, alice.id)

        with pytest.raises(core_exceptions.NotFoundError):
            followers_crud.delete_block(alice.id, bob.id, db)

        assert followers_crud.is_blocked(bob.id, alice.id, db)

    def test_blocked_ids_come_newest_block_first_and_only_the_blockers(self, db, alice, bob, carol):
        make_block(db, alice.id, bob.id, created_at=_NOW)
        make_block(db, alice.id, carol.id, created_at=_NOW + timedelta(hours=1))
        make_block(db, bob.id, alice.id, created_at=_NOW + timedelta(hours=2))

        assert followers_crud.list_blocked_user_ids(alice.id, db) == [carol.id, bob.id]
        assert followers_crud.list_blocked_user_ids(carol.id, db) == []


class TestTheDatabaseGuaranteesTheRules:
    def test_a_user_cannot_follow_themselves(self, db, alice):
        db.add(followers_models.Follower(follower_id=alice.id, followee_id=alice.id, status="pending"))

        with pytest.raises(IntegrityError, match="ck_followers_not_self"):
            db.flush()

    def test_a_follow_has_a_known_status(self, db, alice, bob):
        db.add(followers_models.Follower(follower_id=alice.id, followee_id=bob.id, status="blocked"))

        with pytest.raises(IntegrityError, match="ck_followers_status"):
            db.flush()

    def test_a_pair_has_one_follow_row(self, db, alice, bob):
        make_follow(db, alice.id, bob.id, accepted=False)
        db.add(followers_models.Follower(follower_id=alice.id, followee_id=bob.id, status="accepted"))

        with pytest.raises(IntegrityError, match="uq_followers_follower_followee"):
            db.flush()

    def test_a_user_cannot_block_themselves(self, db, alice):
        db.add(followers_models.FollowerBlock(blocker_id=alice.id, blocked_id=alice.id))

        with pytest.raises(IntegrityError, match="ck_follower_blocks_not_self"):
            db.flush()

    def test_a_pair_has_one_decline_row(self, db, alice, bob):
        make_decline(db, alice.id, bob.id, _NOW)
        db.add(followers_models.FollowRequestDecline(follower_id=alice.id, followee_id=bob.id, declined_at=_NOW))

        with pytest.raises(IntegrityError, match="uq_follow_request_declines_follower_followee"):
            db.flush()

    def test_deleting_a_user_removes_their_follows_blocks_and_declines(self, db, alice, bob, carol):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, carol.id, alice.id, accepted=False)
        make_block(db, bob.id, alice.id)
        make_decline(db, alice.id, carol.id, _NOW)
        make_follow(db, bob.id, carol.id, accepted=True)

        db.execute(delete(users_models.Users).where(users_models.Users.id == alice.id))

        assert db.scalar(text("SELECT count(*) FROM followers")) == 1
        assert db.scalar(text("SELECT count(*) FROM follower_blocks")) == 0
        assert db.scalar(text("SELECT count(*) FROM follow_request_declines")) == 0
