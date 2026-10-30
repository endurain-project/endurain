"""Tests for users.users.service module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_CRUD = "modules.users.users.service.users_crud"
_SETTINGS = "modules.users.users.service.server_settings_integration"


def _user(user_id: int = 1, **overrides) -> users_schema.UsersRead:
    fields = {
        "id": user_id,
        "name": "User",
        "username": f"user{user_id}",
        "email": f"user{user_id}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UsersRead(**fields)


def _edit(user_id: int = 1, **overrides) -> users_schema.UsersEdit:
    return users_schema.UsersEdit.from_read(_user(user_id, **overrides))


def _signup() -> users_schema.UsersSignup:
    return users_schema.UsersSignup(
        name="New", username="NewUser", email="New@Example.com", password="SecurePass1!", preferred_language="en"
    )


_auth_service_mock: MagicMock | None = None
_delete_all_sessions_mock: MagicMock


def _identity() -> MagicMock:
    global _auth_service_mock
    _auth_service_mock = MagicMock()
    _auth_service_mock.get_identity_link_counts_for_users.return_value = {}
    _auth_service_mock.get_mfa_enabled_for_users.return_value = {}
    return _auth_service_mock


@pytest.fixture(autouse=True)
def sign_up():
    """Replace the sign-up-token boundary: no pending change, and mail configured."""
    with patch("modules.users.users.service.sign_up_tokens_integration") as integration:
        integration.get_pending_email_changes.return_value = {}
        integration.request_email_change.return_value = True
        yield integration


@pytest.fixture(autouse=True)
def _auth_integration_mocks(monkeypatch):
    """Mock auth integration boundaries while preserving each test's configured values."""
    global _auth_service_mock
    global _delete_all_sessions_mock
    _auth_service_mock = None
    _delete_all_sessions_mock = MagicMock()

    def mock_call(name, *args):
        if _auth_service_mock is None:
            return {}
        return getattr(_auth_service_mock, name)(*args)

    monkeypatch.setattr(
        identity_links_integration,
        "get_identity_link_counts_for_users",
        lambda ids, db: mock_call("get_identity_link_counts_for_users", ids),
    )
    monkeypatch.setattr(
        mfa_integration,
        "get_mfa_enabled_for_users",
        lambda ids, db: mock_call("get_mfa_enabled_for_users", ids),
    )
    monkeypatch.setattr(
        mfa_integration,
        "create_users_mfa_row",
        lambda user_id, db: mock_call("initialize_user_mfa", user_id),
    )
    monkeypatch.setattr(
        credentials_integration,
        "validate_and_hash_password_for_user",
        lambda settings, access_type, password, db: mock_call(
            "validate_and_hash_password_for_user", settings, access_type, password
        ),
    )
    monkeypatch.setattr(
        credentials_integration,
        "set_local_password_hash",
        lambda user_id, password_hash, db: mock_call("set_local_password_hash", user_id, password_hash),
    )
    _delete_all_sessions_mock.side_effect = lambda user_id, db: mock_call("delete_all_user_sessions", user_id)
    monkeypatch.setattr(account_security_integration, "delete_all_user_sessions", _delete_all_sessions_mock)


