from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.crud as crud
import modules.gears.gear.schema as schema
import modules.gears.gear.service as service


def _gear(nickname="Road Bike", **overrides) -> schema.GearCreate:
    return schema.GearCreate(**{"nickname": nickname, "gear_type": schema.GearType.BIKE, **overrides})


class TestListGears:
    def test_the_total_ignores_the_page(self, db):
        for name in ("A", "B", "C"):
            crud.create_gear(_gear(name), 1, db)

        result = service.list_gears(1, db, page_number=1, num_records=2)

        assert (result.total, result.num_records, result.page_number) == (3, 2, 1)
        assert [g.nickname for g in result.records] == ["A", "B"]


class TestReadGearDetail:
    def test_totals_add_the_initial_kilometres_to_recorded_usage(self, db):
        created = crud.create_gear(_gear(initial_kms=10.0), 1, db)
        gears_contributor_registry.register_gear_usage_reader(
            lambda gear_id, user_id, _db: gears_contracts.UsageTotals(distance=500.0, time=60.0)
        )
        gears_contributor_registry.register_components_cost_reader(lambda gear_id, user_id, _db: 99.5)

        detail = service.read_gear_detail(created.id, 1, db)

        assert (detail.total_distance, detail.total_time, detail.total_components_cost) == (10_500.0, 60.0, 99.5)

    def test_an_unknown_gear_reads_as_none_without_asking_for_usage(self, db):
        assert service.read_gear_detail(1, 1, db) is None

    def test_missing_contributors_fail_loudly_rather_than_report_zero(self, db):
        created = crud.create_gear(_gear(), 1, db)

        with pytest.raises(RuntimeError, match="configure_gear_contributors"):
            service.read_gear_detail(created.id, 1, db)


class TestCreateGear:
    def test_create_commits_and_returns_the_gear(self, db):
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        created = service.create_gear(_gear(), 1, db)

        spy.assert_called_once_with()
        assert created.nickname == "Road Bike"

    def test_a_repeated_nickname_is_a_conflict_and_nothing_is_committed(self, db):
        crud.create_gear(_gear("Road Bike"), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        with pytest.raises(core_exceptions.ConflictError):
            service.create_gear(_gear(" road bike "), 1, db)

        spy.assert_not_called()

    def test_stage_gear_leaves_the_commit_to_the_caller(self, db):
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        service.stage_gear(_gear(), 1, db)

        spy.assert_not_called()


class TestStageGears:
    def test_only_new_unique_named_gears_are_staged(self, db):
        crud.create_gear(_gear("Existing"), 1, db)

        service.stage_gears(
            [_gear("New"), _gear("new"), None, _gear("   "), _gear("EXISTING"), _gear("Another")],
            1,
            db,
        )

        assert sorted(g.nickname for g in crud.get_gear_user(1, db)) == ["Another", "Existing", "New"]

    def test_nothing_is_written_when_nothing_is_new(self, db):
        crud.create_gear(_gear("Existing"), 1, db)

        service.stage_gears([_gear("existing")], 1, db)

        assert crud.get_gears_number(1, db) == 1


class TestEditAndDelete:
    def test_edit_commits_the_change(self, db):
        created = crud.create_gear(_gear(), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        updated = service.edit_gear(schema.GearUpdate(id=created.id, nickname="Gravel", gear_type=1), 1, db)

        spy.assert_called_once_with()
        assert updated.nickname == "Gravel"

    def test_delete_commits_after_staging(self, db):
        created = crud.create_gear(_gear(), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        service.delete_gear(created.id, 1, db)

        spy.assert_called_once_with()
        assert crud.get_gear_user_by_id(1, created.id, db) is None

    def test_delete_of_a_foreign_gear_is_not_found_and_not_committed(self, db):
        created = crud.create_gear(_gear(), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        with pytest.raises(core_exceptions.NotFoundError):
            service.delete_gear(created.id, 2, db)

        spy.assert_not_called()


class TestRequireOwnedGears:
    def test_owned_gears_pass(self, db):
        a = crud.create_gear(_gear("A"), 7, db)
        b = crud.create_gear(_gear("B"), 7, db)

        service.require_owned_gears(7, [a.id, b.id, a.id], db)

    def test_a_foreign_gear_is_not_found(self, db):
        foreign = crud.create_gear(_gear(), 8, db)

        with pytest.raises(core_exceptions.NotFoundError):
            service.require_owned_gears(7, [foreign.id], db)

    def test_clearing_a_gear_needs_no_lookup(self):
        db = MagicMock()

        service.require_owned_gears(7, [None], db)

        db.execute.assert_not_called()
