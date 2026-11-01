"""The users tables are versioned against real PostgreSQL."""

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
import modules.users.users_goals.schema as goals_schema
import modules.users.users_goals.service as goals_service
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.service as profile_service
from tests._helpers.db import ensure_user


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        # The helper's placeholder language is not one the read schema accepts.
        db.get(users_models.Users, 1).preferred_language = "en"
        db.commit()
    return pg_factory


def test_a_goal_edit_names_the_version_it_read(factory):
    goal = goals_schema.UsersGoalCreate(
        interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
    )
    with factory() as db:
        created = goals_service.create_goal(1, goal, db)
    assert created.version == 1

    replacement = goals_schema.UsersGoalUpdate(
        interval="weekly", activity_type="run", goal_type="calories", goal_calories=6000
    )
    with factory() as db:
        updated = goals_service.update_goal(1, created.id, replacement, db, if_match='"1"')
    assert (updated.goal_calories, updated.version) == (6000, 2)

    with factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        goals_service.update_goal(1, created.id, replacement, db, if_match='"1"')


def test_a_privacy_edit_is_refused_when_the_settings_moved(factory):
    with factory() as db:
        created = privacy_integration.create_privacy_settings(1, db)
        db.commit()
    edit = privacy_schema.UsersPrivacySettingsUpdate(hide_activity_map=True)

    with factory() as db:
        profile_service.edit_privacy_settings(1, edit, db, if_match=f'"{created.version}"')
    with factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        profile_service.edit_privacy_settings(1, edit, db, if_match=f'"{created.version}"')


def test_a_stale_user_edit_is_refused_and_a_system_write_still_works(factory):
    with factory() as db:
        before = users_crud.get_user_by_id(1, db)
        assert before is not None
        users_crud.update_user(1, {"city": "Porto"}, db, if_match=f'"{before.version}"')
        db.commit()

    with factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        users_crud.update_user(1, {"city": "Lisbon"}, db, if_match=f'"{before.version}"')

    with factory() as db:
        users_crud.update_user(1, {"city": "Faro"}, db)
        db.commit()
    with factory() as db:
        row = db.scalar(select(users_models.Users).where(users_models.Users.id == 1))
        assert (row.city, row.version) == ("Faro", before.version + 2)
