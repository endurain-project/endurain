"""What other modules read from the followers module."""

import modules.followers.integration_service as followers_integration
from tests._factories.followers import make_follow


def test_the_accepted_followees_of_a_user_are_what_other_modules_read(db, alice, bob, carol):
    make_follow(db, alice.id, bob.id, accepted=True)
    make_follow(db, alice.id, carol.id, accepted=False)

    assert followers_integration.list_accepted_followee_ids(alice.id, db) == [bob.id]
    assert followers_integration.list_accepted_followee_ids(bob.id, db) == []


def test_profile_follow_counts_are_the_accepted_ones_when_the_viewer_may_see_them(db, alice, bob, carol):
    make_follow(db, bob.id, alice.id, accepted=True)
    make_follow(db, carol.id, alice.id, accepted=False)
    make_follow(db, alice.id, carol.id, accepted=True)

    counts = followers_integration.get_profile_follow_counts(alice.id, alice.id, db)

    assert counts is not None
    assert (counts.followers, counts.following) == (1, 1)


def test_profile_follow_counts_are_absent_for_a_viewer_who_may_not_see_the_network(db, alice, bob):
    assert followers_integration.get_profile_follow_counts(alice.id, bob.id, db) is None
