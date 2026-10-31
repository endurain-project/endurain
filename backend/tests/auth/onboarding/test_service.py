"""Tests for the first-run onboarding workflow."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.service as onboarding_service
import modules.auth.onboarding.token_store as onboarding_token_store

_USERS = "modules.auth.onboarding.service.users_integration"


@pytest.fixture
def store() -> onboarding_token_store.OnboardingTokenStore:
    return onboarding_token_store.OnboardingTokenStore(MemoryState())


def _request(token: str) -> onboarding_schema.OnboardingCreate:
    return onboarding_schema.OnboardingCreate(
        token=token, name="Owner", username="owner", email="owner@example.com", password="SecurePass1!"
    )


class TestStatus:
    @pytest.mark.parametrize(("exists", "required"), [(False, True), (True, False)])
    @patch(_USERS)
    def test_onboarding_is_required_exactly_while_no_account_exists(self, users, exists, required, mock_db):
        users.any_user_exists.return_value = exists

        assert onboarding_service.get_onboarding_status(mock_db).onboarding_required is required


class TestCompleteOnboarding:
    @patch(_USERS)
    def test_an_existing_account_is_refused_before_the_token_or_the_password_is_touched(self, users, store, mock_db):
        users.any_user_exists.return_value = True
        token = store.issue()

        with pytest.raises(core_exceptions.ConflictError):
            onboarding_service.complete_onboarding(_request(token), store, mock_db)

        users.stage_first_admin.assert_not_called()
        assert store.exists(token), "a refused request must not consume the token"
        mock_db.commit.assert_not_called()

    @patch(_USERS)
    def test_an_account_check_precedes_the_token_check(self, users, mock_db):
        users.any_user_exists.return_value = True
        store = MagicMock()

        with pytest.raises(core_exceptions.ConflictError):
            onboarding_service.complete_onboarding(_request("t"), store, mock_db)

        store.exists.assert_not_called()

    @patch(_USERS)
    def test_a_bad_token_is_refused_without_staging_or_hashing(self, users, store, mock_db):
        users.any_user_exists.return_value = False

        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired setup token"):
            onboarding_service.complete_onboarding(_request("bogus"), store, mock_db)

        users.stage_first_admin.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(_USERS)
    def test_a_weak_password_is_unprocessable_and_keeps_the_token(self, users, store, mock_db):
        users.any_user_exists.return_value = False
        users.stage_first_admin.side_effect = core_exceptions.InvalidInputError("Password is too short")
        token = store.issue()

        with pytest.raises(credentials_contracts.PasswordPolicyError) as exc_info:
            onboarding_service.complete_onboarding(_request(token), store, mock_db)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "Password is too short"
        assert store.exists(token)
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch(_USERS)
    def test_losing_the_race_for_an_account_rolls_back_and_conflicts(self, users, store, mock_db):
        users.any_user_exists.return_value = False
        users.stage_first_admin.side_effect = core_exceptions.ConflictError("An account already exists")
        token = store.issue()

        with pytest.raises(core_exceptions.ConflictError):
            onboarding_service.complete_onboarding(_request(token), store, mock_db)

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
        assert store.exists(token)

    @patch(_USERS)
    def test_losing_the_race_for_the_token_rolls_back_and_commits_nothing(self, users, mock_db):
        users.any_user_exists.return_value = False
        store = MagicMock()
        store.exists.return_value = True
        store.claim.return_value = False

        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired setup token"):
            onboarding_service.complete_onboarding(_request("t"), store, mock_db)

        users.stage_first_admin.assert_called_once()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch(_USERS)
    def test_success_stages_claims_commits_in_that_order_and_consumes_the_token(self, users, store, mock_db):
        users.any_user_exists.return_value = False
        users.stage_first_admin.return_value = MagicMock(id=1)
        token = store.issue()
        request = _request(token)
        order = MagicMock()
        order.attach_mock(users.stage_first_admin, "stage")
        order.attach_mock(mock_db.commit, "commit")

        created = onboarding_service.complete_onboarding(request, store, mock_db)

        assert created is users.stage_first_admin.return_value
        users.stage_first_admin.assert_called_once_with(request, mock_db)
        assert [call[0] for call in order.mock_calls] == ["stage", "commit"]
        assert not store.exists(token)
        mock_db.rollback.assert_not_called()

    @patch(_USERS)
    def test_a_token_cannot_be_reused_after_a_success(self, users, store, mock_db):
        users.any_user_exists.return_value = False
        users.stage_first_admin.return_value = MagicMock(id=1)
        token = store.issue()
        onboarding_service.complete_onboarding(_request(token), store, mock_db)

        with pytest.raises(core_exceptions.InvalidInputError):
            onboarding_service.complete_onboarding(_request(token), store, mock_db)

    @patch(_USERS)
    def test_an_unavailable_token_store_commits_nothing(self, users, mock_db):
        users.any_user_exists.return_value = False
        store = MagicMock()
        store.exists.side_effect = core_exceptions.ServiceUnavailableError()

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            onboarding_service.complete_onboarding(_request("t"), store, mock_db)

        mock_db.commit.assert_not_called()


class TestRequestShape:
    @pytest.mark.parametrize("field", ["access_type", "active", "email_verified", "pending_admin_approval", "id"])
    def test_a_field_that_decides_the_account_is_rejected(self, field):
        with pytest.raises(ValueError):
            onboarding_schema.OnboardingCreate(
                token="t",
                name="Owner",
                username="owner",
                email="owner@example.com",
                password="SecurePass1!",
                **{field: "admin"},
            )
