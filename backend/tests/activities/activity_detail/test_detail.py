"""An activity with its laps, sets and steps: what an owner, a follower and an anonymous viewer each receive."""

import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_detail.service as detail_service
from tests._factories.activities import make_activity, make_activity_children, make_activity_media, make_multisport
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_URL = f"{core_config.ROOT_PATH}/activities"
_PUBLIC_URL = f"{core_config.ROOT_PATH}/public/activities"


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def viewer(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def activity(db, owner):
    created = make_activity(db, owner.id, visibility=_Visibility.PUBLIC)
    make_activity_children(db, created)
    return created


class TestForASignedInViewer:
    def test_the_owner_gets_the_activity_with_its_media_the_first_page_of_each_collection_and_themselves(
        self, db, owner, activity
    ):
        make_activity_media(db, activity, "photo.jpg")

        detail = detail_service.get_activity_detail(activity.id, owner.id, db)

        assert detail.activity.id == activity.id
        assert len(detail.activity.media) == 1
        assert (detail.laps.total, detail.sets.total, detail.workout_steps.total) == (1, 1, 1)
        assert detail.owner is not None and detail.owner.id == owner.id

    def test_a_viewer_gets_a_public_activity_masked_without_media_and_with_the_owners_profile(
        self, db, owner, viewer, activity
    ):
        make_activity_media(db, activity, "photo.jpg")

        detail = detail_service.get_activity_detail(activity.id, viewer.id, db)

        assert detail.activity.private_notes is None
        assert detail.activity.media == []
        assert detail.owner.id == owner.id
        assert detail.laps.total == 1

    @pytest.mark.parametrize(("flag", "collection"), [("hide_laps", "laps"), ("hide_workout_sets_steps", "sets")])
    def test_a_collection_the_owner_hides_is_an_empty_page_for_a_viewer_and_whole_for_the_owner(
        self, db, owner, viewer, flag, collection
    ):
        hidden = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, **{flag: True})
        make_activity_children(db, hidden)

        seen = detail_service.get_activity_detail(hidden.id, viewer.id, db)
        own = detail_service.get_activity_detail(hidden.id, owner.id, db)

        assert getattr(seen, collection).total == 0
        assert getattr(own, collection).total == 1

    @pytest.mark.parametrize("visibility", [_Visibility.PRIVATE, _Visibility.FOLLOWERS])
    def test_an_activity_the_viewer_may_not_see_is_not_found(self, db, owner, viewer, visibility):
        hidden = make_activity(db, owner.id, visibility=visibility)

        with pytest.raises(core_exceptions.NotFoundError):
            detail_service.get_activity_detail(hidden.id, viewer.id, db)

    def test_a_follower_gets_the_followers_activity(self, db, owner, viewer):
        followers = make_activity(db, owner.id, visibility=_Visibility.FOLLOWERS)
        make_follow(db, viewer.id, owner.id, accepted=True)

        assert detail_service.get_activity_detail(followers.id, viewer.id, db).activity.id == followers.id

    def test_the_owner_is_null_once_they_are_inactive(self, db, viewer):
        gone = make_user(db, active=False)
        mine = make_activity(db, gone.id)

        assert detail_service.get_activity_detail(mine.id, gone.id, db).owner is None


class TestLegs:
    def test_a_multisport_activity_carries_its_legs_in_start_order(self, db, owner, viewer):
        parent, legs = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC)

        for requester in (owner.id, viewer.id):
            detail = detail_service.get_activity_detail(parent.id, requester, db)

            assert [leg.id for leg in detail.legs.items] == [leg.id for leg in legs]
            assert detail.legs.total == len(legs)

    def test_a_viewer_gets_the_legs_masked_as_a_list_row_is(self, db, owner, viewer):
        parent, _ = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC, hide_hr=True, average_hr=150)

        seen = detail_service.get_activity_detail(parent.id, viewer.id, db)
        own = detail_service.get_activity_detail(parent.id, owner.id, db)

        assert {leg.average_hr for leg in seen.legs.items} == {None}
        assert {leg.average_hr for leg in own.legs.items} == {150}

    def test_an_activity_that_is_not_a_multisport_parent_has_an_empty_page(self, db, owner, activity):
        detail = detail_service.get_activity_detail(activity.id, owner.id, db)

        assert (detail.legs.items, detail.legs.total) == ([], 0)

    def test_the_public_detail_carries_the_legs_masked(self, db, owner):
        edit_server_settings(db, public_shareable_links=True)
        parent, legs = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC, hide_hr=True, average_hr=150)

        detail = detail_service.get_public_activity_detail(parent.id, db)

        assert [leg.id for leg in detail.legs.items] == [leg.id for leg in legs]
        assert {leg.average_hr for leg in detail.legs.items} == {None}

    def test_the_public_detail_of_an_activity_without_legs_has_an_empty_page(self, db, activity):
        edit_server_settings(db, public_shareable_links=True)

        assert detail_service.get_public_activity_detail(activity.id, db).legs.total == 0

    def test_the_detail_routes_carry_the_legs(self, arrange, sign_in, client, owner):
        parent, legs = arrange(lambda db: make_multisport(db, owner.id, visibility=_Visibility.PUBLIC))
        arrange(lambda db: edit_server_settings(db, public_shareable_links=True))

        signed = sign_in(owner).client.get(f"{_URL}/{parent.id}/detail").json()
        public = client.get(f"{_PUBLIC_URL}/{parent.id}/detail").json()

        expected = [str(leg.id) for leg in legs]
        assert [item["id"] for item in signed["legs"]["items"]] == expected
        assert [item["id"] for item in public["legs"]["items"]] == expected


