"""Another user's activities are never readable while their owner is inactive or awaiting approval.

The users module decides who is visible; these tests let its real rule run over stubbed user rows so
a follower, an anonymous public-link viewer and the owner are each checked for both hidden states.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.child_access_service as child_access_service
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service

_OWNER = uuid.UUID(int=1)
_FOLLOWER = uuid.UUID(int=2)
_ACTIVITY_ID = uuid.uuid4()

_HIDDEN_STATES = pytest.mark.parametrize(
    "state",
    [{"active": False, "pending_admin_approval": False}, {"active": True, "pending_admin_approval": True}],
    ids=["inactive", "awaiting-approval"],
)


def _owner_row(**state):
    return SimpleNamespace(id=_OWNER, name="Owner", username="owner", city=None, photo_path=None, **state)


@pytest.fixture
def owner_state():
    """Stub the stored owner row, so the real users-module visibility rule decides."""
    with patch("modules.users.users.service.users_crud.get_users_by_ids") as get_users:

        def _set(**state):
            get_users.side_effect = lambda ids, db: [_owner_row(**state)] if _OWNER in ids else []
            return get_users

        yield _set


@pytest.fixture(autouse=True)
def stubs():
    activity = activity_schema.ActivityRead(id=_ACTIVITY_ID, user_id=_OWNER, distance=0, name="Run", activity_type=1)
    with (
        patch("modules.activities.activity.child_access_service.followers_integration") as followers,
        patch("modules.activities.activity.child_access_service.server_settings_integration") as settings,
        patch("modules.activities.activity.service.server_settings_integration") as service_settings,
        patch("modules.activities.activity.child_access_service.activity_crud") as child_crud,
        patch("modules.activities.activity.service.activity_crud") as crud,
        patch.object(activity_service, "_with_thumbnail_urls", side_effect=lambda items: items),
    ):
        followers.list_accepted_followee_ids.return_value = [_OWNER]
        settings.public_shareable_links_enabled.return_value = True
        service_settings.public_shareable_links_enabled.return_value = True
        for target in (child_crud, crud):
            target.get_viewable_activity_by_id_for_user.return_value = activity
            target.get_activity_by_id_from_user_id_or_has_visibility.return_value = activity
            target.get_activity_by_id_if_is_public.return_value = activity
        yield SimpleNamespace(activity=activity, crud=crud, followers=followers)


class TestSingleActivityRead:
    @_HIDDEN_STATES
    def test_a_follower_gets_not_found(self, owner_state, state):
        owner_state(**state)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_activity(_ACTIVITY_ID, _FOLLOWER, MagicMock())

    @_HIDDEN_STATES
    def test_an_anonymous_public_link_viewer_gets_not_found(self, owner_state, state):
        owner_state(**state)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_public_activity(_ACTIVITY_ID, MagicMock())

    @_HIDDEN_STATES
    def test_the_owner_still_reads_their_own_activity(self, owner_state, state, stubs):
        owner_state(**state)

        assert activity_service.get_activity(_ACTIVITY_ID, _OWNER, MagicMock()) is stubs.activity

    def test_a_follower_reads_the_activity_of_an_active_owner(self, owner_state, stubs):
        owner_state(active=True, pending_admin_approval=False)

        assert activity_service.get_activity(_ACTIVITY_ID, _FOLLOWER, MagicMock()) is stubs.activity
        assert activity_service.get_public_activity(_ACTIVITY_ID, MagicMock()) is stubs.activity


class TestChildReads:
    @_HIDDEN_STATES
    def test_a_follower_has_no_readable_parent(self, owner_state, state):
        owner_state(**state)

        assert child_access_service.resolve_readable_parent(_ACTIVITY_ID, _FOLLOWER, MagicMock()) is None

    @_HIDDEN_STATES
    def test_an_anonymous_viewer_has_no_public_parent(self, owner_state, state):
        owner_state(**state)

        assert child_access_service.resolve_public_parent(_ACTIVITY_ID, MagicMock()) is None

    @_HIDDEN_STATES
    def test_the_owner_still_has_a_readable_parent(self, owner_state, state, stubs):
        owner_state(**state)

        assert child_access_service.resolve_readable_parent(_ACTIVITY_ID, _OWNER, MagicMock()) is stubs.activity

    def test_a_follower_has_the_parent_of_an_active_owner(self, owner_state, stubs):
        owner_state(active=True, pending_admin_approval=False)

        assert child_access_service.resolve_readable_parent(_ACTIVITY_ID, _FOLLOWER, MagicMock()) is stubs.activity
        assert child_access_service.resolve_public_parent(_ACTIVITY_ID, MagicMock()) is stubs.activity


class TestFollowingFeed:
    @_HIDDEN_STATES
    def test_the_feed_does_not_query_a_hidden_owner(self, owner_state, state, stubs):
        owner_state(**state)
        stubs.crud.get_following_feed_after.return_value = []

        activity_service.scroll_feed(_FOLLOWER, None, 25, MagicMock())

        assert stubs.crud.get_following_feed_after.call_args.args[0] == []

    def test_the_feed_queries_an_active_owner(self, owner_state, stubs):
        owner_state(active=True, pending_admin_approval=False)
        stubs.crud.get_following_feed_after.return_value = []

        activity_service.scroll_feed(_FOLLOWER, None, 25, MagicMock())

        assert stubs.crud.get_following_feed_after.call_args.args[0] == [_OWNER]
