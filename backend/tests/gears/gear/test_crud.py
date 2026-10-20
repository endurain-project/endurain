import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.gears.gear.crud as crud
import modules.gears.gear.schema as schema
from tests._helpers.gears import gear_create


class TestReads:
    def test_a_gear_is_visible_only_to_its_owner(self, db):
        created = crud.create_gear(gear_create(), 1, db)

        assert crud.get_gear_user_by_id(1, created.id, db) == created
        assert crud.get_gear_user_by_id(2, created.id, db) is None
        assert crud.get_gear_user(2, db) == []

    def test_nickname_lookup_ignores_case_and_surrounding_space(self, db):
        crud.create_gear(gear_create("Road Bike"), 1, db)

        assert crud.get_gear_user_by_nickname(1, "  road BIKE ", db).nickname == "Road Bike"
        assert crud.get_gear_user_by_nickname(1, "road", db) is None
        assert [g.nickname for g in crud.get_gear_user_contains_nickname(1, "ROAD", db)] == ["Road Bike"]

    @pytest.mark.parametrize(("term", "expected"), [("%", ["100% Bike"]), ("_", ["Gravel_1"]), ("bike", ["100% Bike"])])
    def test_like_wildcards_in_the_search_text_match_literally(self, term, expected, db):
        crud.create_gear(gear_create("100% Bike"), 1, db)
        crud.create_gear(gear_create("Gravel_1"), 1, db)

        assert [g.nickname for g in crud.get_gear_user_contains_nickname(1, term, db)] == expected

    def test_gears_of_a_type_are_ordered_by_nickname(self, db):
        crud.create_gear(gear_create("B bike"), 1, db)
        crud.create_gear(gear_create("A bike"), 1, db)
        crud.create_gear(gear_create("Shoes", gear_type=schema.GearType.SHOES), 1, db)

        assert [g.nickname for g in crud.get_gear_by_type_and_user(schema.GearType.BIKE, 1, db)] == [
            "A bike",
            "B bike",
        ]

    def test_search_and_type_lists_are_bounded(self, db, monkeypatch):
        for name in ("Bike A", "Bike B", "Bike C"):
            crud.create_gear(gear_create(name), 1, db)
        monkeypatch.setattr(core_pagination, "MAX_NUM_RECORDS", 2)

        assert len(crud.get_gear_user_contains_nickname(1, "bike", db)) == 2
        assert len(crud.get_gear_by_type_and_user(schema.GearType.BIKE, 1, db)) == 2

    def test_provider_ids_resolve_within_the_owner(self, db):
        crud.create_gear(gear_create(strava_gear_id="b1", garminconnect_gear_id="g1"), 1, db)

        assert crud.get_gear_by_strava_id_from_user_id("b1", 1, db).nickname == "Road Bike"
        assert crud.get_gear_by_strava_id_from_user_id("b1", 2, db) is None
        assert crud.get_gear_by_garminconnect_id_from_user_id("g1", 1, db).nickname == "Road Bike"
        assert crud.get_gear_by_garminconnect_id_from_user_id("missing", 1, db) is None

    def test_pagination_and_the_inactive_filter_apply_to_page_and_count(self, db):
        for name, active in (("A", True), ("B", False), ("C", True)):
            crud.create_gear(gear_create(name, active=active), 1, db)

        assert crud.get_gears_number(1, db) == 3
        assert crud.get_gears_number(1, db, show_inactive=False) == 2
        page = crud.get_gear_users_with_pagination(1, db, page_number=2, num_records=2)
        assert [g.nickname for g in page] == ["C"]
        active_only = crud.get_gear_users_with_pagination(1, db, show_inactive=False)
        assert [g.nickname for g in active_only] == ["A", "C"]

    def test_existing_nicknames_are_reported_normalized(self, db):
        crud.create_gear(gear_create("Road Bike"), 1, db)
        crud.create_gear(gear_create("Other"), 2, db)

        assert crud.get_existing_nicknames(1, {"road bike", "other"}, db) == {"road bike"}


