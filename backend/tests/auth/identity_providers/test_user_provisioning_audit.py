"""SSO sign-in audits every identity link it makes, and every one it refuses."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.user_provisioning_service as provisioning

_LINKS = "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration"
_USERS = "modules.auth.identity_providers.user_provisioning_service.users_integration"


def _idp() -> MagicMock:
    idp = MagicMock(id=3, user_mapping=None, sync_user_info=False, auto_create_users=True)
    idp.name = "Pocket"
    return idp


def _existing_user(*, email_verified: bool = True) -> MagicMock:
    user = MagicMock(id=7, email_verified=email_verified)
    user.username = "alice"
    return user


def _sign_in(userinfo, user, mock_db):
    with (
        patch(f"{_LINKS}.get_user_identity_provider_by_subject_and_idp_id", return_value=None),
        patch(f"{_LINKS}.create_user_identity_provider"),
        patch(f"{_USERS}.get_user_by_email", return_value=user),
    ):
        return provisioning.find_or_create_user(_idp(), "subject-1", userinfo, mock_db)


def test_linking_an_existing_account_by_email_is_audited(mock_db):
    with jasil_testing.capture_audit() as audit:
        _sign_in({"email": "alice@example.com", "email_verified": True}, _existing_user(), mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id,
        outcome="success",
        target_type="user",
        target_id="7",
        target_owner_id="7",
    )
    assert entry.details == {"idp_id": 3, "reason": None}


def test_a_sign_in_through_an_existing_link_writes_no_link_row(mock_db):
    with (
        patch(f"{_LINKS}.get_user_identity_provider_by_subject_and_idp_id", return_value=MagicMock(user_id=7)),
        patch(f"{_LINKS}.update_user_identity_provider_last_login"),
        patch(f"{_USERS}.get_user", return_value=_existing_user()),
        jasil_testing.capture_audit() as audit,
    ):
        provisioning.find_or_create_user(_idp(), "subject-1", {}, mock_db)

    audit.assert_not_audited(idp_audit_actions.IDENTITY_LINK_LINK.id)


@pytest.mark.parametrize(
    ("userinfo", "user", "reason"),
    [
        ({"email": "alice@example.com"}, _existing_user(), "provider_email_unverified"),
        (
            {"email": "alice@example.com", "email_verified": True},
            _existing_user(email_verified=False),
            "account_email_unverified",
        ),
    ],
)
def test_a_refused_email_link_is_recorded_as_denied_with_its_reason(mock_db, userinfo, user, reason):
    with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PermissionDeniedError):
        _sign_in(userinfo, user, mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id,
        outcome="denied",
        target_type="user",
        target_id="7",
        target_owner_id="7",
    )
    assert entry.details == {"idp_id": 3, "reason": reason}


def test_creating_an_account_from_a_provider_audits_its_link(mock_db):
    with (
        patch(f"{_USERS}.get_user_by_username", return_value=None),
        patch(f"{_USERS}.create_sso_user", return_value=MagicMock(id=9, username="new")),
        patch.object(provisioning.server_settings_integration, "get_server_settings"),
        patch(f"{_LINKS}.create_user_identity_provider"),
        jasil_testing.capture_audit() as audit,
    ):
        provisioning.create_user_from_idp(
            _idp(), "subject-1", {"username": "new", "email": "new@example.com"}, mock_db, email_verified=True
        )

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id, outcome="success", target_type="user", target_id="9"
    )
    assert entry.details == {"idp_id": 3, "reason": None}


def test_an_inactive_account_found_by_its_link_is_refused_before_any_write(mock_db):
    inactive = _existing_user()
    inactive.active = False
    with (
        patch(f"{_LINKS}.get_user_identity_provider_by_subject_and_idp_id", return_value=MagicMock(user_id=7)),
        patch(f"{_LINKS}.update_user_identity_provider_last_login") as last_login,
        patch(f"{_USERS}.get_user", return_value=inactive),
        pytest.raises(core_exceptions.PermissionDeniedError),
    ):
        provisioning.find_or_create_user(_idp(), "subject-1", {}, mock_db)

    last_login.assert_not_called()


def test_an_inactive_account_matched_by_email_is_not_linked(mock_db):
    inactive = _existing_user()
    inactive.active = False
    with (
        patch(f"{_LINKS}.get_user_identity_provider_by_subject_and_idp_id", return_value=None),
        patch(f"{_LINKS}.create_user_identity_provider") as create_link,
        patch(f"{_USERS}.get_user_by_email", return_value=inactive),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.PermissionDeniedError),
    ):
        provisioning.find_or_create_user(
            _idp(), "subject-1", {"email": "alice@example.com", "email_verified": True}, mock_db
        )

    create_link.assert_not_called()
    audit.assert_not_audited(idp_audit_actions.IDENTITY_LINK_LINK.id)
