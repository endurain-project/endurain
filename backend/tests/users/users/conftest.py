"""Fixtures shared by the users tests: the administrator's step-up, mail, the events the module's flows publish."""

import jasil.runtime as jasil_runtime
import pytest
from jasil.events import Event

import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.sign_up_tokens.events as sign_up_tokens_events
import modules.users.users.events as users_events
from tests._factories.server_settings import edit_mail_settings

_CHANNELS = (
    account_security_events.ACCOUNT_SECURITY_CHANGED,
    users_events.USERS_ADMIN_PROMOTED,
    sign_up_tokens_events.ADMIN_INVITATION_REQUESTED,
    sign_up_tokens_events.EMAIL_CHANGE_REQUESTED,
    sign_up_tokens_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
    sign_up_tokens_events.EMAIL_CHANGED,
    sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED,
    sign_up_tokens_events.SIGN_UP_APPROVED,
)


@pytest.fixture
def step_up_store():
    """The platform's step-up lockout store, as the routes resolve it."""
    return account_security_integration.get_step_up_attempts(jasil_runtime.get_active_platform().state)


@pytest.fixture
def mail_configured(db):
    """Store a mail host, so the server counts as able to send mail."""
    edit_mail_settings(db, host="smtp.example.com", port=587, security="starttls", username=None, from_address=None)


@pytest.fixture
def published() -> list[Event]:
    """The events the account flows publish during the test, in order, as the bus delivers them."""
    events: list[Event] = []
    bus = jasil_runtime.get_active_platform().events
    for channel in _CHANNELS:
        bus.subscribe(channel, events.append)
    return events
