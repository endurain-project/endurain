"""A gear type change and a component create serialise on the gear row against real PostgreSQL."""

import threading

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.service as component_service
from tests._factories.gears import component_payload, make_gear
from tests._factories.users import make_user


@pytest.fixture
def factory(committed_sessions):
    return committed_sessions


@pytest.fixture
def owner(factory):
    with factory() as db:
        created = make_user(db)
        db.commit()
    return created


def test_a_component_create_waits_for_a_type_change_and_is_checked_against_the_new_type(factory, owner):
    with factory() as db:
        gear_id = make_gear(db, owner.id).id
        db.commit()
    outcome: list = []
    started = threading.Event()

    def create_chain() -> None:
        started.set()
        with factory() as db:
            try:
                outcome.append(
                    component_service.create_gear_component(component_payload(gear_id, type="chain"), owner.id, db)
                )
            except Exception as err:
                db.rollback()
                outcome.append(err)

    with factory() as editor:
        gear_crud.lock_gear(gear_id, owner.id, editor)
        thread = threading.Thread(target=create_chain)
        thread.start()
        started.wait(timeout=5)
        thread.join(timeout=1)
        assert thread.is_alive(), "the component create did not wait for the gear lock"

        gear_crud.edit_gear(
            gear_id, gear_schema.GearUpdate(gear_type=gear_schema.GearType.SHOES), owner.id, editor, if_match="*"
        )
        editor.commit()

    thread.join(timeout=10)
    assert len(outcome) == 1
    assert isinstance(outcome[0], core_exceptions.InvalidInputError)
