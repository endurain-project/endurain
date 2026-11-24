"""The owner of an account is emailed about the security events that concern it, through the real subscribers.

An event is published as production publishes it (staged on a session that commits, or on its own); the subscribers
read the user back, build the message in the user's language and hand it to the mail provider, whose recording
backend stands in for SMTP.
"""

import uuid
from datetime import UTC, datetime

import jasil.events as platform_events
import jasil.jobs.registry as jobs_registry
import jasil.providers as platform_providers
import jasil.runtime as jasil_runtime
import jasil.testing as jasil_testing
import pytest

import core.config as core_config
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.event_publishers as account_security_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.subscriber_registry as account_security_subscriber_registry
import modules.auth.account_security.subscribers as account_security_subscribers
import modules.auth.authentication.event_publishers as authentication_publishers
import modules.auth.identity_providers.event_publishers as idp_publishers
import modules.auth.known_devices.event_publishers as known_devices_publishers
import modules.auth.known_devices.events as known_devices_events
import modules.auth.mfa_backup_codes.event_publishers as backup_code_publishers
import modules.auth.password_reset_tokens.event_publishers as password_reset_publishers
import modules.users.users.event_publishers as users_publishers
from tests._factories.account_security import deliver_notices, outbox, sent_to
from tests._factories.identity_links import make_identity_provider
from tests._factories.users import make_admin, make_sign_up, make_user

_Change = account_security_events.AccountSecurityChange


@pytest.fixture
def user(committed_sessions):
    deliver_notices()
    with committed_sessions() as db:
        created = make_user(db, name="Alice Example")
        db.commit()
    return created


def _announce(committed_sessions, publish):
    """Run a publisher the way its producer does, then commit so a staged event is delivered."""
    with committed_sessions() as db:
        publish(db)
        db.commit()


class TestSecurityChanges:
    @pytest.mark.parametrize("change", [change for change in _Change if change is not _Change.ROLE_CHANGED_BY_ADMIN])
    def test_each_change_sends_the_owner_one_message_in_their_own_name(self, committed_sessions, user, change):
        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(user.id, change, db),
        )

        (message,) = sent_to(user.email)
        assert message.subject.startswith("Endurain - ")
        assert message.to == [user.email]
        assert "Hi Alice Example," in message.text
        assert "account_security_changed." not in message.subject + message.text

    def test_every_change_has_a_message_of_its_own(self, committed_sessions, user):
        for change in _Change:
            _announce(
                committed_sessions,
                lambda db, change=change: account_security_publishers.publish_account_security_changed(
                    user.id, change, db, access_type="admin"
                ),
            )

        subjects = [message.subject for message in sent_to(user.email)]
        assert len(subjects) == len(set(subjects)) == len(list(_Change))

    def test_a_role_change_names_the_new_access(self, committed_sessions, user):
        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                user.id, _Change.ROLE_CHANGED_BY_ADMIN, db, access_type="admin"
            ),
        )

        (message,) = sent_to(user.email)
        assert "to administrator" in message.text

    def test_an_unlink_names_the_provider(self, committed_sessions, user):
        with committed_sessions() as db:
            idp_id = make_identity_provider(db, "authentik")
            db.commit()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                user.id, _Change.IDENTITY_PROVIDER_UNLINKED, db, idp_id=idp_id
            ),
        )

        (message,) = sent_to(user.email)
        assert "Provider authentik" in message.text

    def test_a_deleted_provider_leaves_the_name_out(self, committed_sessions, user):
        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                user.id, _Change.IDENTITY_PROVIDER_UNLINKED, db, idp_id=uuid.uuid4()
            ),
        )

        (message,) = sent_to(user.email)
        assert "None" not in message.text

    def test_the_message_follows_the_users_language(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            portuguese = make_user(db, preferred_language="pt-PT")
            db.commit()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                portuguese.id, _Change.PASSWORD_CHANGED, db
            ),
        )

        (message,) = sent_to(portuguese.email)
        assert message.subject != "Endurain - Your password was changed"

    def test_a_missing_user_is_sent_nothing(self, committed_sessions):
        deliver_notices()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                uuid.uuid4(), _Change.PASSWORD_CHANGED, db
            ),
        )

        assert outbox() == []

    def test_a_staged_event_is_sent_only_when_the_transaction_commits(self, committed_sessions, user):
        with committed_sessions() as db:
            account_security_publishers.publish_account_security_changed(user.id, _Change.MFA_ENABLED, db)
            db.rollback()

        assert sent_to(user.email) == []


