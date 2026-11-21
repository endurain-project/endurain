"""The gear service on the real database: reads with usage totals, writes that commit, type changes, deletion."""

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as crud
import modules.gears.gear.schema as schema
import modules.gears.gear.service as service
import modules.gears.gear_components.crud as gear_components_crud
from tests._factories.activities import make_activity
from tests._factories.gears import gear_payload, make_gear, make_gear_component
from tests._factories.users import make_user


@pytest.fixture
def owner(committed_sessions):
    """A committed user."""
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def committed_gear(committed_sessions, owner):
    """A committed bike of the owner."""
    with committed_sessions() as db:
        created = make_gear(db, owner.id)
        db.commit()
    return created


def _stored(committed_sessions, owner, gear_id):
    """Read a gear back in a new session, or ``None``."""
    with committed_sessions() as db:
        return crud.get_gear_user_by_id(owner.id, gear_id, db)


class TestListGears:
    def test_the_total_ignores_the_page(self, db, user):
        for name in ("A", "B", "C"):
            make_gear(db, user.id, nickname=name)

        result = service.list_gears(user.id, db, page_number=1, num_records=2)

        assert (result.total, result.num_records, result.page, result.next) == (3, 2, 1, 2)
        assert [g.nickname for g in result.items] == ["A", "B"]


