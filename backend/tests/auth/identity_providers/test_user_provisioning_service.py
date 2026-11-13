"""
Tests for user_provisioning_service.find_or_create_user email-link gating.

Focuses on the account-takeover prevention introduced for email-based
linking: an external identity may only be auto-linked to an EXISTING local
account when the IdP asserts a verified email (OIDC ``email_verified``).
"""

import uuid
from unittest.mock import ANY, MagicMock, patch

import pytest
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.users.users.schema as users_schema
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()


def _make_idp() -> MagicMock:
    """Build a minimal IdP mock that maps the standard email claim."""
    idp = MagicMock()
    idp.id = IDP_ID
    idp.name = "TestIdP"
    idp.user_mapping = None
    idp.sync_user_info = False
    idp.sync_email = False
    idp.link_by_email = True
    idp.auto_create_users = True
    return idp


class TestFindOrCreateUserEmailLinking:
    """Test suite for email-based linking gate in find_or_create_user."""

    def test_unverified_email_existing_account_is_rejected(self):
        """Linking to an existing account must fail when email unverified."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"

        userinfo = {"email": "victim@example.com"}  # no email_verified claim

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert exc_info.value.status_code == 403
        # No link must be created for the unverified takeover attempt.
        mock_link.assert_not_called()

    def test_mail_claim_with_verified_flag_existing_account_is_rejected(self):
        """An address from ``mail`` never auto-links, even when email_verified is true."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"

        userinfo = {"mail": "victim@example.com", "email_verified": True}

        base = "modules.auth.identity_providers.user_provisioning_service"
        with (
            patch(
                f"{base}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(f"{base}.users_integration.get_user_by_email", return_value=existing_user),
            patch(f"{base}.identity_provider_links_integration.create_user_identity_provider") as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert exc_info.value.status_code == 403
        mock_link.assert_not_called()

    def test_verified_email_existing_account_is_linked(self):
        """Linking to an existing account succeeds when email is verified."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.id = MOCK_USER_ID
        existing_user.username = "legit"

        userinfo = {"email": "legit@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
        ):
            result = user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert result is existing_user
        mock_link.assert_called_once_with(existing_user.id, idp.id, "subject-123", mock_db)

    def test_email_link_publishes_idp_linked(self):
        """An automatic link by email tells the owner, as an explicit link does."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.id = MOCK_USER_ID
        existing_user.username = "legit"

        with (
            patch(
                f"{_BASE}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(f"{_BASE}.users_integration.get_user_by_email", return_value=existing_user),
            patch(f"{_BASE}.identity_provider_links_integration.create_user_identity_provider"),
            patch(f"{_BASE}.idp_event_publishers.publish_idp_linked") as publish,
        ):
            user_provisioning_service.find_or_create_user(
                idp, "subject-123", {"email": "legit@example.com", "email_verified": True}, mock_db
            )

        publish.assert_called_once_with(existing_user.id, idp.id, mock_db)

    def test_unverified_email_no_existing_account_creates_user(self):
        """Unverified email with no existing account still auto-creates."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        created_user = MagicMock()

        userinfo = {"email": "fresh@example.com"}  # unverified, no match

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch(f"{_BASE}.server_settings_integration.get_server_settings"),
            patch.object(
                user_provisioning_service,
                "create_user_from_idp",
                new=MagicMock(return_value=created_user),
            ) as mock_create,
        ):
            result = user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert result is created_user
        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["email_verified"] is False


class TestSsoSignUpGate:
    """A new account is created only when the server allows SSO sign-up and the provider allows account creation."""

    def _sign_in(self, *, server_allows: bool, provider_allows: bool, existing_user=None):
        idp = _make_idp()
        idp.auto_create_users = provider_allows
        with (
            patch(
                f"{_BASE}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(f"{_BASE}.users_integration.get_user_by_email", return_value=existing_user),
            patch(f"{_BASE}.users_integration.require_active_user"),
            patch(f"{_BASE}.identity_provider_links_integration.create_user_identity_provider"),
            patch(f"{_BASE}.stage_identity_link"),
            patch(f"{_BASE}.idp_event_publishers.publish_idp_linked"),
            patch(f"{_BASE}.update_user_from_idp", side_effect=lambda user, *_: user),
            patch(
                f"{_BASE}.server_settings_integration.get_server_settings",
                return_value=MagicMock(signup_sso_enabled=server_allows),
            ),
            patch.object(user_provisioning_service, "create_user_from_idp") as create,
        ):
            create.return_value = MagicMock()
            try:
                result = user_provisioning_service.find_or_create_user(
                    idp, "subject-1", {"email": "new@example.com", "email_verified": True}, MagicMock()
                )
            except user_provisioning_service.SsoSignInRefusedError as err:
                return create, None, err
        return create, result, None

    def test_both_allowing_creates_the_account(self):
        create, result, error = self._sign_in(server_allows=True, provider_allows=True)

        assert error is None
        create.assert_called_once()
        assert result is create.return_value

    @pytest.mark.parametrize(("server_allows", "provider_allows"), [(False, True), (True, False), (False, False)])
    def test_either_switch_off_refuses_with_its_login_error(self, server_allows, provider_allows):
        create, result, error = self._sign_in(server_allows=server_allows, provider_allows=provider_allows)

        assert result is None
        assert error is not None
        assert error.login_error == "sso_auto_create_disabled"
        assert error.status_code == 403
        create.assert_not_called()

    def test_the_server_switch_off_still_links_an_account_by_email(self):
        existing = MagicMock(id=MOCK_USER_ID, username="alice", email_verified=True)
        create, result, error = self._sign_in(server_allows=False, provider_allows=True, existing_user=existing)

        assert error is None
        assert result is existing
        create.assert_not_called()


class TestCreatedAccountEmailVerification:
    """A new SSO account's email is verified only when the provider asserted it as verified."""

    def _create(self, *, asserted: bool, verification_required: bool) -> MagicMock:
        with (
            patch.object(user_provisioning_service.users_integration, "get_user_by_username", return_value=None),
            patch.object(
                user_provisioning_service.server_settings_integration,
                "get_server_settings",
                return_value=MagicMock(signup_require_email_verification=verification_required),
            ),
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            patch.object(
                user_provisioning_service.identity_provider_links_integration, "create_user_identity_provider"
            ),
        ):
            create_sso_user.return_value = MagicMock(id=3, username="new")
            user_provisioning_service.create_user_from_idp(
                _make_idp(),
                "subject-123",
                {"username": "new", "email": "new@example.com"},
                MagicMock(),
                email_verified=asserted,
            )
        return create_sso_user

    @pytest.mark.parametrize("asserted", [True, False])
    def test_the_flag_follows_the_provider(self, asserted):
        create_sso_user = self._create(asserted=asserted, verification_required=False)

        assert create_sso_user.call_args.kwargs["email_verified"] is asserted

    def test_an_address_the_provider_verified_is_accepted_when_the_server_requires_verification(self):
        create_sso_user = self._create(asserted=True, verification_required=True)

        create_sso_user.assert_called_once()

    def test_an_unverified_address_is_refused_when_the_server_requires_verification(self):
        """The provider identity is already bound to the account, so a link clicked by the address's owner would
        hand that address to whoever signed in; only the provider's own verification proves it."""
        with (
            patch.object(
                user_provisioning_service.server_settings_integration,
                "get_server_settings",
                return_value=MagicMock(signup_require_email_verification=True),
            ),
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            pytest.raises(user_provisioning_service.SsoSignInRefusedError) as exc_info,
        ):
            user_provisioning_service.create_user_from_idp(
                _make_idp(),
                "subject-123",
                {"username": "new", "email": "new@example.com"},
                MagicMock(),
                email_verified=False,
            )

        assert exc_info.value.login_error == "sso_email_unverified"
        create_sso_user.assert_not_called()

    def test_the_account_carries_the_mapped_profile(self):
        with (
            patch.object(user_provisioning_service.users_integration, "get_user_by_username", return_value=None),
            patch.object(user_provisioning_service.server_settings_integration, "get_server_settings"),
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            patch.object(
                user_provisioning_service.identity_provider_links_integration, "create_user_identity_provider"
            ),
        ):
            create_sso_user.return_value = MagicMock(id=3, username="new")
            user_provisioning_service.create_user_from_idp(
                _make_idp(),
                "subject-123",
                {"username": "new", "email": "new@example.com", "city": "Lisbon", "height": 180},
                MagicMock(),
                email_verified=True,
            )

        profile = create_sso_user.call_args.args[0]
        assert (profile.username, profile.city, profile.height) == ("new", "Lisbon", 180)

    @pytest.mark.parametrize("mapped", [{}, {"email": ""}, {"email": None}])
    def test_an_account_without_an_email_is_refused_with_its_own_reason(self, mapped):
        """Every account needs a real address for reset and notices, so none is invented for it."""
        with (
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            pytest.raises(user_provisioning_service.SsoSignInRefusedError) as exc_info,
        ):
            user_provisioning_service.create_user_from_idp(
                _make_idp(), "subject-123", {"username": "new", **mapped}, MagicMock(), email_verified=True
            )

        assert exc_info.value.login_error == "sso_email_missing"
        create_sso_user.assert_not_called()


class TestLocalEmailVerificationGate:
    """An email-based link also requires the local account's email to be verified."""

    def test_verified_idp_email_with_unverified_local_email_is_rejected(self):
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"
        existing_user.email_verified = False

        userinfo = {"email": "victim@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert exc_info.value.status_code == 403
        mock_link.assert_not_called()


_BASE = "modules.auth.identity_providers.user_provisioning_service"


class TestLinkByEmail:
    """A provider links an unlinked subject to the local account with its email only when ``link_by_email`` is on."""

    @staticmethod
    def _sign_in(idp, userinfo, *, existing_user):
        with (
            patch(
                f"{_BASE}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id"
            ) as get_link,
            patch(f"{_BASE}.users_integration.get_user_by_email", return_value=existing_user),
            patch(f"{_BASE}.users_integration.create_sso_user") as create_user,
            patch(f"{_BASE}.identity_provider_links_integration.create_user_identity_provider") as link,
            patch(f"{_BASE}.record_identity_link_refused") as refused,
            patch(f"{_BASE}.idp_event_publishers.publish_idp_linked") as publish,
        ):
            get_link.return_value = None
            try:
                result = user_provisioning_service.find_or_create_user(idp, "subject-1", userinfo, MagicMock())
                error = None
            except core_exceptions.DomainError as exc:
                result, error = None, exc
        return result, error, link, create_user, refused, publish

    def test_off_refuses_an_email_match_and_tells_the_user_to_sign_in_locally(self):
        idp = _make_idp()
        idp.link_by_email = False
        existing = MagicMock(id=MOCK_USER_ID, email_verified=True)
        existing.username = "alice"

        _, error, link, create_user, refused, publish = self._sign_in(
            idp, {"email": "alice@example.com", "email_verified": True}, existing_user=existing
        )

        assert isinstance(error, user_provisioning_service.SsoSignInRefusedError)
        assert error.status_code == 403
        assert error.login_error == "sso_link_by_email_disabled"
        link.assert_not_called()
        publish.assert_not_called()
        create_user.assert_not_called()
        refused.assert_called_once_with(
            MOCK_USER_ID, IDP_ID, idp_audit_actions.IdentityLinkRefusal.LINK_BY_EMAIL_DISABLED
        )

    def test_off_refuses_before_the_verification_checks(self):
        idp = _make_idp()
        idp.link_by_email = False
        existing = MagicMock(id=MOCK_USER_ID, email_verified=False)
        existing.username = "alice"

        _, error, _, _, refused, publish = self._sign_in(idp, {"email": "alice@example.com"}, existing_user=existing)
        publish.assert_not_called()

        assert error.login_error == "sso_link_by_email_disabled"
        refused.assert_called_once_with(
            MOCK_USER_ID, IDP_ID, idp_audit_actions.IdentityLinkRefusal.LINK_BY_EMAIL_DISABLED
        )

    def test_on_links_as_before(self):
        idp = _make_idp()
        existing = MagicMock(id=MOCK_USER_ID, email_verified=True)
        existing.username = "alice"

        result, error, link, _, refused, _ = self._sign_in(
            idp, {"email": "alice@example.com", "email_verified": True}, existing_user=existing
        )

        assert error is None
        assert result is existing
        link.assert_called_once_with(MOCK_USER_ID, IDP_ID, "subject-1", ANY)
        refused.assert_not_called()

    def test_off_still_creates_a_new_user_when_no_account_has_the_email(self):
        idp = _make_idp()
        idp.link_by_email = False

        with (
            patch(
                f"{_BASE}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(f"{_BASE}.users_integration.get_user_by_email", return_value=None),
            patch(f"{_BASE}.users_integration.get_user_by_username", return_value=None),
            patch(f"{_BASE}.server_settings_integration.get_server_settings"),
            patch(f"{_BASE}.users_integration.create_sso_user", return_value=MagicMock(id=3, username="new")) as create,
            patch(f"{_BASE}.identity_provider_links_integration.create_user_identity_provider"),
        ):
            user_provisioning_service.find_or_create_user(
                idp, "subject-1", {"email": "new@example.com", "email_verified": True}, MagicMock()
            )

        create.assert_called_once()

    def test_off_does_not_affect_a_subject_that_is_already_linked(self):
        idp = _make_idp()
        idp.link_by_email = False
        user = MagicMock(id=MOCK_USER_ID)

        with (
            patch(
                f"{_BASE}.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=MagicMock(user_id=MOCK_USER_ID),
            ),
            patch(f"{_BASE}.identity_provider_links_integration.update_user_identity_provider_last_login"),
            patch(f"{_BASE}.users_integration.get_user", return_value=user),
            patch(f"{_BASE}.users_integration.require_active_user"),
        ):
            result = user_provisioning_service.find_or_create_user(idp, "subject-1", {}, MagicMock())

        assert result is user


class TestUpdateUserFromIdp:
    """``sync_user_info`` syncs the name; the email follows ``sync_email`` alone."""

    @staticmethod
    def _user(**overrides):
        user = MagicMock()
        user.id = MOCK_USER_ID
        user.username = "alice"
        user.email = "old@example.com"
        user.name = "Old Name"
        for key, value in overrides.items():
            setattr(user, key, value)
        return user

    @staticmethod
    def _sync(user, idp, userinfo, *, holder=None):
        refreshed = MagicMock(name="refreshed", username="alice")
        with (
            patch(f"{_BASE}.users_integration.is_email_available", return_value=holder is None),
            patch(f"{_BASE}.users_integration.edit_user", return_value=user) as edit,
            patch(f"{_BASE}.users_integration.stage_synced_email_change") as email_change,
            patch(f"{_BASE}.users_integration.get_user", return_value=refreshed) as get_user,
            patch(f"{_BASE}.users_schema.UserEdit.from_read"),
        ):
            result = user_provisioning_service.update_user_from_idp(user, idp, userinfo, MagicMock(spec=Session))
        return result, refreshed, edit, email_change, get_user

    def test_with_both_flags_off_nothing_is_written(self):
        user = self._user()

        result, _, edit, email_change, _ = self._sync(
            user, _make_idp(), {"email": "new@example.com", "email_verified": True, "name": "New"}
        )

        assert result is user
        edit.assert_not_called()
        email_change.assert_not_called()

    def test_sync_user_info_syncs_the_name_and_keeps_the_email(self):
        idp = _make_idp()
        idp.sync_user_info = True
        user = self._user()

        _, _, edit, email_change, _ = self._sync(
            user, idp, {"email": "new@example.com", "email_verified": True, "name": "New Name"}
        )

        user.model_copy.assert_called_once_with(update={"name": "New Name"})
        edit.assert_called_once()
        assert edit.call_args.kwargs["if_match"] == "*"
        email_change.assert_not_called()

    def test_sync_email_changes_the_email_notifies_the_previous_address_and_leaves_the_name(self):
        idp = _make_idp()
        idp.sync_email = True
        user = self._user()

        result, refreshed, edit, email_change, get_user = self._sync(
            user, idp, {"email": "new@example.com", "email_verified": True, "name": "New Name"}
        )

        email_change.assert_called_once_with(MOCK_USER_ID, "new@example.com", ANY)
        edit.assert_not_called()
        get_user.assert_called_once_with(MOCK_USER_ID, ANY)
        assert result is refreshed

    def test_both_flags_sync_the_name_and_the_email(self):
        idp = _make_idp()
        idp.sync_user_info = True
        idp.sync_email = True
        user = self._user()

        _, _, edit, email_change, _ = self._sync(
            user, idp, {"email": "new@example.com", "email_verified": True, "name": "New Name"}
        )

        edit.assert_called_once()
        email_change.assert_called_once()

    def test_an_email_the_provider_did_not_verify_is_not_synced(self):
        idp = _make_idp()
        idp.sync_email = True

        _, _, _, email_change, _ = self._sync(self._user(), idp, {"email": "new@example.com"})

        email_change.assert_not_called()

    def test_an_email_another_account_uses_is_not_synced(self):
        idp = _make_idp()
        idp.sync_email = True

        _, _, _, email_change, _ = self._sync(
            self._user(), idp, {"email": "new@example.com", "email_verified": True}, holder=MagicMock(id=OTHER_USER_ID)
        )

        email_change.assert_not_called()

    def test_the_same_email_is_not_a_change(self):
        idp = _make_idp()
        idp.sync_email = True

        _, _, _, email_change, _ = self._sync(self._user(), idp, {"email": "old@example.com", "email_verified": True})

        email_change.assert_not_called()

    def test_applied_updates_log_field_names_and_hashed_username(self):
        idp = _make_idp()
        idp.sync_email = True
        user = self._user()
        with (
            patch(f"{_BASE}.users_integration.is_email_available", return_value=True),
            patch(f"{_BASE}.users_integration.stage_synced_email_change"),
            patch(f"{_BASE}.users_integration.get_user", return_value=MagicMock(username="alice")),
            patch(f"{_BASE}.logger") as mock_logger,
        ):
            user_provisioning_service.update_user_from_idp(
                user, idp, {"email": "new@example.com", "email_verified": True}, MagicMock(spec=Session)
            )

        extra = mock_logger.info.call_args.kwargs["extra"]
        assert extra["updated_fields"] == ["email"]
        assert "alice" not in str(extra)
        assert "new@example.com" not in str(extra)


def _signed_up_username(subject: str, claims: dict, taken: set[str] | None = None) -> str:
    """Sign a user up from raw IdP claims and return the username the account was created with."""
    taken = taken or set()
    idp = _make_idp()
    mapped = user_provisioning_service.claim_mapping.map_user_claims(idp, claims)
    with (
        patch.object(
            user_provisioning_service.users_integration,
            "get_user_by_username",
            side_effect=lambda username, _db: MagicMock() if username in taken else None,
        ),
        patch.object(user_provisioning_service.server_settings_integration, "get_server_settings"),
        patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
        patch.object(user_provisioning_service.identity_provider_links_integration, "create_user_identity_provider"),
    ):
        create_sso_user.return_value = MagicMock(id=3, username="new")
        user_provisioning_service.create_user_from_idp(idp, subject, mapped, MagicMock(), email_verified=True)
    return create_sso_user.call_args.args[0].username


class TestSsoUsernameDerivation:
    """An SSO account's username is valid and never carries any part of the email address."""

    def test_google_claims_without_preferred_username_get_a_subject_based_name(self):
        claims = {"sub": "1048576123456789", "email": "john.smith@gmail.com", "name": "John Smith"}
        assert _signed_up_username("1048576123456789", claims) == "user_10485761"

    def test_entra_upn_is_not_used(self):
        claims = {"sub": "AAAAAAAA-bbbb", "preferred_username": "john@contoso.com", "email": "john@contoso.com"}
        username = _signed_up_username("AAAAAAAA-bbbb", claims)
        assert username == "user_AAAAAAAA"
        assert "john" not in username

    def test_valid_preferred_username_is_kept(self):
        claims = {"sub": "abc", "preferred_username": "jane.doe", "email": "jane@example.com"}
        assert _signed_up_username("abc", claims) == "jane.doe"

    def test_invalid_characters_are_replaced_by_a_single_underscore_per_run(self):
        claims = {"sub": "abc", "preferred_username": "  Jöse +Silva  ", "email": "j@example.com"}
        assert _signed_up_username("abc", claims) == "J_se_Silva"

    def test_a_claim_with_nothing_usable_falls_back_to_the_subject(self):
        claims = {"sub": "abcdefghijkl", "preferred_username": "+++ ö", "email": "j@example.com"}
        assert _signed_up_username("abcdefghijkl", claims) == "user_abcdefgh"

    def test_subject_with_pipe_gives_a_valid_name(self):
        username = _signed_up_username("auth0|5f7c8ec7c33c6c004bbafe82", {"email": "j@example.com"})
        assert username == "user_auth0_5f"

    def test_short_or_unusable_subject_falls_back_to_a_hash(self):
        assert _signed_up_username("|||", {"email": "j@example.com"}) == (
            f"user_{user_provisioning_service.core_hashing.sha256_hex('|||')[:8]}"
        )

    def test_a_subject_that_is_an_email_is_hashed(self):
        username = _signed_up_username("john@contoso.com", {"email": "john@contoso.com"})
        assert "john" not in username
        assert len(username) == len("user_") + 8

    def test_very_long_subject_gives_a_short_valid_name(self):
        assert _signed_up_username("x" * 5000, {"email": "j@example.com"}) == "user_xxxxxxxx"

    def test_uniqueness_suffix_stays_valid_at_the_length_limit(self):
        long_name = "a" * 400
        base = "a" * user_provisioning_service.MAX_USERNAME_BASE_LENGTH
        username = _signed_up_username("abc", {"preferred_username": long_name, "email": "j@example.com"}, {base})
        adapter = TypeAdapter(users_schema.UserUsername)
        assert adapter.validate_python(username) == username
        assert username.startswith(base + "_")
        assert len(username) == 250
