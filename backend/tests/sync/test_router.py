"""``GET /sync`` through the production application: the page shape, the problem types and the parameters."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import core.config as core_config
import core.cryptography as core_cryptography
import core.sync as core_sync
import modules.auth.api_keys.constants as api_keys_constants
import modules.health.health_steps.models as steps_models
import modules.health.health_weight.models as weight_models
import modules.sync.service as sync_service
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.health import make_health_steps, make_health_weight
from tests._factories.sync import restamp
from tests._factories.users import make_user

_SYNC = f"{core_config.ROOT_PATH}/sync"
_LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def records(committed_sessions):
    """A user with a weight and a steps record, stamped long enough ago for a sync to report them."""
    with committed_sessions() as db:
        user = make_user(db)
        weight = make_health_weight(db, user.id)
        steps = make_health_steps(db, user.id)
        other = make_user(db)
        foreign = make_health_weight(db, other.id)
        restamp(db, weight_models.HealthWeight, [weight.id, foreign.id], _LONG_AGO)
        restamp(db, steps_models.HealthSteps, [steps.id], _LONG_AGO + timedelta(days=1))
        db.commit()
    return user, weight.id, steps.id, foreign.id


def _cursor(**raw) -> str:
    return core_cryptography.encrypt_token_fernet(json.dumps({"t": datetime.now(UTC).isoformat(), **raw}))


def test_a_sync_reports_the_callers_changes_then_nothing_with_the_cursor_it_returned(sign_in, records):
    user, weight, steps, foreign = records
    client = sign_in(user).client

    first = client.get(_SYNC)

    assert first.status_code == 200
    body = first.json()
    assert [(change["type"], change["id"]) for change in body["changes"]] == [
        ("health_weight", str(weight)),
        ("health_steps", str(steps)),
    ]
    assert body["changes"][0]["record"]["weight_kg"] == 75
    assert body["has_more"] is False
    assert str(foreign) not in first.text
    assert client.get(_SYNC, params={"cursor": body["next_cursor"]}).json()["changes"] == []


def test_the_page_size_and_the_cursor_page_through_the_changes(sign_in, records):
    user, weight, steps, _ = records
    client = sign_in(user).client

    first = client.get(_SYNC, params={"num_records": 1}).json()
    second = client.get(_SYNC, params={"num_records": 1, "cursor": first["next_cursor"]}).json()

    assert [change["id"] for change in first["changes"]] == [str(weight)]
    assert first["has_more"] is True
    assert [change["id"] for change in second["changes"]] == [str(steps)]
    assert second["has_more"] is False


def test_types_limit_the_walk(sign_in, records):
    user, _, steps, _ = records

    response = sign_in(user).client.get(_SYNC, params=[("types", "health_steps")])

    assert [change["id"] for change in response.json()["changes"]] == [str(steps)]


def test_a_key_syncs_only_the_types_its_scopes_read_and_is_refused_the_others(app, committed_sessions, records):
    user = records[0]
    with committed_sessions() as db:
        key, raw_key = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.GEARS_READ])
        db.commit()
    client = key_client(app, user, key, raw_key).client

    assert client.get(_SYNC).json()["changes"] == []
    refused = client.get(_SYNC, params=[("types", "health_weight")])
    assert refused.status_code == 403


def test_an_expired_cursor_is_410_sync_expired(sign_in, records):
    stale = datetime.now(UTC) - core_sync.TOMBSTONE_RETENTION - timedelta(days=1)
    cursor = core_cryptography.encrypt_token_fernet(
        json.dumps({"f": sync_service._CURSOR_FORMAT, "t": stale.isoformat()})
    )

    response = sign_in(records[0]).client.get(_SYNC, params={"cursor": cursor})

    assert response.status_code == 410
    assert response.json()["type"] == "urn:endurain:error:sync-expired"


def test_a_cursor_of_the_old_format_is_410_sync_expired(sign_in, records):
    old = _cursor(s=datetime.now(UTC).isoformat(), r=0, i=str(uuid.uuid4()))

    response = sign_in(records[0]).client.get(_SYNC, params={"cursor": old})

    assert response.status_code == 410
    assert response.json()["type"] == "urn:endurain:error:sync-expired"


@pytest.mark.parametrize(
    "cursor",
    ["not-a-cursor", _cursor(f=sync_service._CURSOR_FORMAT, s="2026-01-01T00:00:00+00:00", r=2, i="not-a-uuid")],
    ids=["not issued by the server", "malformed id"],
)
def test_a_cursor_the_server_did_not_issue_is_400(sign_in, records, cursor):
    assert sign_in(records[0]).client.get(_SYNC, params={"cursor": cursor}).status_code == 400


def test_an_unknown_type_and_an_oversized_page_are_refused(sign_in, records):
    client = sign_in(records[0]).client

    assert client.get(_SYNC, params={"types": "nope"}).status_code == 422
    assert client.get(_SYNC, params={"num_records": 5000}).status_code == 422