class TestReadGearDetail:
    def test_totals_add_the_initial_distance_to_recorded_usage_and_sum_the_component_costs(self, db, user):
        gear = make_gear(db, user.id, initial_distance=10_000.0)
        make_activity(db, user.id, gear_id=gear.id, distance=500, total_timer_time=60.0)
        make_activity(db, user.id)
        make_gear_component(db, user.id, gear.id, purchase_value="99.50")

        detail = service.read_gear_detail(gear.id, user.id, db)

        assert (detail.total_distance, detail.total_time, detail.total_components_cost) == (10_500.0, 60.0, "99.50")

    def test_a_gear_without_activities_or_components_has_only_its_initial_distance(self, db, user):
        gear = make_gear(db, user.id)

        detail = service.read_gear_detail(gear.id, user.id, db)

        assert (detail.total_distance, detail.total_time, detail.total_components_cost) == (0.0, 0.0, "0.00")

    def test_another_users_activities_do_not_count(self, db, user, other):
        gear = make_gear(db, user.id)
        make_activity(db, other.id, gear_id=gear.id, distance=700)

        assert service.read_gear_detail(gear.id, user.id, db).total_distance == 0.0

    def test_an_unknown_or_foreign_gear_is_not_found(self, db, user, other):
        foreign = make_gear(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            service.read_gear_detail(foreign.id, user.id, db)

    def test_missing_readers_fail_loudly_rather_than_report_zero(self, db, user):
        gear = make_gear(db, user.id)
        gears_contributor_registry.clear()

        with pytest.raises(RuntimeError, match="configure_gear_contributors"):
            service.read_gear_detail(gear.id, user.id, db)


class TestCreateGear:
    def test_create_commits_and_returns_the_gear(self, committed_sessions, owner):
        with committed_sessions() as db:
            created = service.create_gear(
                schema.GearCreateRequest(nickname="Road Bike", gear_type="bike"), owner.id, db
            )

        assert _stored(committed_sessions, owner, created.id).nickname == "Road Bike"

    def test_a_repeated_nickname_is_a_conflict_and_leaves_one_gear(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            service.create_gear(
                schema.GearCreateRequest(nickname=f" {committed_gear.nickname.lower()} ", gear_type="bike"),
                owner.id,
                db,
            )

        with committed_sessions() as db:
            assert crud.get_gears_number(owner.id, db) == 1


class TestStageGears:
    def test_only_new_unique_named_gears_are_staged(self, db, user):
        make_gear(db, user.id, nickname="Existing")

        service.stage_gears(
            [
                gear_payload("New"),
                gear_payload("new"),
                None,
                gear_payload("   "),
                gear_payload("EXISTING"),
                gear_payload("Another"),
            ],
            user.id,
            db,
        )

        assert sorted(g.nickname for g in crud.get_gear_user(user.id, db)) == ["Another", "Existing", "New"]

    def test_nothing_is_written_when_nothing_is_new(self, db, user):
        make_gear(db, user.id, nickname="Existing")

        service.stage_gears([gear_payload("existing")], user.id, db)

        assert crud.get_gears_number(user.id, db) == 1

    def test_staged_gears_are_left_to_the_caller_to_commit(self, committed_sessions, owner):
        with committed_sessions() as db:
            service.stage_gears([gear_payload("Staged")], owner.id, db)
            db.rollback()

        with committed_sessions() as db:
            assert crud.get_gear_user(owner.id, db) == []


class TestEditGearType:
    def test_a_type_change_with_a_component_of_the_old_type_is_a_conflict_and_changes_nothing(
        self, committed_sessions, owner, committed_gear
    ):
        with committed_sessions() as db:
            make_gear_component(db, owner.id, committed_gear.id, type="chain")
            db.commit()

        with (
            committed_sessions() as db,
            pytest.raises(core_exceptions.ComponentsOutsideGearTypeError, match="Remove the components"),
        ):
            service.edit_gear(
                committed_gear.id, schema.GearUpdate(gear_type=schema.GearType.SHOES), owner.id, db, if_match="*"
            )

        assert _stored(committed_sessions, owner, committed_gear.id).gear_type == schema.GearType.BIKE

    def test_a_type_change_without_components_is_applied(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db:
            updated = service.edit_gear(
                committed_gear.id, schema.GearUpdate(gear_type=schema.GearType.SHOES), owner.id, db, if_match="*"
            )

        assert updated.gear_type == schema.GearType.SHOES
        assert _stored(committed_sessions, owner, committed_gear.id).gear_type == schema.GearType.SHOES

    def test_a_type_change_to_a_type_that_accepts_every_component_is_applied(self, db, user):
        gear = make_gear(db, user.id)
        make_gear_component(db, user.id, gear.id, type="chain")

        updated = service.edit_gear(
            gear.id, schema.GearUpdate(gear_type=schema.GearType.WETSUIT), user.id, db, if_match="*"
        )

        assert updated.gear_type == schema.GearType.WETSUIT

    def test_an_edit_that_keeps_the_type_is_applied_whatever_the_components(self, db, user):
        gear = make_gear(db, user.id)
        make_gear_component(db, user.id, gear.id, type="chain")

        renamed = service.edit_gear(gear.id, schema.GearUpdate(nickname="Gravel"), user.id, db, if_match="*")
        same_type = service.edit_gear(
            gear.id, schema.GearUpdate(gear_type=schema.GearType.BIKE), user.id, db, if_match="*"
        )

        assert (renamed.nickname, same_type.gear_type) == ("Gravel", schema.GearType.BIKE)

    def test_a_stale_type_change_is_a_precondition_failure_even_with_components_outside_the_type(self, db, user):
        gear = make_gear(db, user.id)
        make_gear_component(db, user.id, gear.id, type="chain")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_gear(gear.id, schema.GearUpdate(gear_type=schema.GearType.SHOES), user.id, db, if_match='"99"')

    def test_a_type_change_of_a_foreign_gear_is_not_found(self, db, user, other):
        foreign = make_gear(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            service.edit_gear(foreign.id, schema.GearUpdate(gear_type=schema.GearType.SHOES), user.id, db, if_match="*")


class TestEditAndDelete:
    def test_edit_commits_the_change(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db:
            updated = service.edit_gear(
                committed_gear.id, schema.GearUpdate(nickname="Gravel"), owner.id, db, if_match="*"
            )

        assert updated.nickname == "Gravel"
        assert _stored(committed_sessions, owner, committed_gear.id).nickname == "Gravel"

    def test_a_stale_edit_is_a_precondition_failure_and_changes_nothing(
        self, committed_sessions, owner, committed_gear
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_gear(committed_gear.id, schema.GearUpdate(brand="x"), owner.id, db, if_match='"99"')

        stored = _stored(committed_sessions, owner, committed_gear.id)
        assert (stored.brand, stored.version) == (None, committed_gear.version)

    def test_delete_commits_after_staging(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db:
            service.delete_gear(committed_gear.id, owner.id, db, if_match=f'"{committed_gear.version}"')

        assert _stored(committed_sessions, owner, committed_gear.id) is None

    def test_a_stale_delete_is_a_precondition_failure_and_keeps_the_gear(
        self, committed_sessions, owner, committed_gear
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            service.delete_gear(committed_gear.id, owner.id, db, if_match='"99"')

        assert _stored(committed_sessions, owner, committed_gear.id) is not None

    def test_delete_unassigns_the_activities_in_batches_before_removing_the_gear(
        self, committed_sessions, monkeypatch, owner, committed_gear
    ):
        monkeypatch.setattr(gears_constants, "DELETION_BATCH_SIZE", 2)
        with committed_sessions() as db:
            ids = [make_activity(db, owner.id, gear_id=committed_gear.id).id for _ in range(5)]
            db.commit()

        with committed_sessions() as db:
            service.delete_gear(committed_gear.id, owner.id, db, if_match="*")

        with committed_sessions() as db:
            rows = db.execute(select(activity_models.Activity.id, activity_models.Activity.gear_id)).all()
        assert {row.id for row in rows} == set(ids)
        assert all(row.gear_id is None for row in rows)

    def test_delete_of_a_gear_removes_its_components_with_it(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db:
            make_gear_component(db, owner.id, committed_gear.id)
            db.commit()

        with committed_sessions() as db:
            service.delete_gear(committed_gear.id, owner.id, db, if_match="*")

        with committed_sessions() as db:
            assert gear_components_crud.get_gear_components_user(owner.id, db) == []

    def test_delete_of_a_foreign_gear_is_not_found_and_keeps_it(self, committed_sessions, owner, committed_gear):
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            service.delete_gear(committed_gear.id, stranger.id, db, if_match="*")

        assert _stored(committed_sessions, owner, committed_gear.id) is not None


class TestDeleteAllStravaGearForUser:
    def test_only_the_users_strava_gears_are_removed(self, db, user, other):
        crud.create_gear(gear_payload("S", strava_gear_id="b1"), user.id, db)
        crud.create_gear(gear_payload("G", garminconnect_gear_id="g1"), user.id, db)
        crud.create_gear(gear_payload("S2", strava_gear_id="b2"), other.id, db)

        service.delete_all_strava_gear_for_user(user.id, db)

        assert [g.nickname for g in crud.get_gear_user(user.id, db)] == ["G"]
        assert len(crud.get_gear_user(other.id, db)) == 1

    def test_the_activities_of_a_removed_strava_gear_are_unassigned(self, db, user):
        strava = crud.create_gear(gear_payload("S", strava_gear_id="b1"), user.id, db)
        activity = make_activity(db, user.id, gear_id=strava.id)

        service.delete_all_strava_gear_for_user(user.id, db)
        db.expire_all()

        assert db.get(activity_models.Activity, activity.id).gear_id is None


class TestRequireOwnedGears:
    def test_owned_gears_pass(self, db, other):
        a = make_gear(db, other.id, nickname="A")
        b = make_gear(db, other.id, nickname="B")

        service.require_owned_gears(other.id, [a.id, b.id, a.id], db)

    def test_a_foreign_gear_is_not_found(self, db, user, other):
        foreign = make_gear(db, user.id)

        with pytest.raises(core_exceptions.NotFoundError):
            service.require_owned_gears(other.id, [foreign.id], db)

    def test_clearing_a_gear_needs_no_ownership(self, db, other):
        service.require_owned_gears(other.id, [None], db)
