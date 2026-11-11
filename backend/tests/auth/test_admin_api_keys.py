"""Tests for an administrator's routes over another user's API keys and the service behind them."""

from unittest.mock import MagicMock, patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.events as account_security_events
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema

_STEP_UP = auth_schema.StepUpVerification(current_password="pw")
_CHANGE = account_security_events.AccountSecurityChange.API_KEYS_REVOKED_BY_ADMIN


@pytest.fixture
def published():
    with patch.object(platform_publisher, "publish_on_commit") as publish:
        yield publish


def _assert_owner_notified(publish, user_id=7):
    publish.assert_called_once()
    assert publish.call_args.args[0] == account_security_events.ACCOUNT_SECURITY_CHANGED
    assert publish.call_args.args[1]["user_id"] == user_id
    assert publish.call_args.args[1]["change"] == _CHANGE.value


class TestListService:
    def test_a_missing_user_is_not_found(self, mock_db):
        with (
            patch.object(
                api_key_service.users_integration, "require_user", side_effect=core_exceptions.NotFoundError("x")
            ),
            patch.object(api_key_service.api_keys_integration, "list_user_api_keys") as listing,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            api_key_service.list_api_keys_of_user(7, core_pagination.PageParams(1, 25), mock_db)

        listing.assert_not_called()

    def test_it_lists_the_users_keys(self, mock_db):
        page = api_keys_schema.UserApiKeyPage.build([], 0, 1, 25)
        params = core_pagination.PageParams(1, 25)
        with (
            patch.object(api_key_service.users_integration, "require_user"),
            patch.object(api_key_service.api_keys_integration, "list_user_api_keys", return_value=page) as listing,
        ):
            assert api_key_service.list_api_keys_of_user(7, params, mock_db) is page

        listing.assert_called_once_with(7, params, mock_db)


class TestRevokeOne:
    def _revoke(self, mock_db):
        api_key_service.revoke_api_key_of_user("key-1", 7, 1, "sid", _STEP_UP, MagicMock(), mock_db)

    def test_the_admins_step_up_is_verified_for_the_admin_action_before_the_key_is_revoked(self, mock_db, published):
        calls = MagicMock()
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials", calls.verify),
            patch.object(api_key_service.api_keys_integration, "revoke_api_key", calls.revoke),
        ):
            self._revoke(mock_db)

        assert [call[0] for call in calls.mock_calls] == ["verify", "revoke"]
        assert calls.verify.call_args.args[0] == 1
        assert (
            calls.verify.call_args.kwargs["action"] == identity_providers_constants.StepUpAction.ADMIN_API_KEYS_REVOKE
        )
        assert calls.verify.call_args.kwargs["session_id"] == "sid"
        calls.revoke.assert_called_once_with("key-1", 7, mock_db)

    def test_the_revocation_is_audited_without_a_secret_the_owner_is_notified_and_it_commits(self, mock_db, published):
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(api_key_service.api_keys_integration, "revoke_api_key"),
            jasil_testing.capture_audit() as audit,
        ):
            self._revoke(mock_db)

        row = audit.assert_audited(
            account_security_audit_actions.API_KEY_REVOKE.id,
            target_type="api_key",
            target_id="key-1",
            target_owner_id="7",
        )
        assert not row.details
        _assert_owner_notified(published)
        mock_db.commit.assert_called_once()

    def test_a_key_of_another_user_is_not_found_and_nothing_is_audited_or_sent(self, mock_db, published):
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(
                api_key_service.api_keys_integration, "revoke_api_key", side_effect=core_exceptions.NotFoundError("x")
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            self._revoke(mock_db)

        audit.assert_not_audited(account_security_audit_actions.API_KEY_REVOKE.id)
        published.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_refused_step_up_revokes_nothing(self, mock_db, published):
        with (
            patch.object(
                api_key_service.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.StepUpFailedError(),
            ),
            patch.object(api_key_service.api_keys_integration, "revoke_api_key") as revoke,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            self._revoke(mock_db)

        revoke.assert_not_called()
        published.assert_not_called()


class TestRevokeAll:
    def _revoke_all(self, mock_db):
        api_key_service.revoke_api_keys_of_user(7, 1, "sid", _STEP_UP, MagicMock(), mock_db)

    def test_the_count_is_audited_the_owner_is_notified_and_it_commits(self, mock_db, published):
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials") as verify,
            patch.object(api_key_service.users_integration, "require_user"),
            patch.object(api_key_service.api_keys_integration, "revoke_user_api_keys", return_value=3),
            jasil_testing.capture_audit() as audit,
        ):
            self._revoke_all(mock_db)

        assert verify.call_args.kwargs["action"] == identity_providers_constants.StepUpAction.ADMIN_API_KEYS_REVOKE
        row = audit.assert_audited(
            account_security_audit_actions.API_KEYS_REVOKE.id,
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert row.details == {"api_keys_revoked": 3}
        _assert_owner_notified(published)
        mock_db.commit.assert_called_once()

    def test_a_user_without_active_keys_is_audited_but_not_notified(self, mock_db, published):
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(api_key_service.users_integration, "require_user"),
            patch.object(api_key_service.api_keys_integration, "revoke_user_api_keys", return_value=0),
            jasil_testing.capture_audit() as audit,
        ):
            self._revoke_all(mock_db)

        assert audit.assert_audited(account_security_audit_actions.API_KEYS_REVOKE.id).details == {
            "api_keys_revoked": 0
        }
        published.assert_not_called()

    def test_a_missing_user_is_not_found_and_revokes_nothing(self, mock_db, published):
        with (
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(
                api_key_service.users_integration, "require_user", side_effect=core_exceptions.NotFoundError("x")
            ),
            patch.object(api_key_service.api_keys_integration, "revoke_user_api_keys") as revoke,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            self._revoke_all(mock_db)

        revoke.assert_not_called()

    def test_a_refused_step_up_revokes_nothing(self, mock_db, published):
        with (
            patch.object(
                api_key_service.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.StepUpFailedError(),
            ),
            patch.object(api_key_service.api_keys_integration, "revoke_user_api_keys") as revoke,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            self._revoke_all(mock_db)

        revoke.assert_not_called()


_HEADERS = {"Authorization": "Bearer mock_token"}
_BODY = {"step_up": {"current_password": "pw"}}
_SERVICE = "modules.auth.account_security.admin_api_keys_router.api_key_service"


class TestRoutes:
    def test_the_list_answers_a_page(self, fast_api_client):
        with patch(
            f"{_SERVICE}.list_api_keys_of_user", return_value=api_keys_schema.UserApiKeyPage.build([], 0, 1, 25)
        ):
            response = fast_api_client.get("/users/7/api-keys", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_revoking_one_answers_204_and_names_the_key_user_and_admin(self, fast_api_client):
        with patch(f"{_SERVICE}.revoke_api_key_of_user") as revoke:
            response = fast_api_client.post("/users/7/api-keys/key-1/revoke", json=_BODY, headers=_HEADERS)

        assert response.status_code == 204
        assert revoke.call_args.args[:2] == ("key-1", 7)

    def test_a_key_of_another_user_is_404(self, fast_api_client):
        with patch(f"{_SERVICE}.revoke_api_key_of_user", side_effect=core_exceptions.NotFoundError("x")):
            response = fast_api_client.post("/users/7/api-keys/key-1/revoke", json=_BODY, headers=_HEADERS)

        assert response.status_code == 404

    def test_revoking_all_answers_204(self, fast_api_client):
        with patch(f"{_SERVICE}.revoke_api_keys_of_user") as revoke:
            response = fast_api_client.post("/users/7/api-keys/revoke", json=_BODY, headers=_HEADERS)

        assert response.status_code == 204
        assert revoke.call_args.args[0] == 7

    @pytest.mark.parametrize("path", ["/users/7/api-keys/key-1/revoke", "/users/7/api-keys/revoke"])
    def test_a_body_without_step_up_is_refused(self, fast_api_client, path):
        assert fast_api_client.post(path, json={}, headers=_HEADERS).status_code == 422
