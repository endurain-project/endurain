"""The API-key routes of the signed-in user: what they return, what they never reveal and how they refuse."""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.models as api_keys_models
from tests._factories.api_keys import make_api_key
from tests._factories.tokens import audit_rows, make_mfa, totp_code
from tests._factories.users import PASSWORD, make_user

_API_KEYS = f"{core_config.ROOT_PATH}/profile/api-keys"
_SCOPES = [api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD]
_STEP_UP_FAILED = "urn:endurain:error:step-up-failed"


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "FitoTrack",
        "scopes": ["activities:upload"],
        "step_up": {"current_password": PASSWORD},
    } | overrides


def _rows(committed_sessions, user_id: uuid.UUID) -> list[api_keys_models.UsersApiKeys]:
    with committed_sessions() as db:
        return list(
            db.scalars(sa.select(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.user_id == user_id))
        )


def _user_with_keys(committed_sessions, count: int):
    with committed_sessions() as db:
        user = make_user(db)
        keys = [make_api_key(db, user, scopes=_SCOPES, name=f"key {index}") for index in range(count)]
        db.commit()
    return user, keys


class TestList:
    def test_a_page_lists_only_the_owners_keys_without_their_secrets(self, committed_sessions, sign_in):
        user, keys = _user_with_keys(committed_sessions, 2)
        _user_with_keys(committed_sessions, 1)

        response = sign_in(user).client.get(_API_KEYS)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert {item["id"] for item in body["items"]} == {str(key.id) for key, _ in keys}
        for item in body["items"]:
            assert "key" not in item and "key_hash" not in item
            assert item["user_id"] == str(user.id)
            assert item["scopes"] == ["activities:upload"]
        raw_keys = [raw for _, raw in keys]
        assert not any(raw in response.text for raw in raw_keys)

    def test_a_user_without_keys_gets_an_empty_page(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 0)

        response = sign_in(user).client.get(_API_KEYS)

        assert response.status_code == 200
        assert (response.json()["items"], response.json()["total"]) == ([], 0)

    def test_the_pagination_parameters_split_the_keys_over_pages(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 3)
        owner = sign_in(user)

        first = owner.client.get(_API_KEYS, params={"page_number": 1, "num_records": 2})
        second = owner.client.get(_API_KEYS, params={"page_number": 2, "num_records": 2})

        assert [len(first.json()["items"]), len(second.json()["items"])] == [2, 1]
        assert first.json()["total"] == second.json()["total"] == 3


