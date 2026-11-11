"""An administrator's role change, deactivation or promotion and an account deletion request stage the notice events
in the transaction that commits the change."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.integration_service as account_security_integration
import modules.users.users.deletion_job_service as job_service
import modules.users.users.deletion_state_store as deletion_state_store
import modules.users.users.event_publishers as users_event_publishers
import modules.users.users.events as users_events
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_SERVICE = "modules.users.users.service"
_JOBS = "modules.users.users.deletion_job_service"
_Change = account_security_events.AccountSecurityChange


def _user(user_id=1, **overrides) -> users_schema.UserRead:
    fields = {
        "id": user_id,
        "name": "User",
        "username": f"user{user_id}",
        "email": f"user{user_id}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UserRead(**fields)


@pytest.fixture
def staged():
    """Record what an edit stages, in order, together with the commit."""
    calls = []
    with (
        patch(f"{_SERVICE}.account_security_integration.stage_account_change_notice") as notice,
        patch(f"{_SERVICE}.users_event_publishers.publish_admin_promoted") as promoted,
        patch(f"{_SERVICE}.account_security_integration.verify_step_up"),
        patch(f"{_SERVICE}.account_security_integration.delete_all_user_sessions"),
        patch(f"{_SERVICE}.sign_up_tokens_integration") as sign_up,
        patch(f"{_SERVICE}.server_settings_integration"),
        patch(f"{_SERVICE}.mfa_integration") as mfa,
        patch(f"{_SERVICE}.identity_provider_links_integration") as links,
        patch(f"{_SERVICE}.users_crud") as crud,
    ):
        sign_up.get_pending_email_changes.return_value = {}
        mfa.get_mfa_enabled_for_users.return_value = {}
        links.get_identity_link_counts_for_users.return_value = {}
        notice.side_effect = lambda *a, **k: calls.append(("notice", a[1], k))
        promoted.side_effect = lambda *a, **k: calls.append(("promoted", a[0], a[1]))
        crud.lock_active_admin_ids.return_value = [1, 2, 3]
        yield SimpleCalls(calls, crud)


class SimpleCalls:
    def __init__(self, calls, crud):
        self.calls = calls
        self.crud = crud

    def edit(self, mock_db, before, after, *, actor_id=9, admins=()):
        self.crud.get_user_by_id.return_value = before
        self.crud.update_user.return_value = after
        self.crud.get_users_admin.return_value = list(admins)
        mock_db.commit.side_effect = lambda: self.calls.append(("commit",))
        users_service.edit_user(
            before.id,
            users_schema.UserEdit.from_read(after),
            None,
            actor_id,
            "sid",
            MagicMock(),
            mock_db,
            if_match="*",
        )
        return self.calls


class TestRoleChange:
    def test_the_user_is_told_their_new_role_before_the_commit(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1), _user(1, access_type="admin"))

        assert ("notice", _Change.ROLE_CHANGED_BY_ADMIN, {"access_type": "admin"}) in calls
        assert calls.index(("notice", _Change.ROLE_CHANGED_BY_ADMIN, {"access_type": "admin"})) < calls.index(
            ("commit",)
        )

    def test_a_demotion_tells_the_user_and_no_administrator(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1, access_type="admin"), _user(1, access_type="regular"), admins=[_user(2)])

        assert ("notice", _Change.ROLE_CHANGED_BY_ADMIN, {"access_type": "regular"}) in calls
        assert not [call for call in calls if call[0] == "promoted"]

    def test_an_edit_that_keeps_the_role_tells_nobody(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1), _user(1, name="Renamed"))

        assert calls == [("commit",)]

    def test_an_administrator_editing_their_own_role_is_not_told(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(9, access_type="admin"), _user(9, access_type="regular"), actor_id=9)

        assert calls == [("commit",)]

    def test_a_user_the_edit_also_deactivates_is_told_of_the_deactivation_only(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1), _user(1, access_type="admin", active=False))

        assert [call for call in calls if call[0] == "notice"] == [("notice", _Change.ACCOUNT_DEACTIVATED_BY_ADMIN, {})]


class TestPromotion:
    def test_each_other_active_administrator_is_told_and_nobody_else(self, mock_db, staged):
        admins = [
            _user(1, access_type="admin"),
            _user(2, access_type="admin"),
            _user(3, access_type="admin", active=False),
            _user(4, access_type="admin"),
        ]

        calls = staged.edit(mock_db, _user(1), _user(1, access_type="admin"), admins=admins)

        assert [call for call in calls if call[0] == "promoted"] == [("promoted", 1, 2), ("promoted", 1, 4)]

    def test_a_promotion_is_staged_before_the_commit(self, mock_db, staged):
        calls = staged.edit(
            mock_db,
            _user(1),
            _user(1, access_type="admin"),
            admins=[_user(1, access_type="admin"), _user(2, access_type="admin")],
        )

        assert calls.index(("promoted", 1, 2)) < calls.index(("commit",))


class TestDeactivation:
    def test_the_user_is_told_before_the_commit(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1), _user(1, active=False))

        assert calls == [("notice", _Change.ACCOUNT_DEACTIVATED_BY_ADMIN, {}), ("commit",)]

    def test_a_reactivation_tells_nobody(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(1, active=False), _user(1))

        assert calls == [("commit",)]

    def test_an_administrator_deactivating_themselves_is_not_told(self, mock_db, staged):
        calls = staged.edit(mock_db, _user(9), _user(9, active=False), actor_id=9)

        assert calls == [("commit",)]


class TestDeletionRequest:
    def test_request_deletion_stages_no_account_security_notice(self, mock_db):
        states = deletion_state_store.UserDeletionStateStore(MemoryState())
        with (
            patch(f"{_JOBS}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_JOBS}.account_security_integration") as account_security,
            patch(f"{_JOBS}.sign_up_tokens_integration"),
            patch(f"{_JOBS}.users_service"),
            patch(f"{_JOBS}.users_crud"),
            patch(f"{_JOBS}.security_generation_integration"),
            patch(f"{_JOBS}._deletion_pool"),
        ):
            job_service.request_deletion(4, 4, states, MagicMock(), MagicMock(), mock_db, if_match="*")

        account_security.stage_account_change_notice.assert_not_called()


class TestStagingTheNotice:
    def test_the_integration_stages_a_security_change_event_with_the_access_type(self, mock_db):
        with patch.object(account_security_event_publishers, "publish_account_security_changed") as publish:
            account_security_integration.stage_account_change_notice(
                4, _Change.ROLE_CHANGED_BY_ADMIN, mock_db, access_type="admin"
            )

        publish.assert_called_once_with(4, _Change.ROLE_CHANGED_BY_ADMIN, mock_db, access_type="admin")

    def test_the_event_carries_the_access_type_and_no_secret(self, mock_db):
        with patch("modules.auth.account_security.event_publishers.platform_publisher.publish_on_commit") as publish:
            account_security_event_publishers.publish_account_security_changed(
                4, _Change.ROLE_CHANGED_BY_ADMIN, mock_db, access_type="admin"
            )

        _, payload = publish.call_args.args
        assert payload == {"user_id": 4, "change": "role_changed_by_admin", "idp_id": None, "access_type": "admin"}

    def test_the_promotion_event_names_the_user_and_the_recipient_only(self, mock_db):
        with patch("modules.users.users.event_publishers.platform_publisher.publish_on_commit") as publish:
            users_event_publishers.publish_admin_promoted(3, 8, mock_db)

        event_type, payload = publish.call_args.args
        assert event_type == users_events.USERS_ADMIN_PROMOTED
        assert payload == {"user_id": 3, "admin_user_id": 8}
        assert publish.call_args.kwargs["db"] is mock_db
        assert account_security_service  # the service module the integration delegates to is importable