class TestForAnAnonymousViewer:
    def test_a_public_activity_is_served_masked_with_its_collections_only_while_links_are_shared(self, db, activity):
        with pytest.raises(core_exceptions.NotFoundError):
            detail_service.get_public_activity_detail(activity.id, db)
        edit_server_settings(db, public_shareable_links=True)

        detail = detail_service.get_public_activity_detail(activity.id, db)

        assert (detail.activity.private_notes, detail.activity.media) == (None, [])
        assert detail.laps.total == 1

    def test_the_owner_is_shown_only_when_the_server_shares_user_info(self, db, owner, activity):
        edit_server_settings(db, public_shareable_links=True, public_shareable_links_user_info=False)
        assert detail_service.get_public_activity_detail(activity.id, db).owner is None

        edit_server_settings(db, public_shareable_links=True, public_shareable_links_user_info=True)
        shared = detail_service.get_public_activity_detail(activity.id, db).owner

        assert set(shared.model_dump()) == {"id", "name", "username", "city", "photo_path"}
        assert shared.id == owner.id

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    def test_an_owner_who_is_inactive_or_awaiting_approval_is_not_found(self, db, state):
        edit_server_settings(db, public_shareable_links=True, public_shareable_links_user_info=True)
        gone = make_user(db, **state)
        mine = make_activity(db, gone.id, visibility=_Visibility.PUBLIC)

        with pytest.raises(core_exceptions.NotFoundError):
            detail_service.get_public_activity_detail(mine.id, db)

    @pytest.mark.parametrize(
        "fields", [{"visibility": _Visibility.FOLLOWERS}, {"visibility": _Visibility.PRIVATE}, {"is_hidden": True}]
    )
    def test_an_activity_that_is_not_public_is_not_found(self, db, owner, fields):
        edit_server_settings(db, public_shareable_links=True)
        mine = make_activity(db, owner.id, **{"visibility": _Visibility.PUBLIC, **fields})

        with pytest.raises(core_exceptions.NotFoundError):
            detail_service.get_public_activity_detail(mine.id, db)

    def test_a_hidden_collection_is_an_empty_page(self, db, owner):
        edit_server_settings(db, public_shareable_links=True)
        mine = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, hide_laps=True)
        make_activity_children(db, mine)

        assert detail_service.get_public_activity_detail(mine.id, db).laps.total == 0


class TestRoutes:
    @pytest.fixture
    def me(self, sign_in, arrange):
        return sign_in(arrange(lambda db: make_user(db, timezone="UTC")))

    @pytest.fixture
    def stored(self, arrange):
        author = arrange(lambda db: make_user(db, timezone="UTC"))

        def make(**fields):
            def stage(db):
                created = make_activity(db, author.id, **fields)
                make_activity_children(db, created)
                return created

            return arrange(stage)

        make.author = author
        return make

    def test_the_signed_in_detail_carries_the_activitys_etag_for_a_later_save(self, sign_in, stored):
        mine = stored(visibility=_Visibility.PRIVATE)

        response = sign_in(stored.author).client.get(f"{_URL}/{mine.id}/detail")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert body["activity"]["id"] == str(mine.id)
        assert (body["laps"]["total"], body["sets"]["total"], body["workout_steps"]["total"]) == (1, 1, 1)
        assert body["owner"]["id"] == str(stored.author.id)

    def test_an_activity_the_caller_may_not_see_and_a_malformed_id_are_refused(self, me, stored):
        private = stored(visibility=_Visibility.PRIVATE)

        assert me.client.get(f"{_URL}/{private.id}/detail").status_code == 404
        assert me.client.get(f"{_URL}/not-a-uuid/detail").status_code == 422

    def test_the_public_detail_needs_no_credentials_but_the_server_must_share_links(self, client, stored, arrange):
        public = stored(visibility=_Visibility.PUBLIC)
        refused = client.get(f"{_PUBLIC_URL}/{public.id}/detail").status_code
        arrange(lambda db: edit_server_settings(db, public_shareable_links=True))

        response = client.get(f"{_PUBLIC_URL}/{public.id}/detail")

        assert refused == 404
        assert response.status_code == 200
        assert response.json()["activity"]["id"] == str(public.id)

    def test_the_public_detail_of_a_private_activity_looks_like_one_that_does_not_exist(self, client, stored, arrange):
        arrange(lambda db: edit_server_settings(db, public_shareable_links=True))
        private = stored(visibility=_Visibility.PRIVATE)

        hidden = client.get(f"{_PUBLIC_URL}/{private.id}/detail")
        missing = client.get(f"{_PUBLIC_URL}/6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01/detail")

        assert (hidden.status_code, missing.status_code) == (404, 404)
        assert hidden.json()["detail"] == missing.json()["detail"]

    def test_a_malformed_public_id_is_422(self, client):
        assert client.get(f"{_PUBLIC_URL}/not-a-uuid/detail").status_code == 422
