"""The dedicated username change: schema, step-up, conflict, no-op, session revocation, audit and notice."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from pydantic import ValidationError

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.service as profile_service

_SERVICE = "modules.users.users_profile.service"
_USERS = "modules.users.users.service"
_TARGET = {"target_type": "user", "target_id": "7", "target_owner_id": "7"}


def _change(username="New.Name", *, revoke=True) -> users_schema.UsernameChange:
    return users_schema.UsernameChange(
        username=username, step_up={"current_password": "pw"}, revoke_other_sessions=revoke
    )


class TestUsernameChangeSchema:
    def test_revokes_other_sessions_by_default(self):
        assert users_schema.UsernameChange(username="ada", step_up={"current_password": "pw"}).revoke_other_sessions

    @pytest.mark.parametrize("username", ["", "has space", "a" * 251, "bad/char"])
    def test_refuses_what_the_profile_edit_used_to_refuse(self, username):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username=username, step_up={"current_password": "pw"})

    def test_requires_step_up(self):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username="ada")

    def test_refuses_unknown_fields(self):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username="ada", step_up={"current_password": "pw"}, email="a@b.co")

    def test_the_profile_update_no_longer_takes_a_username(self):
        with pytest.raises(ValidationError):
            users_schema.ProfileUpdate(username="ada")


class TestStageUsernameChange:
    def _stage(self, mock_db, new, *, current="old"):
        with (
            patch(f"{_USERS}.users_crud") as crud,
            patch(f"{_USERS}.security_generation_integration") as generation,
        ):
            crud.get_user_by_id.return_value = users_schema.UserRead(
                id=7, name="N", username=current, email="a@example.com", active=True, access_type="regular"
            )
            result = users_service.stage_username_change(7, new, mock_db)
        return result, crud, generation

    def test_stores_the_lower_cased_username(self, mock_db):
        changed, crud, _ = self._stage(mock_db, "New.Name")

        assert changed is True
        assert crud.update_user.call_args.args[:2] == (7, {"username": "new.name"})

    def test_the_same_username_in_any_case_changes_nothing(self, mock_db):
        changed, crud, _ = self._stage(mock_db, "OLD")

        assert changed is False
        crud.update_user.assert_not_called()

    def test_does_not_bump_the_security_generation(self, mock_db):
        _, _, generation = self._stage(mock_db, "new")

        generation.stage_bump.assert_not_called()


class TestChangeUsername:
    def _run(self, mock_db, change, *, staged=True, side_effect=None):
        with (
            patch(f"{_SERVICE}.account_security_integration") as security,
            patch(f"{_SERVICE}.users_integration") as users,
            patch(f"{_SERVICE}.get_profile") as get_profile,
        ):
            users.stage_username_change.return_value = staged
            users.stage_username_change.side_effect = side_effect
            result = profile_service.change_username(7, change, "sid", MagicMock(), mock_db)
        return result, security, users, get_profile

    def test_verifies_step_up_for_the_username_change_action(self, mock_db):
        _, security, _, _ = self._run(mock_db, _change())

        args = security.verify_step_up.call_args.args
        assert args[1:3] == (7, "sid")
        assert args[3] == identity_providers_constants.StepUpAction.USERNAME_CHANGE

    def test_stages_the_username_and_commits_once(self, mock_db):
        _, _, users, get_profile = self._run(mock_db, _change())

        assert users.stage_username_change.call_args.args[:2] == (7, "New.Name")
        mock_db.commit.assert_called_once()
        get_profile.assert_called_once_with(7, mock_db)

    def test_a_failed_step_up_changes_nothing(self, mock_db):
        with (
            patch(f"{_SERVICE}.account_security_integration") as security,
            patch(f"{_SERVICE}.users_integration") as users,
        ):
            security.verify_step_up.side_effect = core_exceptions.StepUpFailedError("no")
            with pytest.raises(core_exceptions.StepUpFailedError):
                profile_service.change_username(7, _change(), "sid", MagicMock(), mock_db)

        users.stage_username_change.assert_not_called()

    def test_a_taken_username_rolls_back_and_raises_a_conflict(self, mock_db):
        with pytest.raises(core_exceptions.ConflictError):
            self._run(mock_db, _change(), side_effect=core_exceptions.ConflictError("taken"))

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_resubmitting_the_current_username_is_a_no_op(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            _, security, _, _ = self._run(mock_db, _change(), staged=False)

        audit.assert_not_audited(profile_audit_actions.USERNAME_CHANGE.id)
        security.stage_account_change_notice.assert_not_called()
        security.delete_other_user_sessions.assert_not_called()

    def test_revokes_other_sessions_when_asked(self, mock_db):
        _, security, _, _ = self._run(mock_db, _change(revoke=True))

        security.delete_other_user_sessions.assert_called_once_with(7, "sid", mock_db)

    def test_keeps_other_sessions_when_the_client_opts_out(self, mock_db):
        _, security, _, _ = self._run(mock_db, _change(revoke=False))

        security.delete_other_user_sessions.assert_not_called()

    def test_tells_the_account_owner(self, mock_db):
        _, security, _, _ = self._run(mock_db, _change())

        security.stage_account_change_notice.assert_called_once_with(
            7, account_security_events.AccountSecurityChange.USERNAME_CHANGED, mock_db
        )

    @pytest.mark.parametrize("revoke", [True, False])
    def test_audits_the_change_without_the_username(self, mock_db, revoke):
        with jasil_testing.capture_audit() as audit:
            self._run(mock_db, _change(revoke=revoke))

        entry = audit.assert_audited(profile_audit_actions.USERNAME_CHANGE.id, **_TARGET)
        assert entry.details == {"other_sessions_revoked": revoke}
