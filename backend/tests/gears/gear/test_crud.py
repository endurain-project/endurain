import uuid
from datetime import date

import pytest

import core.exceptions as core_exceptions
import core.timezone as core_timezone
import modules.gears.gear.crud as crud
import modules.gears.gear.schema as schema
from tests._factories.gears import gear_payload


def _page(db, user_id: uuid.UUID, **filters):
    return crud.get_gear_users_with_pagination(user_id, db, **filters)


class TestReads:
    def test_a_gear_is_visible_only_to_its_owner(self, db, user, other):
        created = crud.create_gear(gear_payload(), user.id, db)

        assert crud.get_gear_user_by_id(user.id, created.id, db) == created
        assert crud.get_gear_user_by_id(other.id, created.id, db) is None
        assert crud.get_gear_user(other.id, db) == []

    def test_nickname_lookup_ignores_case_and_surrounding_space(self, db, user):
        crud.create_gear(gear_payload("Road Bike"), user.id, db)

        assert crud.get_gear_user_by_nickname(user.id, "  road BIKE ", db).nickname == "Road Bike"
        assert crud.get_gear_user_by_nickname(user.id, "road", db) is None
        assert [g.nickname for g in _page(db, user.id, nickname_contains="ROAD")] == ["Road Bike"]

    @pytest.mark.parametrize(("term", "expected"), [("%", ["100% Bike"]), ("_", ["Gravel_1"]), ("bike", ["100% Bike"])])
    def test_like_wildcards_in_the_search_text_match_literally(self, term, expected, db, user):
        crud.create_gear(gear_payload("100% Bike"), user.id, db)
        crud.create_gear(gear_payload("Gravel_1"), user.id, db)

        assert [g.nickname for g in _page(db, user.id, nickname_contains=term)] == expected

    def test_gears_of_a_type_are_ordered_by_nickname(self, db, user):
        crud.create_gear(gear_payload("B bike"), user.id, db)
        crud.create_gear(gear_payload("A bike"), user.id, db)
        crud.create_gear(gear_payload("Shoes", gear_type=schema.GearType.SHOES), user.id, db)

        assert [g.nickname for g in _page(db, user.id, gear_type=schema.GearType.BIKE)] == ["A bike", "B bike"]
        assert crud.get_gears_number(user.id, db, gear_type=schema.GearType.BIKE) == 2

    def test_filters_narrow_the_total_and_the_page_together(self, db, user):
        for name in ("Bike A", "Bike B", "Bike C"):
            crud.create_gear(gear_payload(name), user.id, db)

        assert crud.get_gears_number(user.id, db, nickname_contains="bike") == 3
        assert len(_page(db, user.id, nickname_contains="bike", num_records=2)) == 2

    def test_provider_ids_resolve_within_the_owner(self, db, user, other):
        crud.create_gear(gear_payload(strava_gear_id="b1", garminconnect_gear_id="g1"), user.id, db)

        assert crud.get_gear_by_strava_id_from_user_id("b1", user.id, db).nickname == "Road Bike"
        assert crud.get_gear_by_strava_id_from_user_id("b1", other.id, db) is None
        assert crud.get_gear_by_garminconnect_id_from_user_id("g1", user.id, db).nickname == "Road Bike"
        assert crud.get_gear_by_garminconnect_id_from_user_id("missing", user.id, db) is None

    def test_pagination_and_the_active_filter_apply_to_page_and_count(self, db, user):
        for name, active in (("A", True), ("B", False), ("C", True)):
            crud.create_gear(gear_payload(name, active=active), user.id, db)

        assert crud.get_gears_number(user.id, db) == 3
        assert crud.get_gears_number(user.id, db, active=True) == 2
        assert crud.get_gears_number(user.id, db, active=False) == 1
        page = crud.get_gear_users_with_pagination(user.id, db, page_number=2, num_records=2)
        assert [g.nickname for g in page] == ["C"]
        active_only = crud.get_gear_users_with_pagination(user.id, db, active=True)
        assert [g.nickname for g in active_only] == ["A", "C"]
        inactive_only = crud.get_gear_users_with_pagination(user.id, db, active=False)
        assert [g.nickname for g in inactive_only] == ["B"]


