from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.gears.contracts as gears_contracts
import modules.gears.gear.crud as crud
import modules.gears.gear.schema as schema
import modules.gears.gear.service as service
from tests._helpers.gears import gear_create, install_readers


class TestListGears:
    def test_the_total_ignores_the_page(self, db):
        for name in ("A", "B", "C"):
            crud.create_gear(gear_create(name), 1, db)

        result = service.list_gears(1, db, page_number=1, num_records=2)

        assert (result.total, result.num_records, result.page, result.next) == (3, 2, 1, 2)
        assert [g.nickname for g in result.items] == ["A", "B"]


class TestReadGearDetail:
    def test_totals_add_the_initial_kilometres_to_recorded_usage(self, db):
        created = crud.create_gear(gear_create(initial_kms=10.0), 1, db)
        install_readers(
            usage=lambda gear_id, user_id, _db: gears_contracts.UsageTotals(distance=500.0, time=60.0),
            components_cost=lambda gear_id, user_id, _db: 99.5,
        )

        detail = service.read_gear_detail(created.id, 1, db)

        assert (detail.total_distance, detail.total_time, detail.total_components_cost) == (10_500.0, 60.0, 99.5)

    def test_an_unknown_gear_is_not_found_without_asking_for_usage(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            service.read_gear_detail(1, 1, db)

    def test_missing_readers_fail_loudly_rather_than_report_zero(self, db):
        created = crud.create_gear(gear_create(), 1, db)

        with pytest.raises(RuntimeError, match="configure_gear_contributors"):
            service.read_gear_detail(created.id, 1, db)


class TestCreateGear:
    def test_create_commits_and_returns_the_gear(self, db, commit_spy):
        created = service.create_gear(gear_create(), 1, db)

        commit_spy.assert_called_once_with()
        assert created.nickname == "Road Bike"

    def test_a_repeated_nickname_is_a_conflict_and_nothing_is_committed(self, db, commit_spy):
        crud.create_gear(gear_create("Road Bike"), 1, db)

        with pytest.raises(core_exceptions.ConflictError):
            service.create_gear(gear_create(" road bike "), 1, db)

        commit_spy.assert_not_called()


class TestStageGears:
    def test_only_new_unique_named_gears_are_staged(self, db, commit_spy):
        crud.create_gear(gear_create("Existing"), 1, db)

        service.stage_gears(
            [
                gear_create("New"),
                gear_create("new"),
                None,
                gear_create("   "),
                gear_create("EXISTING"),
                gear_create("Another"),
            ],
            1,
            db,
        )

        commit_spy.assert_not_called()
        assert sorted(g.nickname for g in crud.get_gear_user(1, db)) == ["Another", "Existing", "New"]

    def test_nothing_is_written_when_nothing_is_new(self, db):
        crud.create_gear(gear_create("Existing"), 1, db)

        service.stage_gears([gear_create("existing")], 1, db)

        assert crud.get_gears_number(1, db) == 1


class TestEditAndDelete:
    def test_edit_commits_the_change(self, db, commit_spy):
        created = crud.create_gear(gear_create(), 1, db)

        updated = service.edit_gear(created.id, schema.GearUpdate(nickname="Gravel"), 1, db)

        commit_spy.assert_called_once_with()
        assert updated.nickname == "Gravel"

    def test_a_stale_edit_is_a_precondition_failure_and_not_committed(self, db, commit_spy):
        created = crud.create_gear(gear_create(), 1, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_gear(created.id, schema.GearUpdate(brand="x"), 1, db, if_match='"99"')

        commit_spy.assert_not_called()

    def test_delete_commits_after_staging(self, db, commit_spy):
        created = crud.create_gear(gear_create(), 1, db)

        install_readers()

        service.delete_gear(created.id, 1, db)

        commit_spy.assert_called_once_with()
        assert crud.get_gear_user_by_id(1, created.id, db) is None

    def test_delete_unassigns_the_activities_before_removing_the_gear(self, db):
        created = crud.create_gear(gear_create(), 1, db)
        clear = MagicMock(return_value=2)
        install_readers(clear_activities_gear=clear)

        service.delete_gear(created.id, 1, db)

        clear.assert_called_once_with(created.id, 1, db)

    def test_delete_of_a_foreign_gear_is_not_found_and_not_committed(self, db, commit_spy):
        created = crud.create_gear(gear_create(), 8, db)
        install_readers()

        with pytest.raises(core_exceptions.NotFoundError):
            service.delete_gear(created.id, 2, db)

        commit_spy.assert_not_called()


class TestRequireOwnedGears:
    def test_owned_gears_pass(self, db):
        a = crud.create_gear(gear_create("A"), 7, db)
        b = crud.create_gear(gear_create("B"), 7, db)

        service.require_owned_gears(7, [a.id, b.id, a.id], db)

    def test_a_foreign_gear_is_not_found(self, db):
        foreign = crud.create_gear(gear_create(), 8, db)

        with pytest.raises(core_exceptions.NotFoundError):
            service.require_owned_gears(7, [foreign.id], db)

    def test_clearing_a_gear_needs_no_lookup(self):
        db = MagicMock()

        service.require_owned_gears(7, [None], db)

        db.execute.assert_not_called()


class TestConcurrentStaging:
    def test_a_nickname_taken_between_check_and_insert_is_left_out(self, db):
        crud.create_gear(gear_create("Taken"), 1, db)
        with patch("modules.gears.gear.crud.get_existing_nicknames", return_value=set()):
            service.stage_gears([gear_create("taken"), gear_create("Fresh")], 1, db)

        assert sorted(g.nickname for g in crud.get_gear_user(1, db)) == ["Fresh", "Taken"]
