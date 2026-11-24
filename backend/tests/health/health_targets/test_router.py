"""The targets routes, through the production application: real authentication, scopes and database."""

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.health.health_targets.models as health_targets_models
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/targets"


def _stored(committed_sessions, user_id):
    with committed_sessions() as db:
        row = db.scalar(
            sa.select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
        )
        db.expunge(row)
        return row


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


class TestRead:
    def test_a_new_account_reads_empty_targets_with_their_etag(self, me, user):
        response = me.client.get(_URL)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert body["user_id"] == str(user.id)
        assert [
            body[f] for f in ("weight_kg", "steps", "sleep_seconds", "fasting_seconds", "water_ml", "poop_count")
        ] == [None] * 6

    def test_a_user_without_targets_reads_null_and_no_etag(self, me, user, committed_sessions):
        with committed_sessions() as db:
            db.execute(
                sa.delete(health_targets_models.HealthTargets).where(
                    health_targets_models.HealthTargets.user_id == user.id
                )
            )
            db.commit()

        response = me.client.get(_URL)

        assert (response.status_code, response.json()) == (200, None)
        assert "ETag" not in response.headers

    def test_another_users_targets_are_never_read(self, me, sign_in, committed_sessions):
        with committed_sessions() as db:
            theirs = make_user(db)
            db.commit()
        assert sign_in(theirs).client.patch(_URL, json={"steps": 9000}, headers={"If-Match": '"1"'}).status_code == 200

        assert me.client.get(_URL).json()["steps"] is None


class TestUpdate:
    def test_every_field_is_stored_and_the_etag_moves_on(self, me, user, committed_sessions):
        body = {
            "weight_kg": 75.5,
            "steps": 10000,
            "sleep_seconds": 28800,
            "fasting_seconds": 57600,
            "water_ml": 2500.0,
            "poop_count": 2,
        }

        response = me.client.patch(_URL, json=body, headers={"If-Match": '"1"'})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert {k: response.json()[k] for k in body} == body
        row = _stored(committed_sessions, user.id)
        assert (row.weight_kg, row.steps, row.water_ml, row.version) == (75.5, 10000, 2500, 2)
        assert me.client.get(_URL).json()["version"] == 2

    def test_a_partial_update_keeps_the_other_fields(self, me):
        me.client.patch(_URL, json={"steps": 10000, "weight_kg": 70.0}, headers={"If-Match": '"1"'})

        response = me.client.patch(_URL, json={"steps": 12000}, headers={"If-Match": '"2"'})

        assert (response.json()["steps"], response.json()["weight_kg"]) == (12000, 70.0)

    def test_a_field_set_to_null_is_cleared(self, me):
        me.client.patch(_URL, json={"steps": 10000}, headers={"If-Match": '"1"'})

        response = me.client.patch(_URL, json={"steps": None}, headers={"If-Match": '"2"'})

        assert response.json()["steps"] is None

    def test_a_stale_version_is_412_and_nothing_changes(self, me, user, committed_sessions):
        assert me.client.patch(_URL, json={"steps": 1}, headers={"If-Match": '"9"'}).status_code == 412
        assert _stored(committed_sessions, user.id).version == 1

    def test_a_user_without_targets_is_404(self, me, user, committed_sessions):
        with committed_sessions() as db:
            db.execute(
                sa.delete(health_targets_models.HealthTargets).where(
                    health_targets_models.HealthTargets.user_id == user.id
                )
            )
            db.commit()

        assert me.client.patch(_URL, json={"steps": 1}, headers={"If-Match": '"1"'}).status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            {"steps": 3_000_000_000},
            {"steps": -1},
            {"weight_kg": 0.0},
            {"weight_kg": 600.0},
            {"sleep_seconds": 86401},
            {"fasting_seconds": 259201},
            {"water_ml": 20001.0},
            {"poop_count": 21},
            {"steps": "100"},
            {"user_id": "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"},
            {"version": 5},
        ],
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_changes(self, me, user, committed_sessions, body):
        assert me.client.patch(_URL, json=body, headers={"If-Match": '"1"'}).status_code == 422
        assert _stored(committed_sessions, user.id).version == 1
