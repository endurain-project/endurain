"""Event subscribers for account-security change emails."""

import jasil.event_versioning as platform_event_versioning
import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.email_messages as account_security_email_messages
import modules.auth.account_security.events as account_security_events
import modules.auth.identity_providers.events as idp_events

logger = core_logger.get_logger(__name__)
ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID = "auth.send_account_security_changed_email"
IDP_LINKED_EMAIL_SUBSCRIBER_ID = "auth.send_idp_linked_email"


def _send_security_change_email(
    user_id: int, change: str, idp_id: int | None, mail: platform_providers.MailProvider
) -> None:
    """Prepare a security-change email in a short session and send it once the session has closed."""
    with core_database.SessionLocal() as db:
        message = account_security_service.prepare_security_change_email(
            user_id, change, idp_id, core_config.settings.ENDURAIN_HOST, db
        )
    if message is None:
        logger.debug(
            "Skipped security-change email because the user is missing or inactive",
            extra=core_logger.context(user_id=user_id, change=change),
        )
        return
    recipient, subject, html_content, text_content = message
    try:
        sent = core_mail.send_email(mail, recipient, subject, html_content, text_content)
    except Exception as err:
        logger.error(
            "Security-change email delivery failed",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, change=change),
        )
        raise
    logger.debug(
        "Security-change email delivered" if sent else "Security-change email was not delivered",
        extra=core_logger.context(user_id=user_id, change=change),
    )


def send_security_changed_email_for_event(event: Event) -> None:
    """Send the user an email naming the account-security change that happened."""
    payload = platform_event_versioning.parse_payload(account_security_events.AccountSecurityChangedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    _send_security_change_email(payload.user_id, payload.change.value, payload.idp_id, mail)
    logger.debug(
        "Account-security-changed event processed",
        extra=core_logger.context(user_id=payload.user_id, change=payload.change.value),
    )


def send_idp_linked_email_for_event(event: Event) -> None:
    """Send the user an email saying a sign-in provider was linked to their account."""
    payload = platform_event_versioning.parse_payload(idp_events.IdpLinkedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    _send_security_change_email(
        payload.user_id, account_security_email_messages.IDENTITY_PROVIDER_LINKED, payload.idp_id, mail
    )
    logger.debug("Identity-provider-linked event processed", extra=core_logger.context(user_id=payload.user_id))


on_security_changed = best_effort(send_security_changed_email_for_event)
on_idp_linked = best_effort(send_idp_linked_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the account-security email bus subscribers."""
    events.subscribe(account_security_events.ACCOUNT_SECURITY_CHANGED, on_security_changed)
    events.subscribe(idp_events.IDP_LINKED, on_idp_linked)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable account-security email durable handlers."""
    registry.register(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID,
        send_security_changed_email_for_event,
    )
    registry.register(
        idp_events.IDP_LINKED,
        IDP_LINKED_EMAIL_SUBSCRIBER_ID,
        send_idp_linked_email_for_event,
    )
