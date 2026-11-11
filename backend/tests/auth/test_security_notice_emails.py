"""Tests for the emails of a backup code use, a refresh-token reuse, an administrator's change to an account and an
administrator promotion."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import pytest

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.email_messages as email_messages
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.subscribers as account_security_subscribers
import modules.auth.authentication.events as authentication_events
import modules.auth.mfa_backup_codes.events as backup_codes_events
import modules.users.users.events as users_events

HOST = "https://endurain.example.com"
SERVICE = "modules.auth.account_security.account_security_service"
SUBSCRIBERS = "modules.auth.account_security.subscribers"
_Change = account_security_events.AccountSecurityChange


def _user(active=True, user_id=4, email="alice@example.test", name="Alice"):
    user = MagicMock()
    user.id = user_id
    user.name = name
    user.username = name.lower()
    user.email = email
    user.preferred_language = "en"
    user.active = active
    return user


class TestBackupCodeUsedEmail:
    def test_says_how_many_codes_are_left(self):
        subject, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "backup_code_used", None, HOST, "en", backup_codes_remaining=3
        )

        assert "backup code" in subject.lower()
        assert "3" in html_body
        assert "3" in text_body

    def test_says_when_none_are_left(self):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "backup_code_used", None, HOST, "en", backup_codes_remaining=0
        )

        assert "no unused backup codes" in html_body
        assert "no unused backup codes" in text_body

    def test_warns_that_someone_may_know_the_password(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "Alice", "backup_code_used", None, HOST, "en", backup_codes_remaining=3
        )

        assert "Change your password" in html_body


class TestUsernameChangedEmail:
    def test_says_the_username_changed_and_holds_no_username(self):
        subject, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "username_changed", None, HOST, "en"
        )

        assert "username" in subject.lower()
        assert "username" in html_body.lower()
        assert "username" in text_body.lower()

    def test_advises_changing_the_password(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "Alice", "username_changed", None, HOST, "en"
        )

        assert "reset your password" in html_body


class TestRefreshReuseEmail:
    def test_says_a_session_was_ended_and_what_to_do(self):
        subject, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "refresh_token_reuse_detected", None, HOST, "en"
        )

        assert "session" in subject.lower()
        assert "ended" in html_body
        assert "ended" in text_body
        assert "Change your password" in html_body


class TestAdministratorChangeEmails:
    @pytest.mark.parametrize("access_type, word", [("admin", "administrator"), ("regular", "regular user")])
    def test_a_role_change_names_the_new_access(self, access_type, word):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "role_changed_by_admin", None, HOST, "en", access_type=access_type
        )

        assert f"to {word}" in html_body
        assert f"to {word}" in text_body
        assert "contact your Endurain administrator" in html_body

    def test_a_deactivation_says_the_account_cannot_sign_in(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "Alice", "account_deactivated_by_admin", None, HOST, "en"
        )

        assert "deactivated" in html_body
        assert "contact your Endurain administrator" in html_body

    def test_a_deletion_request_says_what_really_happens(self):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "account_deletion_requested", None, HOST, "en"
        )

        for body in (html_body, text_body):
            assert "signed out" in body
            assert "deactivated" in body
            assert "erased" in body
            assert "reactivat" in body
            assert "cannot be undone" not in body


class TestAdminPromotedEmail:
    def test_names_the_promoted_user_to_the_admin(self):
        subject, html_body, text_body = email_messages.get_admin_promoted_email("Bob", "Ada <b>", "ada", HOST, "en")

        assert "administrator" in subject
        assert "Hi Bob," in html_body
        assert "Ada &lt;b&gt;" in html_body
        assert "Ada <b>" not in html_body
        assert "Ada <b> (ada)" in text_body


class TestPrepareForInactiveRecipients:
    def test_the_owner_of_a_deactivated_account_is_still_told(self, mock_db):
        change = _Change.ACCOUNT_DEACTIVATED_BY_ADMIN
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)),
            patch(f"{SERVICE}.users_integration.is_deactivated", return_value=True),
        ):
            message = account_security_service.prepare_security_change_email(4, change.value, None, HOST, mock_db)

        assert message is not None
        assert message[0] == "alice@example.test"

    def test_an_unverified_sign_up_is_not_told_of_a_deactivation(self, mock_db):
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)),
            patch(f"{SERVICE}.users_integration.is_deactivated", return_value=False),
        ):
            assert (
                account_security_service.prepare_security_change_email(
                    4, _Change.ACCOUNT_DEACTIVATED_BY_ADMIN.value, None, HOST, mock_db
                )
                is None
            )

    def test_another_change_still_needs_an_active_account(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)):
            assert (
                account_security_service.prepare_security_change_email(
                    4, _Change.BACKUP_CODE_USED.value, None, HOST, mock_db, backup_codes_remaining=2
                )
                is None
            )

    def test_the_extras_reach_the_message(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=_user()):
            message = account_security_service.prepare_security_change_email(
                4, _Change.BACKUP_CODE_USED.value, None, HOST, mock_db, backup_codes_remaining=7
            )

        assert message is not None
        assert "7" in message[2]


class TestPrepareAccountDeletionEmail:
    def test_goes_to_the_address_on_the_row_even_though_the_account_is_inactive(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)):
            message = account_security_service.prepare_account_deletion_email(4, HOST, mock_db)

        assert message is not None
        assert message[0] == "alice@example.test"
        assert "erased" in message[2]

    def test_a_missing_user_sends_nothing(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=None):
            assert account_security_service.prepare_account_deletion_email(4, HOST, mock_db) is None

    def test_an_event_for_a_deletion_is_not_prepared_as_a_security_change_for_an_inactive_account(self, mock_db):
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)),
            patch(f"{SERVICE}.users_integration.is_deactivated", return_value=True),
        ):
            assert (
                account_security_service.prepare_security_change_email(
                    4, _Change.ACCOUNT_DELETION_REQUESTED.value, None, HOST, mock_db
                )
                is None
            )


class TestPrepareAdminPromotedEmail:
    def test_goes_to_the_admin_and_names_the_promoted_user(self, mock_db):
        admin = _user(user_id=8, email="bob@example.test", name="Bob")
        promoted = _user(user_id=3, email="ada@example.test", name="Ada")
        with patch(
            f"{SERVICE}.users_integration.get_user", side_effect=lambda user_id, db: {8: admin, 3: promoted}[user_id]
        ):
            message = account_security_service.prepare_admin_promoted_email(3, 8, HOST, mock_db)

        assert message is not None
        assert message[0] == "bob@example.test"
        assert "Ada" in message[2]
        assert "ada@example.test" not in message[2] + message[3]

    @pytest.mark.parametrize("missing", [3, 8])
    def test_a_missing_user_sends_nothing(self, missing, mock_db):
        users = {8: _user(user_id=8), 3: _user(user_id=3)}
        users[missing] = None
        with patch(f"{SERVICE}.users_integration.get_user", side_effect=lambda user_id, db: users[user_id]):
            assert account_security_service.prepare_admin_promoted_email(3, 8, HOST, mock_db) is None

    def test_an_inactive_admin_is_not_told(self, mock_db):
        users = {8: _user(user_id=8, active=False), 3: _user(user_id=3)}
        with patch(f"{SERVICE}.users_integration.get_user", side_effect=lambda user_id, db: users[user_id]):
            assert account_security_service.prepare_admin_promoted_email(3, 8, HOST, mock_db) is None


def _handle(handler, event, prepare_target):
    with (
        patch(f"{SUBSCRIBERS}.core_mail.send_email", return_value=True) as send_email,
        patch(f"{SUBSCRIBERS}.account_security_service.{prepare_target}") as prepare,
        patch(f"{SUBSCRIBERS}.platform_runtime.get_active_platform") as get_platform,
        patch(f"{SUBSCRIBERS}.core_database.SessionLocal") as session_local,
    ):
        prepare.return_value = ("alice@example.test", "subject", "html", "text")
        handler(event)
    return prepare, send_email, get_platform, session_local


class TestHandlers:
    def test_the_backup_code_email_carries_the_codes_left(self):
        event = platform_events.new_event(
            backup_codes_events.BACKUP_CODE_USED, {"user_id": 4, "backup_codes_remaining": 2}, source="test"
        )

        prepare, send_email, get_platform, session_local = _handle(
            account_security_subscribers.send_backup_code_used_email_for_event, event, "prepare_security_change_email"
        )

        db = session_local.return_value.__enter__.return_value
        prepare.assert_called_once_with(
            4,
            _Change.BACKUP_CODE_USED.value,
            None,
            account_security_subscribers.core_config.settings.ENDURAIN_HOST,
            db,
            backup_codes_remaining=2,
        )
        send_email.assert_called_once_with(
            get_platform.return_value.mail, "alice@example.test", "subject", "html", "text"
        )

    def test_the_refresh_reuse_email_goes_to_the_session_owner(self):
        event = platform_events.new_event(authentication_events.REFRESH_REUSE_DETECTED, {"user_id": 4}, source="test")

        prepare, send_email, _, session_local = _handle(
            account_security_subscribers.send_refresh_reuse_email_for_event, event, "prepare_security_change_email"
        )

        db = session_local.return_value.__enter__.return_value
        prepare.assert_called_once_with(
            4,
            _Change.REFRESH_TOKEN_REUSE_DETECTED.value,
            None,
            account_security_subscribers.core_config.settings.ENDURAIN_HOST,
            db,
        )
        send_email.assert_called_once()

    def test_the_security_changed_email_carries_the_new_access_type(self):
        event = platform_events.new_event(
            account_security_events.ACCOUNT_SECURITY_CHANGED,
            {"user_id": 4, "change": "role_changed_by_admin", "access_type": "admin"},
            source="test",
        )

        prepare, _, _, session_local = _handle(
            account_security_subscribers.send_security_changed_email_for_event, event, "prepare_security_change_email"
        )

        db = session_local.return_value.__enter__.return_value
        prepare.assert_called_once_with(
            4,
            "role_changed_by_admin",
            None,
            account_security_subscribers.core_config.settings.ENDURAIN_HOST,
            db,
            access_type="admin",
        )

    def test_the_admin_promoted_email_goes_to_the_admin_the_event_names(self):
        event = platform_events.new_event(
            users_events.USERS_ADMIN_PROMOTED, {"user_id": 3, "admin_user_id": 8}, source="test"
        )

        prepare, send_email, _, session_local = _handle(
            account_security_subscribers.send_admin_promoted_email_for_event, event, "prepare_admin_promoted_email"
        )

        db = session_local.return_value.__enter__.return_value
        prepare.assert_called_once_with(3, 8, account_security_subscribers.core_config.settings.ENDURAIN_HOST, db)
        send_email.assert_called_once()

    def test_each_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        account_security_subscribers.register_bus_subscribers(events)
        account_security_subscribers.register_durable_handlers(registry)

        for name, subscriber_id in (
            (backup_codes_events.BACKUP_CODE_USED, "auth.send_backup_code_used_email"),
            (authentication_events.REFRESH_REUSE_DETECTED, "auth.send_refresh_reuse_email"),
            (users_events.USERS_ADMIN_PROMOTED, "users.send_admin_promoted_email"),
        ):
            assert any(c.args[0] == name for c in events.subscribe.call_args_list)
            assert any(c.args[:2] == (name, subscriber_id) for c in registry.register.call_args_list)
