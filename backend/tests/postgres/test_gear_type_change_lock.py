"""A gear type change and a component create serialise on the gear row against real PostgreSQL."""

import threading

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear.service as gear_service
import modules.gears.gear_components.service as component_service
from tests._helpers.db import ensure_user
from tests._helpers.gears import component_create, gear_create


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, 1)
    return pg_factory


def test_a_component_create_waits_for_a_type_change_and_is_checked_against_the_new_type(factory):
    with factory() as db:
        gear_id = gear_service.create_gear(gear_create(), 1, db).id
    outcome: list = []
    started = threading.Event()

    def create_chain() -> None:
        started.set()
        with factory() as db:
            try:
                outcome.append(component_service.create_gear_component(component_create(gear_id, type="chain"), 1, db))
            except Exception as err:
                db.rollback()
                outcome.append(err)

    with factory() as editor:
        gear_crud.lock_gear(gear_id, 1, editor)
        thread = threading.Thread(target=create_chain)
        thread.start()
        started.wait(timeout=5)
        thread.join(timeout=1)
        assert thread.is_alive(), "the component create did not wait for the gear lock"

        gear_crud.edit_gear(
            gear_id, gear_schema.GearUpdate(gear_type=gear_schema.GearType.SHOES), 1, editor, if_match="*"
        )
        editor.commit()

    thread.join(timeout=10)
    assert len(outcome) == 1
    assert isinstance(outcome[0], core_exceptions.InvalidInputError)