class TestRequirements:
    @patch(_CRUD)
    def test_require_user_returns_the_user(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user()

        assert users_service.require_user(1, mock_db).id == 1

    @patch(_CRUD)
    def test_require_user_missing_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user(1, mock_db)

    def test_require_active_user_refuses_an_inactive_user(self):
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.require_active_user(_user(active=False))

    def test_require_active_user_passes_an_active_user(self):
        users_service.require_active_user(_user())

    @patch(_CRUD)
    def test_require_admin_users_none_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_users_admin.return_value = []

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_admin_users(mock_db)


class TestPublicUser:
    @patch(_CRUD)
    @patch(_SETTINGS)
    def test_hidden_when_public_sharing_is_off(self, mock_settings, mock_crud, mock_db):
        mock_settings.get_server_settings.return_value = MagicMock(
            public_shareable_links=False, public_shareable_links_user_info=True
        )

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_user(1, mock_db)
        mock_crud.get_user_by_id.assert_not_called()

    @patch(_CRUD)
    @patch(_SETTINGS)
    def test_hidden_when_user_info_sharing_is_off(self, mock_settings, mock_crud, mock_db):
        mock_settings.get_server_settings.return_value = MagicMock(
            public_shareable_links=True, public_shareable_links_user_info=False
        )

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_user(1, mock_db)

    @patch(_CRUD)
    @patch(_SETTINGS)
    def test_visible_when_both_are_on(self, mock_settings, mock_crud, mock_db):
        mock_settings.get_server_settings.return_value = MagicMock(
            public_shareable_links=True, public_shareable_links_user_info=True
        )

        mock_crud.get_user_by_id.return_value = _user(1, email="private@example.com")

        public = users_service.get_public_user(1, mock_db)

        assert isinstance(public, users_schema.UserPublicRead)
        assert public.id == 1


class TestListPublicProfiles:
    @patch(_CRUD)
    def test_keys_the_public_projection_by_user_id(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [_user(3, city="Porto"), _user(5)]

        profiles = users_service.list_public_profiles({3, 5}, mock_db)

        assert set(profiles) == {3, 5}
        assert all(type(profile) is users_schema.UserPublicRead for profile in profiles.values())
        assert profiles[3].city == "Porto"
        mock_crud.get_users_by_ids.assert_called_once_with({3, 5}, mock_db)

    @patch(_CRUD)
    def test_leaves_out_users_a_viewer_could_not_look_up(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [
            _user(1),
            _user(2, active=False),
            _user(3, pending_admin_approval=True),
        ]

        assert set(users_service.list_public_profiles({1, 2, 3}, mock_db)) == {1}

    @patch(_CRUD)
    def test_carries_no_personal_or_account_fields(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [_user(3, birthdate="1990-01-01")]

        dumped = users_service.list_public_profiles({3}, mock_db)[3].model_dump()

        assert set(dumped) == {"id", "name", "username", "city", "photo_path"}

    @patch(_CRUD)
    def test_no_users_found_is_an_empty_mapping(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = []

        assert users_service.list_public_profiles({7}, mock_db) == {}


class TestPublicProjection:
    @patch(_CRUD)
    def test_carries_no_personal_or_account_fields(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(3, city="Porto", birthdate="1990-01-01")

        dumped = users_service.get_public_profile(3, mock_db).model_dump()

        assert set(dumped) == {"id", "name", "username", "city", "photo_path"}

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    @patch(_CRUD)
    def test_an_inactive_or_pending_account_is_not_found(self, mock_crud, state, mock_db):
        mock_crud.get_user_by_id.return_value = _user(3, **state)

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_profile(3, mock_db)

    @patch(_CRUD)
    def test_an_active_account_is_returned(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(3)

        assert users_service.get_public_profile(3, mock_db).id == 3

    @patch(_CRUD)
    def test_missing_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_profile(3, mock_db)

    @patch(_CRUD)
    def test_search_is_paged_and_projected(self, mock_crud, mock_db):
        mock_crud.search_active_users_by_username.return_value = [_user(1), _user(2)]
        mock_crud.get_users_number.return_value = 30

        found = users_service.search_public_users("user", core_pagination.PageParams(2, 25), mock_db)

        assert [type(user) for user in found.items] == [users_schema.UserPublicRead] * 2
        assert (found.total, found.page, found.next) == (30, 2, None)
        mock_crud.search_active_users_by_username.assert_called_once_with("user", 25, 25, mock_db)
        assert mock_crud.get_users_number.call_args.kwargs["username"] == "user"


class TestListUsers:
    @patch(_CRUD)
    def test_enriches_and_filters_by_authentication(self, mock_crud, mock_db):
        mock_crud.get_users_number.return_value = 2
        mock_crud.get_users_with_pagination.return_value = [_user(1, name="Alice"), _user(2, name="Bob")]
        identity = _identity()
        identity.get_identity_link_counts_for_users.return_value = {1: 2}
        identity.get_mfa_enabled_for_users.return_value = {2: True}

        result = users_service.list_users(mock_db, page_number=1, num_records=10, show_external_auth=False)

        assert result.total == 2
        assert [u.name for u in result.items] == ["Bob"]
        assert result.items[0].mfa_enabled is True

    @patch(_CRUD)
    def test_local_filter_drops_users_without_a_link(self, mock_crud, mock_db):
        mock_crud.get_users_number.return_value = 2
        mock_crud.get_users_with_pagination.return_value = [_user(1, name="Alice"), _user(2, name="Bob")]
        identity = _identity()
        identity.get_identity_link_counts_for_users.return_value = {1: 1}
        identity.get_mfa_enabled_for_users.return_value = {}

        result = users_service.list_users(mock_db, show_local_auth=False)

        assert [u.name for u in result.items] == ["Alice"]


class TestPendingEmailChanges:
    @patch(_CRUD)
    def test_the_list_carries_each_users_pending_change_from_one_lookup(self, mock_crud, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_users_number.return_value = 2
        mock_crud.get_users_with_pagination.return_value = [_user(1), _user(2)]
        sign_up.get_pending_email_changes.return_value = {
            2: sign_up_contracts.PendingEmailChange(email="next@example.com", expires_at=expires)
        }

        result = users_service.list_users(mock_db)

        sign_up.get_pending_email_changes.assert_called_once_with([1, 2], mock_db)
        assert [(u.pending_email, u.pending_email_expires_at) for u in result.items] == [
            (None, None),
            ("next@example.com", expires),
        ]

    @patch(_CRUD)
    def test_an_admin_read_carries_the_pending_change(self, mock_crud, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_user_by_id.return_value = _user(4)
        sign_up.get_pending_email_changes.return_value = {
            4: sign_up_contracts.PendingEmailChange(email="next@example.com", expires_at=expires)
        }

        user = users_service.require_user_with_pending_email(4, mock_db)

        assert (user.pending_email, user.pending_email_expires_at) == ("next@example.com", expires)

    @patch(_CRUD)
    def test_an_admin_read_of_a_missing_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user_with_pending_email(4, mock_db)

    def test_an_edit_built_from_a_read_leaves_the_pending_change_out(self):
        read = _user(1, pending_email="next@example.com", pending_email_expires_at=datetime(2030, 1, 1, tzinfo=UTC))

        edit = users_schema.UsersEdit.from_read(read)

        assert "pending_email" not in edit.model_dump()
        assert "pending_email_expires_at" not in edit.model_dump()


class TestRequireEmailAvailable:
    @patch(_CRUD)
    def test_another_accounts_address_is_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(2)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_email_available(1, "User2@Example.com", mock_db)

        mock_crud.get_user_by_email.assert_called_once_with("user2@example.com", mock_db)

    @patch(_CRUD)
    @pytest.mark.parametrize("holder", [None, 1])
    def test_a_free_address_or_the_users_own_passes(self, mock_crud, mock_db, holder):
        mock_crud.get_user_by_email.return_value = _user(holder) if holder else None

        users_service.require_email_available(1, "a@example.com", mock_db)


class TestCreateUser:
    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_hashes_creates_commits_then_stores_the_credential(self, mock_crud, mock_settings, mock_defaults, mock_db):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(7)
        user = users_schema.UsersCreate(
            name="N",
            username="NewUser",
            email="New@Example.com",
            active=True,
            access_type="regular",
            password="password123",
        )

        created = users_service.create_user(user, mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert fields["username"] == "newuser" and fields["email"] == "new@example.com"
        assert "password" not in fields
        mock_db.commit.assert_called_once()
        identity.set_local_password_hash.assert_called_once_with(7, "hash")
        mock_defaults.assert_called_once_with(7, mock_db)
        assert created.id == 7

    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_duplicate_rolls_back_and_stores_no_credential(self, mock_crud, mock_settings, mock_db):
        identity = _identity()
        mock_crud.create_user.side_effect = core_exceptions.ConflictError("dup")
        user = users_schema.UsersCreate(
            name="N", username="n", email="n@example.com", active=True, access_type="regular", password="password123"
        )

        with pytest.raises(core_exceptions.ConflictError):
            users_service.create_user(user, mock_db)

        mock_db.rollback.assert_called_once()
        identity.set_local_password_hash.assert_not_called()


class TestStageFirstAdmin:
    def _admin(self, **overrides) -> users_schema.FirstAdminCreate:
        fields = {"name": "Owner", "username": "Owner", "email": "Owner@Example.com", "password": "SecurePass1!"}
        fields.update(overrides)
        return users_schema.FirstAdminCreate(**fields)

    @patch(_CRUD)
    def test_refuses_when_a_user_exists_under_the_lock_and_stages_nothing(self, mock_crud, mock_db):
        identity = _identity()
        mock_crud.any_user_exists.return_value = True

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_first_admin(self._admin(), mock_db)

        mock_crud.lock_first_admin_creation.assert_called_once_with(mock_db)
        mock_crud.create_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_locks_before_it_checks_and_checks_before_it_inserts(
        self, mock_crud, mock_settings, mock_defaults, mock_db
    ):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.any_user_exists.return_value = False
        mock_crud.create_user.return_value = _user(1, access_type="admin")
        order = MagicMock()
        order.attach_mock(mock_crud.lock_first_admin_creation, "lock")
        order.attach_mock(mock_crud.any_user_exists, "check")
        order.attach_mock(mock_crud.create_user, "insert")

        users_service.stage_first_admin(self._admin(), mock_db)

        assert [call[0] for call in order.mock_calls] == ["lock", "check", "insert"]

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_stages_an_active_verified_admin_with_the_admin_password_policy_and_does_not_commit(
        self, mock_crud, mock_settings, mock_defaults, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.any_user_exists.return_value = False
        mock_crud.create_user.return_value = _user(1, access_type="admin")

        created = users_service.stage_first_admin(self._admin(), mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert fields["access_type"] == "admin"
        assert fields["active"] is True
        assert fields["email_verified"] is True
        assert fields["pending_admin_approval"] is False
        assert "deactivated_at" not in fields
        assert (fields["preferred_language"], fields["gender"], fields["units"]) == ("en", "unspecified", "metric")
        assert fields["username"] == "owner" and fields["email"] == "owner@example.com"
        assert "password" not in fields
        assert identity.validate_and_hash_password_for_user.call_args.args[1] == "admin"
        identity.set_local_password_hash.assert_called_once_with(1, "hash")
        mock_defaults.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_not_called()
        assert created.id == 1

    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_a_weak_password_surfaces_the_credentials_error_and_inserts_nothing(
        self, mock_crud, mock_settings, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.side_effect = core_exceptions.InvalidInputError("too short")
        mock_crud.any_user_exists.return_value = False

        with pytest.raises(core_exceptions.InvalidInputError):
            users_service.stage_first_admin(self._admin(), mock_db)

        mock_crud.create_user.assert_not_called()

    def test_the_request_shape_carries_no_access_type_or_account_state(self):
        for field in ("access_type", "active", "email_verified", "pending_admin_approval"):
            with pytest.raises(ValueError):
                users_schema.FirstAdminCreate(
                    name="O", username="o", email="o@example.com", password="SecurePass1!", **{field: True}
                )


class TestAccountCreationIsOneUnit:
    """The user row, credential, MFA row and default rows commit together, once, last."""

    @patch("modules.users.users.service.users_default_gear_integration")
    @patch("modules.users.users.service.health_targets_integration")
    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch("modules.users.users.service.user_integrations_integration")
    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_commit_follows_every_staged_write(
        self, mock_crud, mock_settings, mock_integrations, mock_privacy, mock_targets, mock_gear, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(7)
        order = MagicMock()
        order.attach_mock(mock_crud.create_user, "user")
        order.attach_mock(identity.set_local_password_hash, "credential")
        order.attach_mock(mock_integrations.create_integrations, "integrations")
        order.attach_mock(mock_gear.create_default_gear, "gear")
        order.attach_mock(identity.initialize_user_mfa, "mfa")
        order.attach_mock(mock_db.commit, "commit")
        user = users_schema.UsersCreate(
            name="N", username="n", email="n@example.com", active=True, access_type="regular", password="password123"
        )

        users_service.create_user(user, mock_db)

        names = [call[0] for call in order.mock_calls]
        assert names[-1] == "commit"
        assert names.count("commit") == 1
        assert {"user", "credential", "integrations", "gear", "mfa"} <= set(names[:-1])

    @patch("modules.users.users.service._stage_default_data", side_effect=RuntimeError("mfa down"))
    @patch(_CRUD)
    def test_a_failed_part_commits_nothing(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(3)
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)

        with pytest.raises(RuntimeError):
            users_service.create_signup_user(_signup(), settings, mock_db)

        mock_db.commit.assert_not_called()


class TestCreateSignupUser:
    def _settings(self, verification: bool, approval: bool):
        return MagicMock(signup_require_email_verification=verification, signup_require_admin_approval=approval)

    @pytest.mark.parametrize(
        ("verification", "approval", "active", "pending"),
        [
            (False, False, True, False),
            (True, False, False, False),
            (False, True, False, True),
            (True, True, False, True),
        ],
    )
    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    def test_account_state_follows_the_signup_policy(
        self, mock_crud, _defaults, verification, approval, active, pending, mock_db
    ):
        """A sign-up never proves the address, so it starts unverified whatever the policy.

        Only the verification link proves it; a verified flag set without it would let anyone pre-claim an
        address and receive the owner's later SSO sign-in through email auto-linking.
        """
        mock_crud.create_user.return_value = _user(3)

        users_service.create_signup_user(_signup(), self._settings(verification, approval), mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert (fields["active"], fields["email_verified"], fields["pending_admin_approval"]) == (
            active,
            False,
            pending,
        )
        assert fields["access_type"] == "regular"
        assert fields["username"] == "newuser"

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    def test_sso_account_gets_no_credential(self, mock_crud, _defaults, mock_db):
        identity = _identity()
        mock_crud.create_user.return_value = _user(3)

        users_service.create_signup_user(_signup(), self._settings(False, False), mock_db, False)

        identity.validate_and_hash_password_for_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    def test_sso_user_stages_without_committing(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(3)

        created = users_service.create_sso_user(_signup(), self._settings(False, False), mock_db, email_verified=True)

        assert created.id == 3
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_not_called()

    @pytest.mark.parametrize("email_verified", [True, False])
    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    def test_an_sso_account_is_verified_only_when_the_provider_says_so(
        self, mock_crud, _defaults, email_verified, mock_db
    ):
        mock_crud.create_user.return_value = _user(3)

        users_service.create_sso_user(_signup(), self._settings(False, False), mock_db, email_verified=email_verified)

        assert mock_crud.create_user.call_args.args[0]["email_verified"] is email_verified

    @patch(_CRUD)
    def test_duplicate_gives_an_abstract_conflict(self, mock_crud, mock_db):
        mock_crud.create_user.side_effect = core_exceptions.ConflictError("email taken")

        with pytest.raises(core_exceptions.ConflictError) as exc:
            users_service.create_signup_user(_signup(), self._settings(False, False), mock_db)

        assert exc.value.detail == "Unable to create user."
        mock_db.rollback.assert_called_once()


class TestStageDefaultData:
    @patch("modules.users.users.service.users_default_gear_integration")
    @patch("modules.users.users.service.health_targets_integration")
    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch("modules.users.users.service.user_integrations_integration")
    def test_stages_every_default_row_without_committing(
        self, mock_integrations, mock_privacy, mock_targets, mock_gear, mock_db
    ):
        identity = _identity()

        users_service._stage_default_data(5, mock_db)

        mock_integrations.create_integrations.assert_called_once_with(5, mock_db)
        mock_privacy.create_privacy_settings.assert_called_once_with(5, mock_db)
        mock_targets.create_health_targets.assert_called_once_with(5, mock_db)
        mock_gear.create_default_gear.assert_called_once_with(5, mock_db)
        mock_db.commit.assert_not_called()
        identity.initialize_user_mfa.assert_called_once_with(5)


@patch("modules.users.users.service.health_weight_integration")
@patch(_CRUD)
class TestEdits:
    def test_admin_edit_lowercases_and_drops_response_only_fields(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, height=170)
        mock_crud.update_user.return_value = _user(1, height=170)

        users_service.stage_user_edit(1, _edit(1, username="MixedCase", photo_path="/url"), mock_db, if_match="*")

        changes = mock_crud.update_user.call_args.args[1]
        assert changes["username"] == "mixedcase"
        assert "photo_path" not in changes
        assert "mfa_enabled" not in changes
        mock_weight.recalculate_bmi_for_user.assert_not_called()

    def test_admin_edit_recalculates_bmi_when_height_changes(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, height=170)
        mock_crud.update_user.return_value = _user(1, height=180)

        users_service.stage_user_edit(1, _edit(1, height=180), mock_db, if_match="*")

        mock_weight.recalculate_bmi_for_user.assert_called_once_with(1, 180.0, mock_db)

    def test_deactivating_a_user_revokes_their_pending_verification_links(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1, active=False)
        mock_crud.lock_active_admin_ids.return_value = [1, 2]

        with patch("modules.users.users.service.sign_up_tokens_integration.revoke_pending_tokens") as revoke:
            users_service.stage_user_edit(1, _edit(1, active=False), mock_db, if_match="*")

        revoke.assert_called_once_with(1, mock_db)

    def test_an_edit_that_leaves_the_user_active_keeps_their_verification_links(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1)

        with patch("modules.users.users.service.sign_up_tokens_integration.revoke_pending_tokens") as revoke:
            users_service.stage_user_edit(1, _edit(1), mock_db, if_match="*")

        revoke.assert_not_called()

    def test_edit_user_commits_and_reports_authentication(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1)
        identity = _identity()
        identity.get_identity_link_counts_for_users.return_value = {1: 2}
        identity.get_mfa_enabled_for_users.return_value = {1: True}

        result = users_service.edit_user(1, _edit(1), 9, mock_db, if_match="*")

        mock_db.commit.assert_called_once()
        assert result.external_auth_count == 2
        assert result.mfa_enabled is True

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            ({}, {"email": "other@example.com"}),
            ({}, {"access_type": "admin"}),
            ({}, {"active": False}),
            ({"access_type": "admin"}, {"access_type": "regular"}),
        ],
    )
    def test_a_security_relevant_edit_signs_the_user_out_in_the_same_commit(
        self, mock_crud, mock_weight, mock_db, before, after
    ):
        mock_crud.get_user_by_id.return_value = _user(1, **before)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(1, **{**before, **after})
        mock_crud.lock_active_admin_ids.return_value = [1, 2]
        identity = _identity()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(identity.delete_all_user_sessions, "revoke")

        users_service.edit_user(1, _edit(1, **{**before, **after}), 9, mock_db, if_match="*")

        assert [call[0] for call in order.mock_calls] == ["revoke", "commit"]
        _delete_all_sessions_mock.assert_called_once_with(1, mock_db)

    def test_a_requested_email_is_pending_and_the_stored_address_and_verified_flag_are_kept(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(1, email_verified=True)
        _identity()
        order = MagicMock()
        order.attach_mock(mock_crud.update_user, "edit")
        order.attach_mock(sign_up.request_email_change, "request")
        order.attach_mock(mock_db.commit, "commit")

        users_service.edit_user(1, _edit(1, email="Other@example.com", email_verified=False), 9, mock_db, if_match="*")

        assert [call[0] for call in order.mock_calls] == ["request", "edit", "commit"]
        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("user1@example.com", True)
        sign_up.request_email_change.assert_called_once_with(1, "other@example.com", "user1@example.com", mock_db)
        _delete_all_sessions_mock.assert_called_once_with(1, mock_db)

    def test_a_requested_email_is_checked_for_another_account_before_it_is_staged(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.get_user_by_email.return_value = _user(2, email="other@example.com")
        mock_crud.update_user.return_value = _user(1)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.edit_user(1, _edit(1, email="other@example.com"), 9, mock_db, if_match="*")

        sign_up.request_email_change.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_an_email_marked_verified_is_applied_now_and_cancels_a_pending_change(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1, email="other@example.com", email_verified=True)
        _identity()

        result = users_service.edit_user(
            1, _edit(1, email="other@example.com", email_verified=True), 9, mock_db, if_match="*"
        )

        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("other@example.com", True)
        sign_up.revoke_pending_tokens.assert_called_once_with(1, mock_db)
        sign_up.request_email_change.assert_not_called()
        assert result.email == "other@example.com"
        _delete_all_sessions_mock.assert_called_once_with(1, mock_db)

    def test_without_outgoing_mail_a_changed_email_is_applied_unverified(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(1, email="other@example.com", email_verified=False)
        sign_up.request_email_change.return_value = False
        _identity()

        result = users_service.edit_user(1, _edit(1, email="other@example.com"), 9, mock_db, if_match="*")

        mock_crud.update_user.assert_called_once()
        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("other@example.com", False)
        sign_up.revoke_pending_tokens.assert_called_once_with(1, mock_db)
        assert (result.email, result.email_verified) == ("other@example.com", False)
        mock_db.commit.assert_called_once()
        _delete_all_sessions_mock.assert_called_once_with(1, mock_db)

    def test_an_edit_that_keeps_the_email_never_touches_pending_changes(self, mock_crud, mock_weight, mock_db, sign_up):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1, name="Renamed")

        users_service.edit_user(1, _edit(1, name="Renamed"), 9, mock_db, if_match="*")

        sign_up.request_email_change.assert_not_called()
        sign_up.revoke_pending_tokens.assert_not_called()

    def test_the_response_carries_the_pending_email_change(self, mock_crud, mock_weight, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(1)
        sign_up.get_pending_email_changes.return_value = {
            1: sign_up_contracts.PendingEmailChange(email="other@example.com", expires_at=expires)
        }
        _identity()

        result = users_service.edit_user(1, _edit(1, email="other@example.com"), 9, mock_db, if_match="*")

        assert (result.pending_email, result.pending_email_expires_at) == ("other@example.com", expires)

    def test_an_edit_of_other_fields_keeps_the_sessions(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1, name="Renamed")

        users_service.edit_user(1, _edit(1, name="Renamed"), 9, mock_db, if_match="*")

        _delete_all_sessions_mock.assert_not_called()

    def test_an_administrator_editing_themselves_keeps_their_own_sessions(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin")
        mock_crud.update_user.return_value = _user(1, access_type="regular")
        mock_crud.lock_active_admin_ids.return_value = [1, 2]

        users_service.edit_user(1, _edit(1, access_type="regular"), 1, mock_db, if_match="*")

        _delete_all_sessions_mock.assert_not_called()

    def test_an_administrator_cannot_change_their_own_email_without_step_up(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)

        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.edit_user(1, _edit(1, email="other@example.com"), 1, mock_db, if_match="*")

        mock_crud.update_user.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_edit_user_conflict_rolls_back(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.side_effect = core_exceptions.ConflictError("dup")

        with pytest.raises(core_exceptions.ConflictError):
            users_service.edit_user(1, _edit(1), 9, mock_db, if_match="*")

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_profile_edit_keeps_only_allow_listed_fields(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1)
        profile = users_schema.ProfileUpdate.model_construct(
            name="New", username="MIXED", access_type="admin", active=False, email_verified=True
        )
        profile.__pydantic_fields_set__.update({"name", "username", "access_type", "active", "email_verified"})

        users_service.stage_profile_edit(1, profile, mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"name": "New", "username": "mixed"}

    def test_profile_edit_can_set_the_timezone(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1)

        users_service.stage_profile_edit(1, users_schema.ProfileUpdate(timezone="Europe/Lisbon"), mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"timezone": "Europe/Lisbon"}

    def test_profile_height_change_recalculates_bmi(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, height=170)
        mock_crud.update_user.return_value = _user(1, height=175)

        users_service.stage_profile_edit(1, users_schema.ProfileUpdate(height=175), mock_db, if_match="*")

        mock_weight.recalculate_bmi_for_user.assert_called_once_with(1, 175.0, mock_db)

    def test_profile_without_height_never_recalculates(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, height=170)
        mock_crud.update_user.return_value = _user(1, height=175)

        users_service.stage_profile_edit(1, users_schema.ProfileUpdate(name="Only"), mock_db, if_match="*")

        mock_weight.recalculate_bmi_for_user.assert_not_called()


@patch(_CRUD)
class TestApproveAndVerify:
    @pytest.fixture(autouse=True)
    def settings(self):
        with patch(_SETTINGS) as mock_settings:
            mock_settings.get_server_settings.return_value = MagicMock(signup_require_email_verification=True)
            yield mock_settings.get_server_settings.return_value

    def test_approve_activates_and_commits(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=True)
        with patch(
            "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email", return_value=True
        ) as mock_request:
            users_service.approve_user(1, mock_db)

        mock_crud.update_user.assert_called_once_with(1, {"pending_admin_approval": False, "active": True}, mock_db)
        mock_request.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_called_once()

    def test_approve_without_mail_is_still_approved(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=True)

        with patch(
            "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email", return_value=False
        ):
            users_service.approve_user(1, mock_db)

        mock_crud.update_user.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_approval_event_does_not_escape_a_failed_commit(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=True)
        mock_db.commit.side_effect = RuntimeError("commit failed")

        with (
            patch(
                "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email",
                return_value=True,
            ) as mock_request,
            pytest.raises(RuntimeError, match="commit failed"),
        ):
            users_service.approve_user(1, mock_db)

        mock_crud.update_user.assert_called_once()
        mock_request.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_called_once()

    def test_approve_refuses_an_unverified_email_while_verification_is_required(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=False)

        with pytest.raises(core_exceptions.InvalidInputError):
            users_service.approve_user(1, mock_db)

        mock_crud.update_user.assert_not_called()

    def test_approve_needs_no_verified_email_when_verification_is_off(self, mock_crud, mock_db, settings):
        """With approval alone no verification email is ever sent, so requiring one made approval impossible."""
        settings.signup_require_email_verification = False
        mock_crud.get_user_by_id.return_value = _user(1, email_verified=False)

        with patch("modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email"):
            users_service.approve_user(1, mock_db)

        mock_crud.update_user.assert_called_once_with(1, {"pending_admin_approval": False, "active": True}, mock_db)
        mock_db.commit.assert_called_once()

    def test_verification_activates_without_approval_policy(self, mock_crud, mock_db):
        mock_crud.is_deactivated.return_value = False
        users_service.stage_email_verification(1, MagicMock(signup_require_admin_approval=False), mock_db)

        assert mock_crud.update_user.call_args.args[1] == {
            "email_verified": True,
            "pending_admin_approval": False,
            "active": True,
        }
        mock_db.commit.assert_not_called()

    def test_verification_leaves_the_account_pending_under_approval_policy(self, mock_crud, mock_db):
        users_service.stage_email_verification(1, MagicMock(signup_require_admin_approval=True), mock_db)

        assert mock_crud.update_user.call_args.args[1] == {"email_verified": True}


class TestRequireDeletableUser:
    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_deletable_user(1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_the_only_administrator_cannot_be_deleted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [1]

        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_deletable_user(1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_an_administrator_can_be_deleted_while_another_remains(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [1, 2]

        users_service.require_deletable_user(1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_a_regular_user_can_be_deleted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)

        users_service.require_deletable_user(1, mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_a_stale_version_is_refused_before_the_administrator_check(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin", version=3)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_service.require_deletable_user(1, mock_db, if_match='"2"')

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_the_current_version_is_accepted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, version=3)

        users_service.require_deletable_user(1, mock_db, if_match='"3"')


class TestLastAdminIsProtected:
    @pytest.mark.parametrize(
        ("edit", "action"),
        [({"access_type": "regular"}, "demoted"), ({"active": False}, "deactivated")],
    )
    @patch(_CRUD)
    def test_the_only_administrator_cannot_be_demoted_or_deactivated(self, mock_crud, edit, action, mock_db):
        admin = _user(1, access_type="admin")
        mock_crud.get_user_by_id.return_value = admin
        mock_crud.lock_active_admin_ids.return_value = [1]

        with pytest.raises(core_exceptions.ConflictError, match=action):
            users_service.stage_user_edit(1, _edit(1, **{"access_type": "admin", **edit}), mock_db, if_match="*")

        mock_crud.update_user.assert_not_called()

    @patch("modules.users.users.service.health_weight_integration")
    @patch(_CRUD)
    def test_one_of_several_administrators_can_be_demoted(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [1, 2]
        mock_crud.update_user.return_value = _user(1)

        users_service.stage_user_edit(1, _edit(1, access_type="regular"), mock_db, if_match="*")

        mock_crud.update_user.assert_called_once()

    @patch("modules.users.users.service.health_weight_integration")
    @patch(_CRUD)
    def test_an_edit_that_keeps_the_admin_takes_no_lock(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="admin")
        mock_crud.update_user.return_value = _user(1)

        users_service.stage_user_edit(1, _edit(1, access_type="admin", name="Renamed"), mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_a_regular_user_is_never_locked_against(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, access_type="regular")
        mock_crud.update_user.return_value = _user(1)

        with patch("modules.users.users.service.health_weight_integration"):
            users_service.stage_user_edit(1, _edit(1, access_type="regular", active=False), mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()


class TestTimezone:
    @patch(_CRUD)
    def test_prefers_the_users_own_zone(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, timezone="Europe/Lisbon")

        assert users_service.resolve_user_timezone(1, mock_db) == "Europe/Lisbon"

    @patch("modules.users.users.service.core_timezone")
    @patch(_CRUD)
    def test_falls_back_to_the_server_zone(self, mock_crud, mock_tz, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_tz.or_default.side_effect = lambda tz: tz or "UTC"

        assert users_service.resolve_user_timezone(1, mock_db) == "UTC"

    @patch("modules.users.users.service.core_timezone")
    @patch(_CRUD)
    def test_falls_back_when_the_user_is_missing(self, mock_crud, mock_tz, mock_db):
        mock_crud.get_user_by_id.return_value = None
        mock_tz.or_default.side_effect = lambda tz: tz or "UTC"

        assert users_service.resolve_user_timezone(1, mock_db) == "UTC"

    @patch("modules.users.users.service.core_timezone")
    def test_today_is_resolved_in_the_resolved_zone(self, mock_tz, mock_db):
        with patch("modules.users.users.service.resolve_user_timezone", return_value="Pacific/Auckland"):
            result = users_service.user_local_today(1, mock_db)

        mock_tz.today_in.assert_called_once_with("Pacific/Auckland")
        assert result == mock_tz.today_in.return_value


class TestStageEmailChange:
    @patch(_CRUD)
    def test_stores_the_lower_cased_address_as_unverified(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email="old@example.com")

        changed = users_service.stage_email_change(1, "New@Example.COM", mock_db)

        assert changed is True
        mock_crud.update_user.assert_called_once_with(1, {"email": "new@example.com", "email_verified": False}, mock_db)

    @patch(_CRUD)
    def test_a_changed_address_revokes_the_users_unused_tokens(self, mock_crud, mock_db, sign_up):
        mock_crud.get_user_by_id.return_value = _user(1, email="old@example.com")

        users_service.stage_email_change(1, "new@example.com", mock_db)

        sign_up.revoke_pending_tokens.assert_called_once_with(1, mock_db)

    @patch(_CRUD)
    def test_resubmitting_the_current_address_keeps_it_verified(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1, email="same@example.com")

        changed = users_service.stage_email_change(1, "SAME@example.com", mock_db)

        assert changed is False
        mock_crud.update_user.assert_not_called()

    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_email_change(1, "a@example.com", mock_db)


class TestStageConfirmedEmailChange:
    @patch(_CRUD)
    def test_stores_the_lower_cased_address_as_verified(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = None

        users_service.stage_confirmed_email_change(1, "New@Example.COM", mock_db)

        mock_crud.get_user_by_email.assert_called_once_with("new@example.com", mock_db)
        mock_crud.update_user.assert_called_once_with(1, {"email": "new@example.com", "email_verified": True}, mock_db)

    @patch(_CRUD)
    def test_the_users_own_address_is_not_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(1, email="same@example.com")

        users_service.stage_confirmed_email_change(1, "same@example.com", mock_db)

        mock_crud.update_user.assert_called_once()

    @patch(_CRUD)
    def test_an_address_of_another_account_is_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(2, email="taken@example.com")

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_confirmed_email_change(1, "taken@example.com", mock_db)

        mock_crud.update_user.assert_not_called()


class TestAdminEditNormalizesIdentity:
    @patch("modules.users.users.service.health_weight_integration")
    @patch(_CRUD)
    def test_email_is_lower_cased_like_the_username(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(1)
        mock_crud.update_user.return_value = _user(1)

        users_service.stage_user_edit(1, _edit(1, username="Bob", email="Bob@Example.COM"), mock_db, if_match="*")

        changes = mock_crud.update_user.call_args.args[1]
        assert changes["username"] == "bob"
        assert changes["email"] == "bob@example.com"
