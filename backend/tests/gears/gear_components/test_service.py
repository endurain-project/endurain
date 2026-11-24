"""The gear component service on the real database: creation against the gear type, edits, deletes, usage listing."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

import core.exceptions as core_exceptions
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.models as models
import modules.gears.gear_components.schema as schema
import modules.gears.gear_components.service as service
from tests._factories.activities import make_activity
from tests._factories.gears import component_payload, make_gear
from tests._factories.users import make_user


@pytest.fixture
def owner(committed_sessions):
    """A committed user with a committed bike."""
    with committed_sessions() as db:
        created = make_user(db)
        bike = make_gear(db, created.id)
        db.commit()
    return created, bike


def _component(db, user_id: uuid.UUID, gear_id: uuid.UUID, index: int):
    """Create a component whose creation time is ``index`` seconds after a fixed instant."""
    created = crud.create_gear_component(component_payload(gear_id), user_id, db)
    db.execute(
        update(models.GearComponents)
        .where(models.GearComponents.id == created.id)
        .values(created_at=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=index))
    )
    db.flush()
    return created


class TestCreate:
    def test_a_component_matching_the_gear_type_is_created_and_committed(self, committed_sessions, owner):
        user, bike = owner

        with committed_sessions() as db:
            created = service.create_gear_component(component_payload(bike.id), user.id, db)

        with committed_sessions() as db:
            assert [c.id for c in crud.get_gear_components_user(user.id, db)] == [created.id]
        assert created.gear_id == bike.id

    def test_a_gear_the_user_does_not_own_is_not_found(self, db, user, other):
        foreign = make_gear(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            service.create_gear_component(component_payload(foreign.id), user.id, db)

    def test_a_gear_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            service.create_gear_component(component_payload(uuid.uuid4()), user.id, db)

    def test_a_type_that_does_not_fit_the_gear_is_refused_and_nothing_is_written(self, committed_sessions, owner):
        user, _ = owner
        with committed_sessions() as db:
            shoes = make_gear(db, user.id, nickname="Shoes", gear_type="shoes")
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError, match="shoes"):
            service.create_gear_component(component_payload(shoes.id, type="chain"), user.id, db)

        with committed_sessions() as db:
            assert crud.get_gear_components_user(user.id, db) == []

    def test_a_gear_type_without_a_restriction_accepts_any_type(self, db, user):
        wetsuit = make_gear(db, user.id, gear_type=gear_schema.GearType.WETSUIT)

        created = service.create_gear_component(component_payload(wetsuit.id, type="anything"), user.id, db)

        assert created.type == "anything"


class TestGet:
    def test_returns_the_users_component(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        assert service.get_gear_component(user.id, created.id, db).id == created.id

    def test_a_component_of_another_user_is_not_found(self, db, user, other):
        theirs = make_gear(db, other.id)
        created = crud.create_gear_component(component_payload(theirs.id), other.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            service.get_gear_component(user.id, created.id, db)


class TestEdit:
    def test_retiring_before_purchase_is_refused(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id, purchase_date=date(2024, 5, 1)), user.id, db)

        with pytest.raises(core_exceptions.InvalidInputError):
            service.edit_gear_component(
                created.id, schema.GearComponentUpdate(retired_date=date(2024, 5, 1)), user.id, db, if_match="*"
            )

    def test_moving_the_purchase_past_the_stored_retired_date_is_refused(self, db, user, gear):
        created = crud.create_gear_component(
            component_payload(gear.id, purchase_date=date(2024, 1, 1), retired_date=date(2024, 6, 1)), user.id, db
        )

        with pytest.raises(core_exceptions.InvalidInputError):
            service.edit_gear_component(
                created.id, schema.GearComponentUpdate(purchase_date=date(2024, 7, 1)), user.id, db, if_match="*"
            )

    def test_a_type_that_does_not_fit_the_gear_is_refused(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        with pytest.raises(core_exceptions.InvalidInputError):
            service.edit_gear_component(
                created.id, schema.GearComponentUpdate(type="not-a-bike-part"), user.id, db, if_match="*"
            )

    def test_editing_a_missing_component_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            service.edit_gear_component(uuid.uuid4(), schema.GearComponentUpdate(brand="x"), user.id, db, if_match="*")

    def test_a_stale_edit_is_a_precondition_failure_and_changes_nothing(self, committed_sessions, owner):
        user, bike = owner
        with committed_sessions() as db:
            created = crud.create_gear_component(component_payload(bike.id), user.id, db)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_gear_component(created.id, schema.GearComponentUpdate(brand="x"), user.id, db, if_match='"99"')

        with committed_sessions() as db:
            assert crud.get_gear_components_user(user.id, db)[0].brand == "Shimano"

    def test_edit_commits(self, committed_sessions, owner):
        user, bike = owner
        with committed_sessions() as db:
            created = crud.create_gear_component(component_payload(bike.id), user.id, db)
            db.commit()

        with committed_sessions() as db:
            updated = service.edit_gear_component(
                created.id, schema.GearComponentUpdate(brand="SRAM"), user.id, db, if_match="*"
            )

        assert updated.brand == "SRAM"
        with committed_sessions() as db:
            assert crud.get_gear_components_user(user.id, db)[0].brand == "SRAM"


class TestDelete:
    def test_delete_commits(self, committed_sessions, owner):
        user, bike = owner
        with committed_sessions() as db:
            created = crud.create_gear_component(component_payload(bike.id), user.id, db)
            db.commit()

        with committed_sessions() as db:
            service.delete_gear_component(user.id, created.id, db, if_match=f'"{created.version}"')

        with committed_sessions() as db:
            assert crud.get_gear_components_user(user.id, db) == []

    def test_a_stale_delete_is_a_precondition_failure_and_keeps_the_component(self, committed_sessions, owner):
        user, bike = owner
        with committed_sessions() as db:
            created = crud.create_gear_component(component_payload(bike.id), user.id, db)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            service.delete_gear_component(user.id, created.id, db, if_match='"99"')

        with committed_sessions() as db:
            assert len(crud.get_gear_components_user(user.id, db)) == 1


class TestListForGear:
    def test_each_component_gets_the_usage_of_its_own_window(self, db, user, gear):
        first = crud.create_gear_component(
            component_payload(gear.id, purchase_date=date(2025, 1, 1), retired_date=date(2025, 3, 1)), user.id, db
        )
        second = crud.create_gear_component(component_payload(gear.id, purchase_date=date(2025, 3, 1)), user.id, db)
        make_activity(
            db,
            user.id,
            gear_id=gear.id,
            distance=100,
            total_timer_time=10.0,
            start_time=datetime(2025, 2, 1, 8, tzinfo=UTC),
            end_time=datetime(2025, 2, 1, 9, tzinfo=UTC),
        )
        make_activity(
            db,
            user.id,
            gear_id=gear.id,
            distance=5,
            total_timer_time=1.0,
            start_time=datetime(2025, 4, 1, 8, tzinfo=UTC),
            end_time=datetime(2025, 4, 1, 9, tzinfo=UTC),
        )

        result = service.list_components_for_gear(gear.id, user.id, db)

        assert {c.id: (c.current_distance, c.current_time) for c in result.items} == {
            first.id: (100.0, 10.0),
            second.id: (5.0, 1.0),
        }

    def test_a_component_with_no_activities_in_its_window_reports_zero(self, db, user, gear):
        crud.create_gear_component(component_payload(gear.id), user.id, db)

        item = service.list_components_for_gear(gear.id, user.id, db).items[0]

        assert (item.current_distance, item.current_time) == (0, 0)

    def test_no_components_gives_an_empty_page(self, db, user, gear):
        result = service.list_components_for_gear(gear.id, user.id, db)

        assert (result.items, result.total) == ([], 0)

    def test_a_page_lists_its_slice_and_the_total_counts_every_component(self, db, user, gear):
        _component(db, user.id, gear.id, 0)
        second = _component(db, user.id, gear.id, 1)

        result = service.list_components_for_gear(gear.id, user.id, db, page_number=2, num_records=1)

        assert [c.id for c in result.items] == [second.id]
        assert result.total == 2

    def test_the_active_filter_applies(self, db, user, gear):
        _component(db, user.id, gear.id, 0)
        retired = _component(db, user.id, gear.id, 1)
        crud.edit_gear_component(
            retired.id, schema.GearComponentUpdate(retired_date=date(2025, 1, 1)), user.id, db, if_match="*"
        )

        result = service.list_components_for_gear(gear.id, user.id, db, active=False)

        assert [c.id for c in result.items] == [retired.id]

    def test_another_users_gear_lists_nothing(self, db, user, other):
        theirs = make_gear(db, other.id)
        crud.create_gear_component(component_payload(theirs.id), other.id, db)

        assert service.list_components_for_gear(theirs.id, user.id, db).total == 0


def test_the_user_list_is_paged_with_the_total(db, user, gear):
    for _ in range(3):
        crud.create_gear_component(component_payload(gear.id), user.id, db)

    page = service.list_gear_components(user.id, db, page_number=1, num_records=2)

    assert (len(page.items), page.total, page.next) == (2, 3, 2)


def test_component_types_are_grouped_by_gear_type():
    types = service.read_component_types()

    assert "chain" in types.bike
    assert "cleats" in types.shoes
