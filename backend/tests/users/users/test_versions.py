"""The users' rows are versioned: a stale edit is refused, a system write still works, a no-op keeps the version."""

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.users.users.crud as users_crud
import modules.users.users.integration_service as users_integration
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users_goals.schema as goals_schema
import modules.users.users_goals.service as goals_service
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.service as profile_service
from tests._factories.users import make_user


@pytest.fixture
def user_id(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created.id


def test_a_goal_edit_names_the_version_it_read(committed_sessions, user_id):
    goal = goals_schema.UserGoalCreate(interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000)
    with committed_sessions() as db:
        created = goals_service.create_goal(user_id, goal, db)
    assert created.version == 1

    replacement = goals_schema.UserGoalUpdate(
        interval="weekly", activity_type="run", goal_type="calories", goal_calories=6000
    )
    with committed_sessions() as db:
        updated = goals_service.update_goal(user_id, created.id, replacement, db, if_match='"1"')
    assert (updated.goal_calories, updated.version) == (6000, 2)

    with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        goals_service.update_goal(user_id, created.id, replacement, db, if_match='"1"')


def test_a_privacy_edit_is_refused_when_the_settings_moved(committed_sessions, user_id):
    with committed_sessions() as db:
        settings = privacy_integration.get_privacy_settings(user_id, db)
    edit = privacy_schema.UserPrivacySettingsUpdate(hide_activity_map=True)

    with committed_sessions() as db:
        profile_service.edit_privacy_settings(user_id, edit, db, if_match=f'"{settings.version}"')
    with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        profile_service.edit_privacy_settings(user_id, edit, db, if_match=f'"{settings.version}"')


def test_a_stale_user_edit_is_refused_and_a_system_write_still_works(committed_sessions, user_id):
    with committed_sessions() as db:
        before = users_crud.get_user_by_id(user_id, db)
        users_crud.update_user(user_id, {"city": "Porto"}, db, if_match=f'"{before.version}"')
        db.commit()

    with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        users_crud.update_user(user_id, {"city": "Lisbon"}, db, if_match=f'"{before.version}"')

    with committed_sessions() as db:
        users_crud.update_user(user_id, {"city": "Faro"}, db)
        db.commit()
    with committed_sessions() as db:
        row = db.scalar(select(users_models.Users).where(users_models.Users.id == user_id))
        assert (row.city, row.version) == ("Faro", before.version + 2)


def test_a_profile_edit_that_changes_nothing_keeps_the_version(committed_sessions, user_id):
    edit = users_schema.ProfileUpdate(city="Porto", height=180)
    with committed_sessions() as db:
        users_integration.edit_profile(user_id, edit, db, if_match="*")
        db.commit()
        first = users_crud.get_user_by_id(user_id, db)

    with committed_sessions() as db:
        users_integration.edit_profile(user_id, edit, db, if_match=f'"{first.version}"')
        db.commit()
        second = users_crud.get_user_by_id(user_id, db)

    assert second.version == first.version