class TestInactiveRecipients:
    def test_the_owner_of_a_deactivated_account_is_still_told_of_the_deactivation(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            deactivated = make_user(db, active=False)
            db.commit()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                deactivated.id, _Change.ACCOUNT_DEACTIVATED_BY_ADMIN, db
            ),
        )

        assert len(sent_to(deactivated.email)) == 1

    def test_an_unverified_sign_up_is_not_told_of_a_deactivation(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            sign_up = make_sign_up(db)
            db.commit()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                sign_up.id, _Change.ACCOUNT_DEACTIVATED_BY_ADMIN, db
            ),
        )

        assert sent_to(sign_up.email) == []

    def test_another_change_still_needs_an_active_account(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            deactivated = make_user(db, active=False)
            db.commit()

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(
                deactivated.id, _Change.PASSWORD_CHANGED, db
            ),
        )

        assert sent_to(deactivated.email) == []


class TestOtherEvents:
    def test_a_linked_provider_is_announced_with_its_name(self, committed_sessions, user):
        with committed_sessions() as db:
            idp_id = make_identity_provider(db, "keycloak")
            db.commit()

        _announce(committed_sessions, lambda db: idp_publishers.publish_idp_linked(user.id, idp_id, db))

        (message,) = sent_to(user.email)
        assert "Provider keycloak" in message.text

    def test_a_password_reset_is_announced(self, committed_sessions, user):
        _announce(
            committed_sessions, lambda db: password_reset_publishers.publish_password_reset_completed(user.id, db)
        )

        (message,) = sent_to(user.email)
        assert "password" in message.subject.lower()

    @pytest.mark.parametrize(
        ("publisher", "word"),
        [
            (authentication_publishers.publish_account_locked, "locked"),
            (authentication_publishers.publish_mfa_locked, "locked"),
            (account_security_publishers.publish_step_up_locked, "locked"),
            (account_security_publishers.publish_step_up_session_ended, "session"),
            (authentication_publishers.publish_refresh_reuse_detected, "session"),
        ],
        ids=["account-locked", "mfa-locked", "step-up-locked", "step-up-session-ended", "refresh-reuse"],
    )
    def test_a_lock_or_an_ended_session_is_announced(self, committed_sessions, user, publisher, word):
        _announce(committed_sessions, lambda db: publisher(user.id, db))

        (message,) = sent_to(user.email)
        assert word in message.subject.lower()

    def test_a_backup_code_use_says_how_many_are_left(self, committed_sessions, user):
        _announce(committed_sessions, lambda db: backup_code_publishers.publish_backup_code_used(user.id, 7, db))

        (message,) = sent_to(user.email)
        assert "7" in message.text

    def test_a_sign_in_from_a_new_device_names_the_device_and_the_time_in_the_users_zone(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            traveller = make_user(db, timezone="Asia/Tokyo")
            db.commit()
        signed_in_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

        _announce(
            committed_sessions,
            lambda db: known_devices_publishers.publish_new_device_sign_in(
                traveller.id,
                db,
                browser="Firefox",
                operating_system="Linux",
                device_type="PC",
                ip_address="203.0.113.9",
                method=known_devices_events.SignInMethod.PASSWORD,
                signed_in_at=signed_in_at,
            ),
        )

        (message,) = sent_to(traveller.email)
        assert all(part in message.text for part in ("Firefox", "Linux", "203.0.113.9", "21:00"))

    def test_a_promotion_goes_to_the_administrator_the_event_names(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            admin = make_admin(db)
            promoted = make_user(db, name="Ada Promoted")
            db.commit()

        _announce(committed_sessions, lambda db: users_publishers.publish_admin_promoted(promoted.id, admin.id, db))

        (message,) = sent_to(admin.email)
        assert "Ada Promoted" in message.text
        assert sent_to(promoted.email) == []

    def test_an_inactive_administrator_is_not_told_of_a_promotion(self, committed_sessions):
        deliver_notices()
        with committed_sessions() as db:
            admin = make_admin(db, active=False)
            promoted = make_user(db)
            db.commit()

        _announce(committed_sessions, lambda db: users_publishers.publish_admin_promoted(promoted.id, admin.id, db))

        assert outbox() == []


class TestAccountDeletionNotice:
    def test_it_goes_to_the_address_on_the_row_although_the_account_is_inactive(self, db):
        deactivated = make_user(db, active=False)

        message = account_security_service.prepare_account_deletion_email(
            deactivated.id, core_config.settings.ENDURAIN_HOST, db
        )

        assert message is not None
        assert message[0] == deactivated.email

    def test_a_missing_user_is_sent_nothing(self, db):
        assert (
            account_security_service.prepare_account_deletion_email(
                uuid.uuid4(), core_config.settings.ENDURAIN_HOST, db
            )
            is None
        )


class TestDeliveryFailure:
    def _event(self, user_id: uuid.UUID) -> platform_events.Event:
        payload = account_security_events.AccountSecurityChangedPayload(user_id=user_id, change=_Change.MFA_ENABLED)
        return platform_events.new_event(
            account_security_events.ACCOUNT_SECURITY_CHANGED, payload.model_dump(mode="json"), source="test"
        )

    def _refusing_mail(self, monkeypatch) -> None:
        def refuse(_message):
            raise platform_providers.MailError("refused", kind=platform_providers.MailFailure.OTHER)

        monkeypatch.setattr(jasil_testing.memory_mail(jasil_runtime.get_active_platform()), "send", refuse)

    def test_a_refusing_mail_server_fails_the_retryable_handler(self, monkeypatch, user):
        self._refusing_mail(monkeypatch)

        with pytest.raises(platform_providers.MailError):
            account_security_subscribers.send_security_changed_email_for_event(self._event(user.id))

    def test_a_refusing_mail_server_does_not_fail_the_request_that_published_the_event(
        self, monkeypatch, committed_sessions, user
    ):
        self._refusing_mail(monkeypatch)

        _announce(
            committed_sessions,
            lambda db: account_security_publishers.publish_account_security_changed(user.id, _Change.MFA_ENABLED, db),
        )

        assert outbox() == []


class TestRegistration:
    def test_each_event_has_a_retryable_handler_under_its_own_id(self):
        registry = jobs_registry.JobHandlerRegistry()

        account_security_subscribers.register_durable_handlers(registry)

        assert registry.subscriber_ids() >= {
            account_security_subscribers.ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.IDP_LINKED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.PASSWORD_RESET_COMPLETED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.ACCOUNT_LOCKED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.MFA_LOCKED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.STEP_UP_SESSION_ENDED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.STEP_UP_LOCKED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.NEW_DEVICE_SIGN_IN_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.BACKUP_CODE_USED_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.REFRESH_REUSE_EMAIL_SUBSCRIBER_ID,
            account_security_subscribers.ADMIN_PROMOTED_EMAIL_SUBSCRIBER_ID,
        }

    def test_the_module_registry_registers_the_bus_subscribers_and_declares_a_net_for_each_handler(self):
        account_security_subscriber_registry.register_bus_subscribers(jasil_runtime.get_active_platform().events)
        registry = jobs_registry.JobHandlerRegistry()
        account_security_subscriber_registry.register_durable_handlers(registry)

        assert {net.subscriber_id for net in account_security_subscriber_registry.DURABLE_SUBSCRIBER_NETS} == (
            registry.subscriber_ids()
        )