class TestWrites:
    def test_create_trims_text_and_sets_the_owner(self, db):
        created = crud.create_gear(gear_create("  Road Bike  ", brand=" Trek "), 7, db)

        assert (created.nickname, created.brand, created.user_id) == ("Road Bike", "Trek", 7)

    def test_the_owner_comes_from_the_caller_not_the_payload(self, db):
        created = crud.create_gear(gear_create(user_id=99), 7, db)

        assert created.user_id == 7

    def test_a_nickname_is_unique_per_user_regardless_of_case(self, db):
        crud.create_gear(gear_create("Road Bike"), 1, db)
        crud.create_gear(gear_create("Road Bike"), 2, db)

        with pytest.raises(core_exceptions.ConflictError, match="nickname"):
            crud.create_gear(gear_create(" ROAD bike "), 1, db)

    def test_a_taken_provider_id_is_a_conflict(self, db):
        crud.create_gear(gear_create("One", strava_gear_id="b1"), 1, db)

        with pytest.raises(core_exceptions.ConflictError, match="strava_gear_id"):
            crud.create_gear(gear_create("Two", strava_gear_id="b1"), 1, db)

    def test_create_gears_stages_every_gear(self, db):
        crud.create_gears([gear_create("A"), gear_create("B")], 1, db)

        assert crud.get_gears_number(1, db) == 2

    def test_writes_stage_without_committing(self, db):
        crud.create_gear(gear_create(), 1, db)
        db.rollback()

        assert crud.get_gear_user(1, db) == []

    def test_edit_changes_sent_fields_and_never_the_owner(self, db):
        created = crud.create_gear(gear_create(brand="Trek"), 1, db)

        updated = crud.edit_gear(schema.GearUpdate(id=created.id, nickname=" Gravel ", gear_type=1, brand=None), 1, db)

        assert (updated.nickname, updated.brand, updated.user_id) == ("Gravel", "Trek", 1)

    @pytest.mark.parametrize(
        ("change", "cause"),
        [({"nickname": "taken"}, "nickname"), ({"nickname": "Mine", "strava_gear_id": "b1"}, "strava_gear_id")],
    )
    def test_edit_onto_a_taken_nickname_or_provider_id_is_a_conflict(self, change, cause, db):
        crud.create_gear(gear_create("Taken", strava_gear_id="b1"), 1, db)
        mine = crud.create_gear(gear_create("Mine"), 1, db)

        with pytest.raises(core_exceptions.ConflictError, match=cause):
            crud.edit_gear(schema.GearUpdate(id=mine.id, gear_type=1, **change), 1, db)

    def test_edit_of_a_foreign_gear_is_not_found(self, db):
        created = crud.create_gear(gear_create(), 1, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear(schema.GearUpdate(id=created.id, nickname="x", gear_type=1), 2, db)

    def test_delete_removes_the_gear(self, db):
        created = crud.create_gear(gear_create(), 1, db)

        crud.delete_gear(created.id, 1, db)

        assert crud.get_gear_user_by_id(1, created.id, db) is None

    def test_delete_of_a_foreign_gear_is_not_found(self, db):
        created = crud.create_gear(gear_create(), 1, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear(created.id, 2, db)

    def test_strava_gear_is_deleted_per_owner(self, db):
        crud.create_gear(gear_create("S", strava_gear_id="b1"), 1, db)
        crud.create_gear(gear_create("G", garminconnect_gear_id="g1"), 1, db)
        crud.create_gear(gear_create("S2", strava_gear_id="b2"), 2, db)

        crud.delete_all_strava_gear_for_user(1, db)

        assert [g.nickname for g in crud.get_gear_user(1, db)] == ["G"]
        assert len(crud.get_gear_user(2, db)) == 1
