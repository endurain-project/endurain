"""The combined activity detail is the activity plus its child collections, gated once."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_detail.service as detail_service

_ACTIVITY = "modules.activities.activity_detail.service.activity_integration"
_USERS = "modules.activities.activity_detail.service.users_integration"
_LAPS = "modules.activities.activity_detail.service.activity_laps_integration"
_SETS = "modules.activities.activity_detail.service.activity_sets_integration"
_STEPS = "modules.activities.activity_detail.service.activity_workout_steps_integration"


@pytest.fixture
def children():
    with patch(_LAPS) as laps, patch(_SETS) as sets, patch(_STEPS) as steps:
        laps.list_for_activity.return_value = "laps-page"
        sets.list_for_activity.return_value = "sets-page"
        steps.list_for_activity.return_value = "steps-page"
        yield laps, sets, steps


@pytest.fixture
def users():
    with patch(_USERS) as users_integration:
        users_integration.list_public_profiles.return_value = {3: "owner-profile"}
        users_integration.get_public_user.return_value = "public-owner"
        yield users_integration


def _detail():
    """Replace the response model, so stand-in pages need not validate."""
    return patch.object(detail_service.activity_detail_schema, "ActivityDetailRead")


class TestGetActivityDetail:
    def test_reads_the_activity_once_and_each_child_for_it(self, children, users):
        laps, sets, steps = children
        activity, db = SimpleNamespace(id=5, user_id=3), MagicMock()
        with patch(_ACTIVITY) as activity_integration, _detail() as build:
            activity_integration.get_readable_activity.return_value = activity
            activity_integration.with_media.return_value = activity
            detail_service.get_activity_detail(5, 1, db)

        activity_integration.get_readable_activity.assert_called_once_with(5, 1, db)
        activity_integration.with_media.assert_called_once_with(activity, 1, db)
        users.list_public_profiles.assert_called_once_with({3}, db)
        laps.list_for_activity.assert_called_once_with(activity, 1, db)
        sets.list_for_activity.assert_called_once_with(activity, 1, db)
        steps.list_for_activity.assert_called_once_with(activity, 1, db)
        build.assert_called_once_with(
            activity=activity,
            owner="owner-profile",
            laps="laps-page",
            sets="sets-page",
            workout_steps="steps-page",
        )

    def test_an_owner_who_is_not_visible_is_null(self, children, users):
        users.list_public_profiles.return_value = {}
        activity = SimpleNamespace(id=5, user_id=3)
        with patch(_ACTIVITY) as activity_integration, _detail() as build:
            activity_integration.get_readable_activity.return_value = activity
            activity_integration.with_media.return_value = activity
            detail_service.get_activity_detail(5, 1, MagicMock())

        assert build.call_args.kwargs["owner"] is None

    def test_an_activity_the_caller_cannot_see_is_not_found_and_no_child_is_read(self, children, users):
        with patch(_ACTIVITY) as activity_integration:
            activity_integration.get_readable_activity.side_effect = core_exceptions.NotFoundError("nope")
            with pytest.raises(core_exceptions.NotFoundError):
                detail_service.get_activity_detail(5, 1, MagicMock())

        for child in children:
            child.list_for_activity.assert_not_called()


class TestGetPublicActivityDetail:
    def test_reads_the_public_activity_and_each_child_as_anonymous(self, children, users):
        laps, sets, steps = children
        activity, db = SimpleNamespace(id=5, user_id=3), MagicMock()
        with patch(_ACTIVITY) as activity_integration, _detail() as build:
            activity_integration.get_public_activity.return_value = activity
            detail_service.get_public_activity_detail(5, db)

        activity_integration.with_media.assert_not_called()
        users.get_public_user.assert_called_once_with(3, db)
        assert build.call_args.kwargs["owner"] == "public-owner"

        activity_integration.get_public_activity.assert_called_once_with(5, db)
        laps.list_for_activity.assert_called_once_with(activity, None, db)
        sets.list_for_activity.assert_called_once_with(activity, None, db)
        steps.list_for_activity.assert_called_once_with(activity, None, db)

    def test_an_owner_the_server_does_not_share_is_null_not_a_refusal(self, children, users):
        users.get_public_user.side_effect = core_exceptions.NotFoundError("hidden")
        with patch(_ACTIVITY) as activity_integration, _detail() as build:
            activity_integration.get_public_activity.return_value = SimpleNamespace(id=5, user_id=3)
            detail_service.get_public_activity_detail(5, MagicMock())

        assert build.call_args.kwargs["owner"] is None

    def test_an_activity_that_is_not_public_is_not_found(self, children, users):
        with patch(_ACTIVITY) as activity_integration:
            activity_integration.get_public_activity.side_effect = core_exceptions.NotFoundError("nope")
            with pytest.raises(core_exceptions.NotFoundError):
                detail_service.get_public_activity_detail(5, MagicMock())


class TestPublicOwnerVisibility:
    """The owner of a shared activity is shown on the same terms the removed owner route used."""

    _USER_SETTINGS = "modules.users.users.service.server_settings_integration.get_server_settings"
    _USER_CRUD = "modules.users.users.service.users_crud.get_user_by_id"

    def _owner(self, **kw):
        from modules.users.users.schema import UserRead

        data = dict(
            id=3, name="Owner", username="owner", email="o@example.com", active=True, pending_admin_approval=False
        )
        data.update(kw)
        return UserRead.model_construct(**data)

    def _read(self, children, *, user_info=True, owner="ok"):
        owner = self._owner() if owner == "ok" else owner
        settings = MagicMock(public_shareable_links=True, public_shareable_links_user_info=user_info)
        with (
            patch(_ACTIVITY) as activity_integration,
            _detail() as build,
            patch(self._USER_SETTINGS, return_value=settings),
            patch(self._USER_CRUD, return_value=owner),
        ):
            activity_integration.get_public_activity.return_value = SimpleNamespace(id=5, user_id=3)
            detail_service.get_public_activity_detail(5, MagicMock())
        return build.call_args.kwargs["owner"]

    def test_the_owner_is_the_public_projection_when_user_info_is_shared(self, children):
        owner = self._read(children)

        assert set(owner.model_dump()) == {"id", "name", "username", "city", "photo_path"}
        assert owner.id == 3

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"user_info": False},
            {"owner": None},
            {"owner": "inactive"},
            {"owner": "pending"},
        ],
    )
    def test_every_case_that_hid_the_owner_is_now_a_null_owner(self, children, kwargs):
        if kwargs.get("owner") == "inactive":
            kwargs = {"owner": self._owner(active=False)}
        if kwargs.get("owner") == "pending":
            kwargs = {"owner": self._owner(pending_admin_approval=True)}

        assert self._read(children, **kwargs) is None
