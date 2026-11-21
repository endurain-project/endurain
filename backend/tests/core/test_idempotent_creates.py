"""Idempotent creates on the production application: what a replay leaves behind besides the repeated answer.

The repeat, key reuse, invalid key and other-account cases of every create route are proved in
``tests/http_api/test_http_contract.py``; these cover the effects a replay must not repeat and how credentials share
a key.
"""

import jasil.runtime as platform_runtime
import pytest
from sqlalchemy import func, select

import core.config as core_config
import modules.auth.api_keys.constants as api_keys_constants
import modules.followers.events as followers_events
import modules.followers.models as followers_models
import modules.health.health_poop.models as health_poop_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.users import audit_rows_of, make_admin, make_user

_API = core_config.ROOT_PATH
_KEY = {"Idempotency-Key": '"create-0001"'}
_POOP = {"date_time": "2026-01-01T07:00:00Z"}


def _count(sessions, model, *where) -> int:
    with sessions() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def other(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


def test_a_repeated_follow_publishes_one_event_and_makes_one_row(sign_in, user, other, committed_sessions):
    published: list = []
    platform_runtime.get_active_platform().events.subscribe(followers_events.FOLLOWER_REQUESTED, published.append)
    me = sign_in(user)

    first = me.client.post(f"{_API}/users/{other.id}/followers", headers=_KEY)
    second = me.client.post(f"{_API}/users/{other.id}/followers", headers=_KEY)

    assert second.status_code == first.status_code == 201
    assert second.content == first.content
    assert _count(committed_sessions, followers_models.Follower) == 1
    assert len(published) == 1


def test_a_repeated_user_create_writes_one_audit_row(sign_in, committed_sessions):
    with committed_sessions() as db:
        admin = make_admin(db)
        db.commit()
    body = {
        "name": "New User",
        "username": "newuser",
        "email": "new@example.com",
        "password": "Str0ng-Passw0rd!x",
        "access_type": "regular",
        "active": True,
    }
    me = sign_in(admin)

    first = me.client.post(f"{_API}/users", json=body, headers=_KEY)
    second = me.client.post(f"{_API}/users", json=body, headers=_KEY)

    assert first.status_code == second.status_code == 201, first.text + second.text
    assert second.content == first.content
    with committed_sessions() as db:
        assert len(audit_rows_of(db, users_audit_actions.USER_CREATE.id)) == 1
    assert _count(committed_sessions, users_models.Users, users_models.Users.username == "newuser") == 1


def test_a_session_and_an_api_key_of_one_user_share_their_keys(app, sign_in, user, committed_sessions):
    with committed_sessions() as db:
        key, raw_key = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.HEALTH_WRITE])
        db.commit()
    by_session = sign_in(user).client.post(f"{_API}/health/poop", json=_POOP, headers=_KEY)
    by_key = key_client(app, user, key, raw_key).client.post(f"{_API}/health/poop", json=_POOP, headers=_KEY)

    assert by_session.status_code == by_key.status_code == 201
    assert by_key.content == by_session.content
    assert _count(committed_sessions, health_poop_models.HealthPoop) == 1


def test_a_refused_create_stores_nothing_and_leaves_the_key_free(sign_in, user, committed_sessions):
    me = sign_in(user)

    refused = me.client.post(f"{_API}/users/{user.id}/followers", headers=_KEY)

    assert refused.status_code == 400
    assert list(platform_runtime.get_active_platform().state.iter_keys("endurain:idempotency:")) == []
    assert _count(committed_sessions, followers_models.Follower) == 0