class TestCreate:
    def test_the_secret_is_returned_once_and_only_its_hash_is_stored(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 0)
        owner = sign_in(user)

        created = owner.client.post(_API_KEYS, json=_payload())

        assert created.status_code == 201
        assert created.headers["Cache-Control"] == "no-store"
        body = created.json()
        assert "key_hash" not in body
        raw_key = body["key"]
        (row,) = _rows(committed_sessions, user.id)
        assert str(row.id) == body["id"]
        assert row.key_hash == api_keys_integration.hash_api_key(raw_key)
        assert raw_key.startswith("endurain_") and row.key_prefix == body["key_prefix"]
        listed = owner.client.get(_API_KEYS)
        assert raw_key not in listed.text
        creates = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_CREATE)
        assert [(row.outcome, row.target_id, row.details["scopes"]) for row in creates] == [
            ("success", body["id"], ["activities:upload"])
        ]

    def test_a_user_that_signs_in_with_a_second_factor_must_prove_it_to_create_a_key(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            factors = make_mfa(db, user)
            db.commit()
        owner = sign_in(user)

        without_code = owner.client.post(_API_KEYS, json=_payload())
        wrong_code = owner.client.post(
            _API_KEYS, json=_payload(step_up={"current_password": PASSWORD, "mfa_code": "000000"})
        )
        assert [without_code.status_code, wrong_code.status_code] == [403, 403]
        assert without_code.json()["type"] == wrong_code.json()["type"] == _STEP_UP_FAILED
        assert _rows(committed_sessions, user.id) == []

        accepted = owner.client.post(
            _API_KEYS,
            json=_payload(step_up={"current_password": PASSWORD, "mfa_code": totp_code(factors.secret, steps_ahead=1)}),
        )
        assert accepted.status_code == 201
        assert len(_rows(committed_sessions, user.id)) == 1

    def test_a_missing_or_wrong_password_is_refused_and_creates_nothing(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 0)
        owner = sign_in(user)

        missing = owner.client.post(_API_KEYS, json=_payload(step_up={}))
        wrong = owner.client.post(_API_KEYS, json=_payload(step_up={"current_password": "wrong"}))

        assert [missing.status_code, wrong.status_code] == [403, 403]
        assert wrong.json()["type"] == _STEP_UP_FAILED
        assert _rows(committed_sessions, user.id) == []
        assert audit_rows(committed_sessions, account_security_audit_actions.API_KEY_CREATE) == []

    def test_a_request_the_schema_refuses_is_a_validation_error_and_creates_nothing(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 0)
        owner = sign_in(user)
        refused = {
            "unknown scope": _payload(scopes=["fake:scope"]),
            "scope an API key never holds": _payload(scopes=["account:security"]),
            "empty scopes": _payload(scopes=[]),
            "empty name": _payload(name=""),
            "past expiry": _payload(expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()),
            "expiry without an offset": _payload(expires_at="2999-01-01"),
            "unexpected field": _payload(user_id=str(uuid.uuid4())),
        }

        statuses = {label: owner.client.post(_API_KEYS, json=body).status_code for label, body in refused.items()}

        assert statuses == dict.fromkeys(refused, 422)
        assert _rows(committed_sessions, user.id) == []

    def test_an_unknown_scope_is_refused_with_the_allowed_scopes_named_and_no_python_repr(
        self, committed_sessions, sign_in
    ):
        user, _ = _user_with_keys(committed_sessions, 0)

        response = sign_in(user).client.post(_API_KEYS, json=_payload(scopes=["bogus:scope"]))

        assert response.status_code == 422
        assert "activities:upload" in response.text
        assert "frozenset" not in response.text


class TestRevokeAndDelete:
    def test_the_owner_deletes_a_key_and_the_deletion_is_audited(self, committed_sessions, sign_in):
        user, keys = _user_with_keys(committed_sessions, 2)
        (gone, _), (kept, _) = keys

        response = sign_in(user).client.delete(f"{_API_KEYS}/{gone.id}")

        assert response.status_code == 204
        assert {row.id for row in _rows(committed_sessions, user.id)} == {kept.id}
        deletes = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_DELETE)
        assert [(row.outcome, row.target_id) for row in deletes] == [("success", str(gone.id))]

    def test_another_users_key_and_a_missing_key_are_not_found_and_stay_as_they_were(self, committed_sessions, sign_in):
        user, keys = _user_with_keys(committed_sessions, 1)
        stranger, _ = _user_with_keys(committed_sessions, 0)
        key = keys[0][0]
        client = sign_in(stranger).client

        results = [client.post(f"{_API_KEYS}/{target}/revoke").status_code for target in (key.id, uuid.uuid4())] + [
            client.delete(f"{_API_KEYS}/{target}").status_code for target in (key.id, uuid.uuid4())
        ]

        assert results == [404, 404, 404, 404]
        (row,) = _rows(committed_sessions, user.id)
        assert (row.is_active, row.revoked_at) == (True, None)
        assert audit_rows(committed_sessions, account_security_audit_actions.API_KEY_REVOKE) == []
        assert audit_rows(committed_sessions, account_security_audit_actions.API_KEY_DELETE) == []

    def test_a_malformed_key_id_is_a_validation_error(self, committed_sessions, sign_in):
        user, _ = _user_with_keys(committed_sessions, 0)

        response = sign_in(user).client.delete(f"{_API_KEYS}/not-a-uuid")

        assert response.status_code == 422