class TestWrites:
    def test_create_trims_text_and_sets_the_owner(self, db, other):
        created = crud.create_gear(gear_payload("  Road Bike  ", brand=" Trek "), other.id, db)

        assert (created.nickname, created.brand, created.user_id) == ("Road Bike", "Trek", other.id)

    def test_the_acquisition_date_is_stored_as_sent(self, db, user):
        created = crud.create_gear(gear_payload(acquired_on=date(2023, 6, 1)), user.id, db)

        assert created.acquired_on == date(2023, 6, 1)
        assert crud.get_gear_user_by_id(user.id, created.id, db).acquired_on == date(2023, 6, 1)

    def test_a_gear_created_without_an_acquisition_date_gets_today(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        assert created.acquired_on == core_timezone.today_in(core_timezone.or_default(None))

    def test_an_update_changes_the_acquisition_date(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        updated = crud.edit_gear(created.id, schema.GearUpdate(acquired_on=date(2020, 1, 2)), user.id, db, if_match="*")

        assert updated.acquired_on == date(2020, 1, 2)

    def test_the_owner_comes_from_the_caller_not_the_payload(self, db, other):
        created = crud.create_gear(gear_payload(user_id=uuid.uuid4()), other.id, db)

        assert created.user_id == other.id

    def test_a_nickname_is_unique_per_user_regardless_of_case(self, db, user, other):
        crud.create_gear(gear_payload("Road Bike"), user.id, db)
        crud.create_gear(gear_payload("Road Bike"), other.id, db)

        with pytest.raises(core_exceptions.ConflictError, match="nickname"):
            crud.create_gear(gear_payload(" ROAD bike "), user.id, db)

    def test_a_taken_provider_id_is_a_conflict(self, db, user):
        crud.create_gear(gear_payload("One", strava_gear_id="b1"), user.id, db)

        with pytest.raises(core_exceptions.ConflictError, match="Strava or Garmin Connect ID"):
            crud.create_gear(gear_payload("Two", strava_gear_id="b1"), user.id, db)

    def test_the_same_provider_id_is_allowed_for_another_user(self, db, user, other):
        crud.create_gear(gear_payload("One", strava_gear_id="b1"), user.id, db)

        assert crud.create_gear(gear_payload("One", strava_gear_id="b1"), other.id, db).strava_gear_id == "b1"

    def test_create_gears_stages_every_gear(self, db, user):
        crud.create_gears([gear_payload("A"), gear_payload("B")], user.id, db)

        assert crud.get_gears_number(user.id, db) == 2

    def test_writes_stage_without_committing(self, db, user):
        crud.create_gear(gear_payload(), user.id, db)
        db.rollback()

        assert crud.get_gear_user(user.id, db) == []

    def test_edit_changes_sent_fields_and_never_the_owner(self, db, user):
        created = crud.create_gear(gear_payload(brand="Trek"), user.id, db)

        updated = crud.edit_gear(created.id, schema.GearUpdate(nickname=" Gravel "), user.id, db, if_match="*")

        assert (updated.nickname, updated.brand, updated.user_id) == ("Gravel", "Trek", user.id)

    def test_edit_clears_a_nullable_field_sent_as_null(self, db, user):
        created = crud.create_gear(gear_payload(brand="Trek", purchase_value="10.00"), user.id, db)

        updated = crud.edit_gear(
            created.id, schema.GearUpdate(brand=None, purchase_value=None), user.id, db, if_match="*"
        )

        assert (updated.brand, updated.purchase_value) == (None, None)

    def test_edit_bumps_the_version_and_honours_if_match(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        updated = crud.edit_gear(
            created.id, schema.GearUpdate(brand="Trek"), user.id, db, if_match=f'"{created.version}"'
        )

        assert updated.version == created.version + 1
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_gear(created.id, schema.GearUpdate(brand="Giant"), user.id, db, if_match=f'"{created.version}"')

    def test_edit_onto_a_taken_nickname_is_a_conflict(self, db, user):
        crud.create_gear(gear_payload("Taken"), user.id, db)
        mine = crud.create_gear(gear_payload("Mine"), user.id, db)

        with pytest.raises(core_exceptions.ConflictError, match="nickname"):
            crud.edit_gear(mine.id, schema.GearUpdate(nickname="taken"), user.id, db, if_match="*")

    def test_update_and_create_requests_reject_provider_ids_and_blank_nicknames(self):
        with pytest.raises(ValueError):
            schema.GearUpdate(nickname="x", strava_gear_id="b1")
        with pytest.raises(ValueError):
            schema.GearCreateRequest(gear_type=1, nickname="x", garminconnect_gear_id="g1")
        with pytest.raises(ValueError):
            schema.GearCreateRequest(gear_type=1, nickname="   ")
        with pytest.raises(ValueError):
            schema.GearUpdate(nickname=None)

    def test_edit_of_a_foreign_gear_is_not_found(self, db, user, other):
        created = crud.create_gear(gear_payload(), user.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear(created.id, schema.GearUpdate(nickname="x"), other.id, db, if_match="*")

    def test_delete_removes_the_gear(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        crud.delete_gear(created.id, user.id, db, if_match=f'"{created.version}"')

        assert crud.get_gear_user_by_id(user.id, created.id, db) is None

    def test_delete_of_a_stale_version_is_refused_and_keeps_the_gear(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.delete_gear(created.id, user.id, db, if_match=f'"{created.version + 1}"')

        assert crud.get_gear_user_by_id(user.id, created.id, db) is not None

    def test_delete_with_the_wildcard_removes_the_gear(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        crud.delete_gear(created.id, user.id, db, if_match="*")

        assert crud.get_gear_user_by_id(user.id, created.id, db) is None

    def test_delete_of_a_foreign_gear_is_not_found(self, db, user, other):
        created = crud.create_gear(gear_payload(), user.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear(created.id, other.id, db, if_match="*")

    def test_strava_gear_is_deleted_per_owner(self, db, user, other):
        crud.create_gear(gear_payload("S", strava_gear_id="b1"), user.id, db)
        crud.create_gear(gear_payload("G", garminconnect_gear_id="g1"), user.id, db)
        crud.create_gear(gear_payload("S2", strava_gear_id="b2"), other.id, db)

        crud.delete_all_strava_gear_for_user(user.id, db)

        assert [g.nickname for g in crud.get_gear_user(user.id, db)] == ["G"]
        assert len(crud.get_gear_user(other.id, db)) == 1
