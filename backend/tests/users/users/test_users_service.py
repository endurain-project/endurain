"""Tests for users.users.service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import pytest
from pydantic import TypeAdapter

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.schema as auth_schema
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
import modules.users.users.router as users_router
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_SID_9 = uuid.UUID(int=109)
_U1, _U2, _U3, _U4, _U5, _U7, _U8, _U9 = (uuid.UUID(int=n) for n in (1, 2, 3, 4, 5, 7, 8, 9))

_CRUD = "modules.users.users.service.users_crud"
_SETTINGS = "modules.users.users.service.server_settings_integration"


def _user(user_id: uuid.UUID = _U1, **overrides) -> users_schema.UserRead:
    fields = {
        "id": user_id,
        "name": "User",
        "username": f"user{user_id.int}",
        "email": f"user{user_id.int}@example.com",
        "active": True,
        "access_type": "regular",
    }
    fields.update(overrides)
    return users_schema.UserRead(**fields)


def _edit(user_id: uuid.UUID = _U1, **overrides) -> users_schema.UserEdit:
    return users_schema.UserEdit.from_read(_user(user_id, **overrides))


def _signup(*, with_password: bool = True) -> users_schema.UserSignup:
    return users_schema.UserSignup(
        name="New",
        username="NewUser",
        email="New@Example.com",
        password="SecurePass1!" if with_password else None,
        preferred_language="en",
    )


def _profile(**overrides) -> users_schema.UserBase:
    return users_schema.UserBase(name="New", username="NewUser", email="New@Example.com", **overrides)


_auth_service_mock: MagicMock | None = None
_delete_all_sessions_mock: MagicMock
_verify_step_up_mock: MagicMock


def _admin_edit(user_id, edit, actor_id, db, *, step_up=None, store=None):
    """Edit as an administrator whose session is ``sid-9``."""
    return users_service.edit_user(user_id, edit, step_up, actor_id, _SID_9, store or MagicMock(), db, if_match="*")


def _admin_create(user, db, *, step_up=None, store=None):
    """Create as an administrator whose session is ``sid-9``."""
    return users_service.create_user(user, step_up, _U9, _SID_9, store or MagicMock(), db)


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
        integration.get_email_reserver_id.return_value = None
        integration.request_email_change.return_value = True
        yield integration


@pytest.fixture(autouse=True)
def generation():
    """Replace the security-generation boundary."""
    with patch("modules.users.users.service.security_generation_integration") as integration:
        yield integration


@pytest.fixture(autouse=True)
def password_reset():
    """Replace the password-reset-token boundary."""
    with patch("modules.users.users.service.password_reset_tokens_integration") as integration:
        yield integration


@pytest.fixture(autouse=True)
def _auth_integration_mocks(monkeypatch):
    """Mock auth integration boundaries while preserving each test's configured values."""
    global _auth_service_mock
    global _delete_all_sessions_mock
    global _verify_step_up_mock
    _auth_service_mock = None
    _delete_all_sessions_mock = MagicMock()
    _verify_step_up_mock = MagicMock()
    monkeypatch.setattr(account_security_integration, "verify_step_up", _verify_step_up_mock)

    def mock_call(name, *args, **kwargs):
        if _auth_service_mock is None:
            return {}
        return getattr(_auth_service_mock, name)(*args, **kwargs)

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
    monkeypatch.setattr(credentials_integration, "reject_breached_password", lambda settings, password, db: None)
    monkeypatch.setattr(
        credentials_integration,
        "validate_and_hash_password_for_user",
        lambda settings, access_type, password, db, **account: mock_call(
            "validate_and_hash_password_for_user", settings, access_type, password, **account
        ),
    )
    monkeypatch.setattr(
        credentials_integration,
        "set_local_password_hash",
        lambda user_id, password_hash, db, *, change_required: mock_call(
            "set_local_password_hash", user_id, password_hash, change_required
        ),
    )
    _delete_all_sessions_mock.side_effect = lambda user_id, db: mock_call("delete_all_user_sessions", user_id)
    monkeypatch.setattr(account_security_integration, "delete_all_user_sessions", _delete_all_sessions_mock)


class TestRequirements:
    @patch(_CRUD)
    def test_require_user_returns_the_user(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user()

        assert users_service.require_user(_U1, mock_db).id == _U1

    @patch(_CRUD)
    def test_require_user_missing_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user(_U1, mock_db)

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
            users_service.get_public_user(_U1, mock_db)
        mock_crud.get_user_by_id.assert_not_called()

    @patch(_CRUD)
    @patch(_SETTINGS)
    def test_hidden_when_user_info_sharing_is_off(self, mock_settings, mock_crud, mock_db):
        mock_settings.get_server_settings.return_value = MagicMock(
            public_shareable_links=True, public_shareable_links_user_info=False
        )

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_user(_U1, mock_db)

    @patch(_CRUD)
    @patch(_SETTINGS)
    def test_visible_when_both_are_on(self, mock_settings, mock_crud, mock_db):
        mock_settings.get_server_settings.return_value = MagicMock(
            public_shareable_links=True, public_shareable_links_user_info=True
        )

        mock_crud.get_user_by_id.return_value = _user(_U1, email="private@example.com")

        public = users_service.get_public_user(_U1, mock_db)

        assert isinstance(public, users_schema.UserPublicRead)
        assert public.id == _U1


class TestListPublicProfiles:
    @patch(_CRUD)
    def test_keys_the_public_projection_by_user_id(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [_user(_U3, city="Porto"), _user(_U5)]

        profiles = users_service.list_public_profiles({_U3, _U5}, mock_db)

        assert set(profiles) == {_U3, _U5}
        assert all(type(profile) is users_schema.UserPublicRead for profile in profiles.values())
        assert profiles[_U3].city == "Porto"
        mock_crud.get_users_by_ids.assert_called_once_with({_U3, _U5}, mock_db)

    @patch(_CRUD)
    def test_leaves_out_users_a_viewer_could_not_look_up(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [
            _user(_U1),
            _user(_U2, active=False),
            _user(_U3, pending_admin_approval=True),
        ]

        assert set(users_service.list_public_profiles({_U1, _U2, _U3}, mock_db)) == {_U1}

    @patch(_CRUD)
    def test_carries_no_personal_or_account_fields(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = [_user(_U3, birthdate="1990-01-01")]

        dumped = users_service.list_public_profiles({_U3}, mock_db)[_U3].model_dump()

        assert set(dumped) == {"id", "name", "username", "city", "photo_path"}

    @patch(_CRUD)
    def test_no_users_found_is_an_empty_mapping(self, mock_crud, mock_db):
        mock_crud.get_users_by_ids.return_value = []

        assert users_service.list_public_profiles({7}, mock_db) == {}


class TestPublicProjection:
    @patch(_CRUD)
    def test_carries_no_personal_or_account_fields(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U3, city="Porto", birthdate="1990-01-01")

        dumped = users_service.get_public_profile(_U3, mock_db).model_dump()

        assert set(dumped) == {"id", "name", "username", "city", "photo_path"}

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    @patch(_CRUD)
    def test_an_inactive_or_pending_account_is_not_found(self, mock_crud, state, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U3, **state)

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_profile(_U3, mock_db)

    @patch(_CRUD)
    def test_an_active_account_is_returned(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U3)

        assert users_service.get_public_profile(_U3, mock_db).id == _U3

    @patch(_CRUD)
    def test_missing_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_profile(_U3, mock_db)

    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch(_CRUD)
    def test_public_list_is_paged_and_projected(self, mock_crud, mock_privacy, mock_db):
        mock_privacy.list_undiscoverable_user_ids.return_value = []
        mock_crud.get_users_with_pagination.return_value = [_user(_U1), _user(_U2)]
        mock_crud.get_users_number.return_value = 30

        found = users_service.list_public_users(core_pagination.PageParams(2, 25), mock_db, username_contains="user")

        assert [type(user) for user in found.items] == [users_schema.UserPublicRead] * 2
        assert (found.total, found.page, found.next) == (30, 2, None)
        filters = {
            "active": True,
            "pending_approval": False,
            "username": None,
            "username_contains": "user",
            "exclude_user_ids": [],
        }
        mock_crud.get_users_with_pagination.assert_called_once_with(mock_db, 2, 25, **filters)
        mock_crud.get_users_number.assert_called_once_with(mock_db, **filters)

    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch(_CRUD)
    def test_public_list_leaves_out_users_who_opted_out_of_search_and_their_count(
        self, mock_crud, mock_privacy, mock_db
    ):
        mock_privacy.list_undiscoverable_user_ids.return_value = [_U7, _U8]
        mock_crud.get_users_with_pagination.return_value = []
        mock_crud.get_users_number.return_value = 0

        users_service.list_public_users(core_pagination.PageParams(1, 25), mock_db, username="user")

        assert mock_crud.get_users_with_pagination.call_args.kwargs["exclude_user_ids"] == [_U7, _U8]
        assert mock_crud.get_users_number.call_args.kwargs["exclude_user_ids"] == [_U7, _U8]
        assert mock_crud.get_users_number.call_args.kwargs["username"] == "user"


class TestListUsers:
    @patch(_CRUD)
    def test_enriches_each_user_with_the_authentication_status(self, mock_crud, mock_db):
        mock_crud.get_users_number.return_value = 2
        mock_crud.get_users_with_pagination.return_value = [_user(_U1, name="Alice"), _user(_U2, name="Bob")]
        identity = _identity()
        identity.get_identity_link_counts_for_users.return_value = {_U1: 2}
        identity.get_mfa_enabled_for_users.return_value = {_U2: True}

        result = users_service.list_users(mock_db, page_number=1, num_records=10)

        assert result.total == 2
        assert [(u.name, u.external_auth_count, u.mfa_enabled) for u in result.items] == [
            ("Alice", 2, False),
            ("Bob", 0, True),
        ]

    @patch(_CRUD)
    def test_the_page_keeps_the_full_records_through_the_routes_response_model(self, mock_crud, mock_db):
        mock_crud.get_users_number.return_value = 1
        mock_crud.get_users_with_pagination.return_value = [_user(_U1)]
        _identity()
        list_route = next(r for r in users_router.router.routes if r.path == "" and "GET" in r.methods)
        adapter = TypeAdapter(list_route.response_model)

        page = adapter.dump_python(adapter.validate_python(users_service.list_users(mock_db)))

        assert page["items"][0]["email"] == _user(_U1).email


class TestPendingEmailChanges:
    @patch(_CRUD)
    def test_the_list_carries_each_users_pending_change_from_one_lookup(self, mock_crud, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_users_number.return_value = 2
        mock_crud.get_users_with_pagination.return_value = [_user(_U1), _user(_U2)]
        sign_up.get_pending_email_changes.return_value = {
            _U2: sign_up_contracts.PendingEmailChange(email="next@example.com", expires_at=expires)
        }

        result = users_service.list_users(mock_db)

        sign_up.get_pending_email_changes.assert_called_once_with([_U1, _U2], mock_db)
        assert [(u.pending_email, u.pending_email_expires_at) for u in result.items] == [
            (None, None),
            ("next@example.com", expires),
        ]

    @patch(_CRUD)
    def test_an_admin_read_carries_the_pending_change(self, mock_crud, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_user_by_id.return_value = _user(_U4)
        sign_up.get_pending_email_changes.return_value = {
            _U4: sign_up_contracts.PendingEmailChange(email="next@example.com", expires_at=expires)
        }

        user = users_service.require_user_with_pending_email(_U4, mock_db)

        assert (user.pending_email, user.pending_email_expires_at) == ("next@example.com", expires)

    @patch(_CRUD)
    def test_an_admin_read_of_a_missing_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user_with_pending_email(_U4, mock_db)

    def test_an_edit_built_from_a_read_leaves_the_pending_change_out(self):
        read = _user(_U1, pending_email="next@example.com", pending_email_expires_at=datetime(2030, 1, 1, tzinfo=UTC))

        edit = users_schema.UserEdit.from_read(read)

        assert "pending_email" not in edit.model_dump()
        assert "pending_email_expires_at" not in edit.model_dump()

    def test_an_edit_built_from_a_read_leaves_the_deletion_marker_out(self):
        read = _user(_U1, deletion_requested_at=datetime(2030, 1, 1, tzinfo=UTC))

        edit = users_schema.UserEdit.from_read(read)

        assert "deletion_requested_at" not in edit.model_dump()


@pytest.mark.usefixtures("real_email_availability")
class TestRequireEmailAvailable:
    @patch(_CRUD)
    def test_another_accounts_address_is_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(_U2)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_email_available(_U1, "User2@Example.com", mock_db)

        mock_crud.get_user_by_email.assert_called_once_with("user2@example.com", mock_db)

    @patch(_CRUD)
    @pytest.mark.parametrize("holder", [None, _U1])
    def test_a_free_address_or_the_users_own_passes(self, mock_crud, mock_db, holder):
        mock_crud.get_user_by_email.return_value = _user(holder) if holder else None

        users_service.require_email_available(_U1, "a@example.com", mock_db)


class TestCreateUser:
    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_hashes_creates_commits_then_stores_the_credential(self, mock_crud, mock_settings, mock_defaults, mock_db):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7)
        user = users_schema.UserCreate(
            name="N",
            username="NewUser",
            email="New@Example.com",
            active=True,
            access_type="regular",
            password="password123",
        )

        created = _admin_create(user, mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert fields["username"] == "newuser" and fields["email"] == "new@example.com"
        assert "password" not in fields
        mock_db.commit.assert_called_once()
        # An administrator knows the password they set, so the user must change it at the next sign-in.
        identity.set_local_password_hash.assert_called_once_with(_U7, "hash", True)
        mock_defaults.assert_called_once_with(_U7, mock_db)
        assert created.id == _U7

    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_duplicate_rolls_back_and_stores_no_credential(self, mock_crud, mock_settings, mock_db):
        identity = _identity()
        mock_crud.create_user.side_effect = core_exceptions.ConflictError("dup")
        user = users_schema.UserCreate(
            name="N", username="n", email="n@example.com", active=True, access_type="regular", password="password123"
        )

        with pytest.raises(core_exceptions.ConflictError):
            _admin_create(user, mock_db)

        mock_db.rollback.assert_called_once()
        identity.set_local_password_hash.assert_not_called()


class TestCreateInvitedUser:
    def _new(self, **overrides) -> users_schema.UserCreate:
        fields = {
            "name": "N",
            "username": "NewUser",
            "email": "New@Example.com",
            "active": True,
            "access_type": "regular",
        }
        fields.update(overrides)
        return users_schema.UserCreate(**fields)

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_without_a_password_the_account_has_no_credential_and_the_invitation_is_staged(
        self, mock_crud, mock_settings, mock_defaults, mock_db, sign_up
    ):
        identity = _identity()
        mock_settings.is_mail_configured.return_value = True
        mock_crud.create_user.return_value = _user(_U7)

        created = _admin_create(self._new(), mock_db)

        identity.set_local_password_hash.assert_not_called()
        identity.reject_breached_password.assert_not_called()
        identity.validate_and_hash_password_for_user.assert_not_called()
        sign_up.request_admin_invitation_email.assert_called_once_with(_U7, mock_db)
        mock_db.commit.assert_called_once()
        assert created.id == _U7

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_without_mail_a_missing_password_is_refused_before_anything_is_staged(
        self, mock_crud, mock_settings, mock_defaults, mock_db, sign_up
    ):
        identity = _identity()
        mock_settings.is_mail_configured.return_value = False

        with pytest.raises(core_exceptions.PasswordRequiredError):
            _admin_create(self._new(), mock_db)

        mock_crud.create_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()
        sign_up.request_admin_invitation_email.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_administrator_invitation_is_still_verified_with_the_step_up(
        self, mock_crud, mock_settings, mock_defaults, mock_db, sign_up
    ):
        _identity()
        mock_settings.is_mail_configured.return_value = True
        mock_crud.create_user.return_value = _user(_U7, access_type="admin")
        step_up = auth_schema.StepUpVerification(current_password="admin-password")

        _admin_create(self._new(access_type="admin"), mock_db, step_up=step_up)

        _verify_step_up_mock.assert_called_once()
        sign_up.request_admin_invitation_email.assert_called_once_with(_U7, mock_db)

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_password_is_set_as_before_even_when_mail_is_configured(
        self, mock_crud, mock_settings, mock_defaults, mock_db, sign_up
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_settings.is_mail_configured.return_value = True
        mock_crud.create_user.return_value = _user(_U7)

        _admin_create(self._new(password="password123"), mock_db)

        identity.set_local_password_hash.assert_called_once_with(_U7, "hash", True)
        sign_up.request_admin_invitation_email.assert_not_called()


class TestCreateUserStepUp:
    def _new(self, access_type: str) -> users_schema.UserCreate:
        return users_schema.UserCreate(
            name="N",
            username="newadmin",
            email="new@example.com",
            active=True,
            access_type=access_type,
            password="password123",
        )

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_administrator_account_needs_the_step_up_of_the_creating_administrator(
        self, mock_crud, mock_settings, mock_defaults, mock_db
    ):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7, access_type="admin")
        store = MagicMock()
        step_up = auth_schema.StepUpVerification(current_password="admin-password")
        order = MagicMock()
        order.attach_mock(_verify_step_up_mock, "step_up")
        order.attach_mock(mock_crud.create_user, "insert")

        _admin_create(self._new("admin"), mock_db, step_up=step_up, store=store)

        assert [call[0] for call in order.mock_calls] == ["step_up", "insert"]
        _verify_step_up_mock.assert_called_once_with(
            step_up, _U9, _SID_9, identity_providers_constants.StepUpAction.ADMIN_USER_CREATE, store, mock_db
        )

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_the_access_type_is_read_as_an_enum_member_too(self, mock_crud, mock_settings, mock_defaults, mock_db):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7, access_type="admin")

        _admin_create(self._new(users_schema.UserAccessType.ADMIN), mock_db)

        _verify_step_up_mock.assert_called_once()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_missing_step_up_is_verified_as_empty_credentials(self, mock_crud, mock_settings, mock_defaults, mock_db):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7, access_type="admin")

        _admin_create(self._new("admin"), mock_db)

        assert _verify_step_up_mock.call_args.args[0] == auth_schema.StepUpVerification()

    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_a_failed_step_up_creates_nothing(self, mock_crud, mock_settings, mock_db):
        identity = _identity()
        _verify_step_up_mock.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        with pytest.raises(core_exceptions.PermissionDeniedError):
            _admin_create(self._new("admin"), mock_db)

        mock_crud.create_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_regular_account_needs_no_step_up(self, mock_crud, mock_settings, mock_defaults, mock_db):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7)

        _admin_create(self._new("regular"), mock_db)

        _verify_step_up_mock.assert_not_called()
        mock_db.commit.assert_called_once()


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
    @pytest.mark.usefixtures("email_available")
    def test_locks_before_it_checks_and_checks_before_it_inserts(
        self, mock_crud, mock_settings, mock_defaults, mock_db
    ):
        _identity().validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.any_user_exists.return_value = False
        mock_crud.create_user.return_value = _user(_U1, access_type="admin")
        order = MagicMock()
        order.attach_mock(mock_crud.lock_first_admin_creation, "lock")
        order.attach_mock(mock_crud.any_user_exists, "check")
        order.attach_mock(mock_crud.create_user, "insert")

        users_service.stage_first_admin(self._admin(), mock_db)

        assert [call[0] for call in order.mock_calls] == ["lock", "check", "insert"]

    @patch("modules.users.users.service._stage_default_data")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_stages_an_active_verified_admin_with_the_admin_password_policy_and_does_not_commit(
        self, mock_crud, mock_settings, mock_defaults, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.any_user_exists.return_value = False
        mock_crud.create_user.return_value = _user(_U1, access_type="admin")

        created = users_service.stage_first_admin(self._admin(), mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert fields["access_type"] == "admin"
        assert fields["active"] is True
        assert fields["email_verified"] is True
        assert "pending_admin_approval" not in fields
        assert "deactivated_at" not in fields
        assert (fields["preferred_language"], fields["gender"], fields["units"]) == ("en", "unspecified", "metric")
        assert fields["username"] == "owner" and fields["email"] == "owner@example.com"
        assert "password" not in fields
        assert identity.validate_and_hash_password_for_user.call_args.args[1] == "admin"
        assert identity.validate_and_hash_password_for_user.call_args.kwargs == {
            "username": "Owner",
            "email": "Owner@example.com",
        }
        # The first administrator chose their own password.
        identity.set_local_password_hash.assert_called_once_with(_U1, "hash", False)
        mock_defaults.assert_called_once_with(_U1, mock_db)
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_not_called()
        assert created.id == _U1

    @patch(_SETTINGS)
    @patch(_CRUD)
    def test_a_weak_password_surfaces_the_credentials_error_and_inserts_nothing(
        self, mock_crud, mock_settings, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.side_effect = credentials_contracts.PasswordTooShortError()
        mock_crud.any_user_exists.return_value = False

        with pytest.raises(credentials_contracts.PasswordPolicyError):
            users_service.stage_first_admin(self._admin(), mock_db)

        mock_crud.create_user.assert_not_called()

    def test_an_account_created_without_the_flag_is_not_pending(self):
        assert users_models.Users.__table__.c.pending_admin_approval.default.arg is False

    def test_the_request_shape_carries_no_access_type_or_account_state(self):
        for field in ("access_type", "active", "email_verified", "pending_admin_approval"):
            with pytest.raises(ValueError):
                users_schema.FirstAdminCreate(
                    name="O", username="o", email="o@example.com", password="SecurePass1!", **{field: True}
                )


class TestAccountCreationIsOneUnit:
    """The user row, credential, MFA row and default rows commit together, once, last."""

    @patch("modules.users.users.service.users_default_gear_integration")
    @patch("modules.users.users.service.users_contributor_registry")
    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch("modules.users.users.service.user_integrations_integration")
    @patch(_SETTINGS)
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_commit_follows_every_staged_write(
        self, mock_crud, mock_settings, mock_integrations, mock_privacy, mock_targets, mock_gear, mock_db
    ):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hash"
        mock_crud.create_user.return_value = _user(_U7)
        order = MagicMock()
        order.attach_mock(mock_crud.create_user, "user")
        order.attach_mock(identity.set_local_password_hash, "credential")
        order.attach_mock(mock_integrations.create_integrations, "integrations")
        order.attach_mock(mock_gear.create_default_gear, "gear")
        order.attach_mock(mock_db.commit, "commit")
        user = users_schema.UserCreate(
            name="N", username="n", email="n@example.com", active=True, access_type="regular", password="password123"
        )

        _admin_create(user, mock_db)

        names = [call[0] for call in order.mock_calls]
        assert names[-1] == "commit"
        assert names.count("commit") == 1
        assert {"user", "credential", "integrations", "gear"} <= set(names[:-1])

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_sign_up_stages_the_account_and_leaves_the_commit_to_the_caller(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(_U3)
        settings = MagicMock(signup_require_email_verification=True, signup_require_admin_approval=False)

        users_service.stage_signup_user(_signup(with_password=False), settings, mock_db)

        mock_db.commit.assert_not_called()

    @patch("modules.users.users.service._stage_default_data", side_effect=RuntimeError("mfa down"))
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_failed_part_commits_nothing(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(_U3)
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)

        with pytest.raises(RuntimeError):
            users_service.stage_signup_user(_signup(), settings, mock_db)

        mock_db.commit.assert_not_called()


class TestCreateSignupUser:
    def _settings(self, verification: bool, approval: bool):
        return MagicMock(
            signup_require_email_verification=verification,
            signup_require_admin_approval=approval,
            units="imperial",
            currency="dollar",
        )

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
    @pytest.mark.usefixtures("email_available")
    def test_account_state_follows_the_signup_policy(
        self, mock_crud, _defaults, verification, approval, active, pending, mock_db
    ):
        """A sign-up never proves the address, so it starts unverified whatever the policy.

        Only the verification link proves it; a verified flag set without it would let anyone pre-claim an
        address and receive the owner's later SSO sign-in through email auto-linking.
        """
        mock_crud.create_user.return_value = _user(_U3)

        users_service.stage_signup_user(_signup(), self._settings(verification, approval), mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert (fields["active"], fields["email_verified"], fields["pending_admin_approval"]) == (
            active,
            False,
            pending,
        )
        assert fields["access_type"] == "regular"
        assert fields["username"] == "newuser"

    @pytest.mark.parametrize(
        ("verification", "approval", "active", "pending"),
        [
            (False, False, True, False),
            (True, False, True, False),
            (False, True, False, True),
            (True, True, False, True),
        ],
    )
    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_address_the_provider_verified_meets_the_verification_policy(
        self, mock_crud, _defaults, verification, approval, active, pending, mock_db
    ):
        """No verification link is sent for a proven address, so only approval can keep the account inactive."""
        mock_crud.create_user.return_value = _user(_U3)

        users_service.create_sso_user(_profile(), self._settings(verification, approval), mock_db, email_verified=True)

        fields = mock_crud.create_user.call_args.args[0]
        assert (fields["active"], fields["email_verified"], fields["pending_admin_approval"]) == (active, True, pending)

    @pytest.mark.parametrize("pending", [True, False])
    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_sso_account_awaiting_approval_asks_the_administrators_for_it(
        self, mock_crud, _defaults, pending, sign_up, mock_db
    ):
        """It has nothing left to verify, so the administrators are asked now, as a verified sign-up's are."""
        mock_crud.create_user.return_value = _user(
            _U3, active=not pending, email_verified=True, pending_admin_approval=pending
        )

        users_service.create_sso_user(_profile(), self._settings(False, pending), mock_db, email_verified=True)

        if pending:
            sign_up.request_sign_up_admin_approval.assert_called_once_with(_U3, mock_db)
        else:
            sign_up.request_sign_up_admin_approval.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_sso_account_gets_no_credential(self, mock_crud, _defaults, mock_db):
        identity = _identity()
        mock_crud.create_user.return_value = _user(_U3)

        users_service.create_sso_user(_profile(), self._settings(False, False), mock_db, email_verified=True)

        identity.validate_and_hash_password_for_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_supplied_password_is_hashed_and_stored(self, mock_crud, _defaults, mock_db):
        identity = _identity()
        identity.validate_and_hash_password_for_user.return_value = "hashed"
        mock_crud.create_user.return_value = _user(_U3)

        users_service.stage_signup_user(_signup(), self._settings(False, False), mock_db)

        identity.set_local_password_hash.assert_called_once()
        assert identity.set_local_password_hash.call_args.args == (_U3, "hashed", False)

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_sign_up_without_a_password_stores_no_credential(self, mock_crud, _defaults, mock_db):
        identity = _identity()
        mock_crud.create_user.return_value = _user(_U3)

        users_service.stage_signup_user(_signup(with_password=False), self._settings(True, False), mock_db)

        identity.validate_and_hash_password_for_user.assert_not_called()
        identity.set_local_password_hash.assert_not_called()

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_sso_user_stages_without_committing(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(_U3)

        created = users_service.create_sso_user(_profile(), self._settings(False, False), mock_db, email_verified=True)

        assert created.id == _U3
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_not_called()

    @pytest.mark.parametrize("email_verified", [True, False])
    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_sso_account_is_verified_only_when_the_provider_says_so(
        self, mock_crud, _defaults, email_verified, mock_db
    ):
        mock_crud.create_user.return_value = _user(_U3)

        users_service.create_sso_user(_profile(), self._settings(False, False), mock_db, email_verified=email_verified)

        assert mock_crud.create_user.call_args.args[0]["email_verified"] is email_verified

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_sign_up_starts_from_the_default_profile_and_the_server_units(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(_U3)

        users_service.stage_signup_user(_signup(), self._settings(False, False), mock_db)

        fields = mock_crud.create_user.call_args.args[0]
        assert (fields["units"], fields["currency"]) == ("imperial", "dollar")
        assert (fields["preferred_language"], fields["gender"], fields["first_day_of_week"]) == (
            "en",
            "unspecified",
            "monday",
        )
        assert (fields["city"], fields["birthdate"], fields["height"]) == (None, None, None)
        assert "password" not in fields

    @patch("modules.users.users.service._stage_default_data")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_an_sso_account_keeps_its_mapped_profile_and_takes_the_server_units(self, mock_crud, _defaults, mock_db):
        mock_crud.create_user.return_value = _user(_U3)

        users_service.create_sso_user(
            _profile(city="Lisbon", height=180), self._settings(False, False), mock_db, email_verified=True
        )

        fields = mock_crud.create_user.call_args.args[0]
        assert (fields["city"], fields["height"]) == ("Lisbon", 180)
        assert (fields["units"], fields["currency"]) == ("imperial", "dollar")
        assert fields["username"] == "newuser" and fields["email"] == "new@example.com"

    @patch(_CRUD)
    def test_duplicate_gives_an_abstract_conflict(self, mock_crud, mock_db):
        mock_crud.create_user.side_effect = core_exceptions.ConflictError("email taken")

        with pytest.raises(core_exceptions.ConflictError) as exc:
            users_service.stage_signup_user(_signup(), self._settings(False, False), mock_db)

        assert exc.value.detail == "Unable to create user."
        mock_db.rollback.assert_not_called()


class TestStageDefaultData:
    @patch("modules.users.users.service.users_default_gear_integration")
    @patch("modules.users.users.service.users_contributor_registry")
    @patch("modules.users.users.service.users_privacy_settings_integration")
    @patch("modules.users.users.service.user_integrations_integration")
    def test_stages_every_default_row_without_committing(
        self, mock_integrations, mock_privacy, mock_targets, mock_gear, mock_db
    ):
        users_service._stage_default_data(_U5, mock_db)

        mock_integrations.create_integrations.assert_called_once_with(_U5, mock_db)
        mock_privacy.create_privacy_settings.assert_called_once_with(_U5, mock_db)
        mock_targets.lifecycle_hooks.return_value.stage_new_user.assert_called_once_with(_U5, mock_db)
        mock_gear.create_default_gear.assert_called_once_with(_U5, mock_db)
        mock_db.commit.assert_not_called()


@patch("modules.users.users.service.users_contributor_registry")
@patch(_CRUD)
class TestEdits:
    def test_admin_edit_lowercases_and_drops_response_only_fields(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, height=170)
        mock_crud.update_user.return_value = _user(_U1, height=170)

        users_service.stage_user_edit(_U1, _edit(_U1, username="MixedCase", photo_path="/url"), mock_db, if_match="*")

        changes = mock_crud.update_user.call_args.args[1]
        assert changes["username"] == "mixedcase"
        assert "photo_path" not in changes
        assert "mfa_enabled" not in changes
        mock_weight.lifecycle_hooks.return_value.stage_height_change.assert_not_called()

    def test_admin_edit_recalculates_bmi_when_height_changes(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, height=170)
        mock_crud.update_user.return_value = _user(_U1, height=180)

        users_service.stage_user_edit(_U1, _edit(_U1, height=180), mock_db, if_match="*")

        mock_weight.lifecycle_hooks.return_value.stage_height_change.assert_called_once_with(_U1, 180.0, mock_db)

    def test_deactivating_a_user_revokes_their_pending_verification_links(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]

        with patch("modules.users.users.service.sign_up_tokens_integration.revoke_pending_tokens") as revoke:
            users_service.stage_user_edit(_U1, _edit(_U1, active=False), mock_db, if_match="*")

        revoke.assert_called_once_with(_U1, mock_db)

    def test_an_edit_that_leaves_the_user_active_keeps_their_verification_links(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1)

        with patch("modules.users.users.service.sign_up_tokens_integration.revoke_pending_tokens") as revoke:
            users_service.stage_user_edit(_U1, _edit(_U1), mock_db, if_match="*")

        revoke.assert_not_called()

    def test_edit_user_commits_and_reports_authentication(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1)
        identity = _identity()
        identity.get_identity_link_counts_for_users.return_value = {_U1: 2}
        identity.get_mfa_enabled_for_users.return_value = {_U1: True}

        result = _admin_edit(_U1, _edit(_U1), _U9, mock_db)

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
        mock_crud.get_user_by_id.return_value = _user(_U1, **before)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, **{**before, **after})
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        identity = _identity()
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(identity.delete_all_user_sessions, "revoke")

        _admin_edit(_U1, _edit(_U1, **{**before, **after}), _U9, mock_db)

        assert [call[0] for call in order.mock_calls] == ["revoke", "commit"]
        _delete_all_sessions_mock.assert_called_once_with(_U1, mock_db)

    def test_a_requested_email_is_pending_and_the_stored_address_and_verified_flag_are_kept(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, email_verified=True)
        _identity()
        order = MagicMock()
        order.attach_mock(mock_crud.update_user, "edit")
        order.attach_mock(sign_up.request_email_change, "request")
        order.attach_mock(mock_db.commit, "commit")

        _admin_edit(_U1, _edit(_U1, email="Other@example.com", email_verified=False), _U9, mock_db)

        assert [call[0] for call in order.mock_calls] == ["request", "edit", "commit"]
        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("user1@example.com", True)
        sign_up.request_email_change.assert_called_once_with(_U1, "other@example.com", "user1@example.com", mock_db)
        _delete_all_sessions_mock.assert_called_once_with(_U1, mock_db)

    def test_a_requested_email_with_a_deactivation_bumps_before_the_token_is_written(
        self, mock_crud, mock_weight, mock_db, sign_up, generation
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, email_verified=True, active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        _identity()
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        order.attach_mock(sign_up.request_email_change, "request")

        _admin_edit(_U1, _edit(_U1, email="Other@example.com", email_verified=False, active=False), _U9, mock_db)

        names = [call[0] for call in order.mock_calls]
        assert names.index("bump") < names.index("request")

    @pytest.mark.usefixtures("real_email_availability")
    def test_a_requested_email_is_checked_for_another_account_before_it_is_staged(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.get_user_by_email.return_value = _user(_U2, email="other@example.com")
        mock_crud.update_user.return_value = _user(_U1)

        with pytest.raises(core_exceptions.ConflictError):
            _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U9, mock_db)

        sign_up.request_email_change.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    @pytest.mark.usefixtures("email_available")
    def test_an_email_marked_verified_is_applied_now_and_cancels_a_pending_change(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com", email_verified=True)
        _identity()

        with patch(_SETTINGS) as mock_settings:
            mock_settings.is_mail_configured.return_value = True
            result = _admin_edit(_U1, _edit(_U1, email="Other@Example.com", email_verified=True), _U9, mock_db)

        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("other@example.com", True)
        sign_up.stage_email_changed_notice.assert_called_once_with(
            _U1, "other@example.com", "user1@example.com", mock_db
        )
        sign_up.revoke_pending_tokens.assert_not_called()
        sign_up.request_email_change.assert_not_called()
        assert result.email == "other@example.com"
        _delete_all_sessions_mock.assert_called_once_with(_U1, mock_db)

    def test_without_outgoing_mail_a_changed_email_is_applied_unverified(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com", email_verified=False)
        sign_up.request_email_change.return_value = False
        _identity()

        with patch(_SETTINGS) as mock_settings:
            mock_settings.is_mail_configured.return_value = False
            result = _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U9, mock_db)

        mock_crud.update_user.assert_called_once()
        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("other@example.com", False)
        sign_up.revoke_pending_tokens.assert_called_once_with(_U1, mock_db)
        sign_up.stage_email_changed_notice.assert_not_called()
        assert (result.email, result.email_verified) == ("other@example.com", False)
        mock_db.commit.assert_called_once()
        _delete_all_sessions_mock.assert_called_once_with(_U1, mock_db)

    def test_without_outgoing_mail_an_email_edit_that_omits_the_verified_flag_is_stored_unverified(
        self, mock_crud, mock_weight, mock_db, sign_up
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com", email_verified=False)
        sign_up.request_email_change.return_value = False
        _identity()

        with patch(_SETTINGS) as mock_settings:
            mock_settings.is_mail_configured.return_value = False
            _admin_edit(_U1, users_schema.UserEdit(email="other@example.com"), _U9, mock_db)

        changes = mock_crud.update_user.call_args.args[1]
        assert (changes["email"], changes["email_verified"]) == ("other@example.com", False)

    @pytest.mark.usefixtures("email_available")
    def test_an_email_applied_now_voids_the_reset_tokens(self, mock_crud, mock_weight, mock_db, password_reset):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com", email_verified=True)
        _identity()

        with patch(_SETTINGS) as mock_settings:
            mock_settings.is_mail_configured.return_value = True
            _admin_edit(_U1, _edit(_U1, email="other@example.com", email_verified=True), _U9, mock_db)

        password_reset.revoke_unused_tokens.assert_called_once_with(_U1, mock_db)

    @pytest.mark.usefixtures("email_available")
    def test_a_staged_edit_that_changes_the_email_voids_the_reset_tokens(
        self, mock_crud, mock_weight, mock_db, password_reset
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com")

        users_service.stage_user_edit(_U1, _edit(_U1, email="other@example.com"), mock_db, if_match="*")

        password_reset.revoke_unused_tokens.assert_called_once_with(_U1, mock_db)

    def test_a_staged_edit_that_keeps_the_email_keeps_the_reset_tokens(
        self, mock_crud, mock_weight, mock_db, password_reset
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")

        users_service.stage_user_edit(_U1, _edit(_U1, name="Renamed"), mock_db, if_match="*")

        password_reset.revoke_unused_tokens.assert_not_called()

    def test_an_email_only_requested_keeps_the_reset_tokens(self, mock_crud, mock_weight, mock_db, password_reset):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1)
        _identity()

        _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U9, mock_db)

        password_reset.revoke_unused_tokens.assert_not_called()

    def test_an_edit_that_keeps_the_email_never_touches_pending_changes(self, mock_crud, mock_weight, mock_db, sign_up):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")

        _admin_edit(_U1, _edit(_U1, name="Renamed"), _U9, mock_db)

        sign_up.request_email_change.assert_not_called()
        sign_up.revoke_pending_tokens.assert_not_called()

    def test_the_response_carries_the_pending_email_change(self, mock_crud, mock_weight, mock_db, sign_up):
        expires = datetime(2030, 1, 1, tzinfo=UTC)
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1)
        sign_up.get_pending_email_changes.return_value = {
            _U1: sign_up_contracts.PendingEmailChange(email="other@example.com", expires_at=expires)
        }
        _identity()

        result = _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U9, mock_db)

        assert (result.pending_email, result.pending_email_expires_at) == ("other@example.com", expires)

    def test_an_edit_of_other_fields_keeps_the_sessions(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")

        _admin_edit(_U1, _edit(_U1, name="Renamed"), _U9, mock_db)

        _delete_all_sessions_mock.assert_not_called()

    def test_an_administrator_editing_themselves_keeps_their_own_sessions(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.update_user.return_value = _user(_U1, access_type="regular")
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]

        _admin_edit(_U1, _edit(_U1, access_type="regular"), _U1, mock_db)

        _delete_all_sessions_mock.assert_not_called()

    @pytest.mark.parametrize(
        "after",
        [{"email": "other@example.com"}, {"access_type": "admin"}, {"active": False}],
        ids=["email", "access_type", "active"],
    )
    def test_a_security_relevant_edit_needs_the_step_up_of_the_administrator(
        self, mock_crud, mock_weight, mock_db, after
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1, **after)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        _identity()
        store = MagicMock()
        step_up = auth_schema.StepUpVerification(current_password="admin-password")
        order = MagicMock()
        order.attach_mock(_verify_step_up_mock, "step_up")
        order.attach_mock(mock_crud.update_user, "edit")

        _admin_edit(_U1, _edit(_U1, **after), _U9, mock_db, step_up=step_up, store=store)

        assert [call[0] for call in order.mock_calls] == ["step_up", "edit"]
        _verify_step_up_mock.assert_called_once_with(
            step_up, _U9, _SID_9, identity_providers_constants.StepUpAction.ADMIN_USER_EDIT, store, mock_db
        )

    def test_a_missing_step_up_is_verified_as_empty_credentials(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        _identity()
        _admin_edit(_U1, _edit(_U1, active=False), _U9, mock_db)

        assert _verify_step_up_mock.call_args.args[0] == auth_schema.StepUpVerification()

    @pytest.mark.parametrize("actor_id", [9, 1])
    def test_a_failed_step_up_changes_nothing(self, mock_crud, mock_weight, mock_db, actor_id):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        _verify_step_up_mock.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        with pytest.raises(core_exceptions.PermissionDeniedError):
            _admin_edit(_U1, _edit(_U1, access_type="regular"), actor_id, mock_db)

        mock_crud.update_user.assert_not_called()
        mock_db.commit.assert_not_called()
        _delete_all_sessions_mock.assert_not_called()

    def test_an_edit_that_changes_none_of_the_three_needs_no_step_up(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")

        _admin_edit(_U1, _edit(_U1, name="Renamed"), _U9, mock_db)

        _verify_step_up_mock.assert_not_called()

    def test_an_administrator_cannot_change_their_own_email_without_step_up(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)

        with pytest.raises(core_exceptions.PermissionDeniedError):
            _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U1, mock_db)

        _verify_step_up_mock.assert_not_called()
        mock_crud.update_user.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_edit_user_conflict_rolls_back(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.side_effect = core_exceptions.ConflictError("dup")

        with pytest.raises(core_exceptions.ConflictError):
            _admin_edit(_U1, _edit(_U1), _U9, mock_db)

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_an_admin_edit_of_one_field_writes_only_that_field(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")
        body = users_schema.UserAdminEdit(name="Renamed")

        _admin_edit(_U1, body.to_edit(), _U9, mock_db)

        assert mock_crud.update_user.call_args.args[1] == {"name": "Renamed"}
        _verify_step_up_mock.assert_not_called()
        _delete_all_sessions_mock.assert_not_called()

    def test_an_admin_edit_of_the_active_flag_alone_needs_the_step_up_and_ends_sessions(
        self, mock_crud, mock_weight, mock_db
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        _identity()

        _admin_edit(_U1, users_schema.UserAdminEdit(active=False).to_edit(), _U9, mock_db)

        assert mock_crud.update_user.call_args.args[1] == {"active": False}
        _verify_step_up_mock.assert_called_once()
        _delete_all_sessions_mock.assert_called_once_with(_U1, mock_db)

    def test_an_admin_edit_that_resubmits_the_stored_role_and_email_changes_no_session(
        self, mock_crud, mock_weight, mock_db
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")
        body = users_schema.UserAdminEdit(name="Renamed", email="USER1@example.com", access_type="regular")

        _admin_edit(_U1, body.to_edit(), _U9, mock_db)

        _verify_step_up_mock.assert_not_called()
        _delete_all_sessions_mock.assert_not_called()

    def test_an_edit_cannot_activate_a_user_awaiting_approval(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, active=False, pending_admin_approval=True)

        with (
            patch("modules.users.users.service.jasil_audit.record_detached") as record,
            pytest.raises(core_exceptions.ApprovalPendingError, match=f"/users/{_U1}/approve") as refused,
        ):
            users_service.stage_user_edit(_U1, users_schema.UserEdit(active=True), mock_db, if_match="*")

        assert refused.value.code == "approval-pending"
        assert isinstance(refused.value, core_exceptions.ConflictError)
        record.assert_called_once_with(
            users_audit_actions.USER_UPDATE,
            outcome=jasil_audit.Outcome.DENIED,
            target_type="user",
            target_id=str(_U1),
            target_owner_id=str(_U1),
        )
        mock_crud.update_user.assert_not_called()

    def test_an_edit_of_other_fields_of_a_user_awaiting_approval_is_applied(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, active=False, pending_admin_approval=True)
        mock_crud.update_user.return_value = _user(_U1, active=False, pending_admin_approval=True, name="Renamed")

        users_service.stage_user_edit(_U1, users_schema.UserEdit(name="Renamed", active=False), mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"name": "Renamed", "active": False}

    def test_an_edit_activates_a_deactivated_user_who_is_not_awaiting_approval(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, active=False)
        mock_crud.update_user.return_value = _user(_U1)

        users_service.stage_user_edit(_U1, users_schema.UserEdit(active=True), mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"active": True}

    def test_profile_edit_keeps_only_allow_listed_fields(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1)
        profile = users_schema.ProfileUpdate.model_construct(
            name="New", username="MIXED", access_type="admin", active=False, email_verified=True
        )
        profile.__pydantic_fields_set__.update({"name", "username", "access_type", "active", "email_verified"})

        users_service.stage_profile_edit(_U1, profile, mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"name": "New"}

    def test_profile_edit_can_set_the_timezone(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1)

        users_service.stage_profile_edit(
            _U1, users_schema.ProfileUpdate(timezone="Europe/Lisbon"), mock_db, if_match="*"
        )

        assert mock_crud.update_user.call_args.args[1] == {"timezone": "Europe/Lisbon"}

    def test_profile_edit_can_set_the_weight_units_override(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, weight_units="imperial")

        users_service.stage_profile_edit(
            _U1, users_schema.ProfileUpdate(weight_units="imperial"), mock_db, if_match="*"
        )

        assert mock_crud.update_user.call_args.args[1] == {"weight_units": "imperial"}

    def test_profile_edit_can_clear_the_weight_units_override(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, weight_units="imperial")
        mock_crud.update_user.return_value = _user(_U1, weight_units=None)

        users_service.stage_profile_edit(_U1, users_schema.ProfileUpdate(weight_units=None), mock_db, if_match="*")

        assert mock_crud.update_user.call_args.args[1] == {"weight_units": None}

    def test_admin_edit_without_weight_units_keeps_the_override(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, weight_units="imperial")
        mock_crud.update_user.return_value = _user(_U1, units="imperial", weight_units="imperial")
        edit = users_schema.UserEdit(**_edit(_U1, units="imperial").model_dump(exclude={"weight_units"}))

        users_service.stage_user_edit(_U1, edit, mock_db, if_match="*")

        changes = mock_crud.update_user.call_args.args[1]
        assert changes["units"] == "imperial"
        assert "weight_units" not in changes

    def test_profile_height_change_recalculates_bmi(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, height=170)
        mock_crud.update_user.return_value = _user(_U1, height=175)

        users_service.stage_profile_edit(_U1, users_schema.ProfileUpdate(height=175), mock_db, if_match="*")

        mock_weight.lifecycle_hooks.return_value.stage_height_change.assert_called_once_with(_U1, 175.0, mock_db)

    def test_profile_without_height_never_recalculates(self, mock_crud, mock_weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, height=170)
        mock_crud.update_user.return_value = _user(_U1, height=175)

        users_service.stage_profile_edit(_U1, users_schema.ProfileUpdate(name="Only"), mock_db, if_match="*")

        mock_weight.lifecycle_hooks.return_value.stage_height_change.assert_not_called()


@patch(_CRUD)
class TestApproveAndVerify:
    @pytest.fixture(autouse=True)
    def settings(self):
        with patch(_SETTINGS) as mock_settings:
            mock_settings.get_server_settings.return_value = MagicMock(signup_require_email_verification=True)
            yield mock_settings.get_server_settings.return_value

    def test_approve_activates_and_commits(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        with patch(
            "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email", return_value=True
        ) as mock_request:
            users_service.approve_user(_U1, mock_db)

        mock_crud.approve_pending_user.assert_called_once_with(_U1, mock_db)
        mock_request.assert_called_once_with(_U1, mock_db)
        mock_db.commit.assert_called_once()

    def test_approve_without_mail_is_still_approved(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)

        with patch(
            "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email", return_value=False
        ):
            users_service.approve_user(_U1, mock_db)

        mock_crud.approve_pending_user.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_approval_event_does_not_escape_a_failed_commit(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_db.commit.side_effect = RuntimeError("commit failed")

        with (
            patch(
                "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email",
                return_value=True,
            ) as mock_request,
            pytest.raises(RuntimeError, match="commit failed"),
        ):
            users_service.approve_user(_U1, mock_db)

        mock_crud.approve_pending_user.assert_called_once()
        mock_request.assert_called_once_with(_U1, mock_db)
        mock_db.commit.assert_called_once()

    def test_approve_refuses_a_user_who_is_not_awaiting_approval(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=True)
        mock_crud.approve_pending_user.return_value = False

        with (
            patch(
                "modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email"
            ) as mock_request,
            pytest.raises(core_exceptions.ConflictError, match="not awaiting approval"),
        ):
            users_service.approve_user(_U1, mock_db)

        mock_request.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_approve_refuses_an_unverified_email_while_verification_is_required(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=False)

        with pytest.raises(core_exceptions.ConflictError, match="User email is not verified") as refused:
            users_service.approve_user(_U1, mock_db)

        assert refused.value.status_code == 409
        mock_crud.approve_pending_user.assert_not_called()

    def test_approve_needs_no_verified_email_when_verification_is_off(self, mock_crud, mock_db, settings):
        """With approval alone no verification email is ever sent, so requiring one made approval impossible."""
        settings.signup_require_email_verification = False
        mock_crud.get_user_by_id.return_value = _user(_U1, email_verified=False)

        with patch("modules.users.users.service.sign_up_tokens_integration.request_sign_up_approved_email"):
            users_service.approve_user(_U1, mock_db)

        mock_crud.approve_pending_user.assert_called_once_with(_U1, mock_db)
        mock_db.commit.assert_called_once()

    def test_verification_activates_without_approval_policy(self, mock_crud, mock_db):
        mock_crud.is_deactivated.return_value = False
        users_service.stage_email_verification(_U1, MagicMock(signup_require_admin_approval=False), mock_db)

        assert mock_crud.update_user.call_args.args[1] == {
            "email_verified": True,
            "pending_admin_approval": False,
            "active": True,
        }
        mock_db.commit.assert_not_called()

    def test_verification_leaves_the_account_pending_under_approval_policy(self, mock_crud, mock_db):
        users_service.stage_email_verification(_U1, MagicMock(signup_require_admin_approval=True), mock_db)

        assert mock_crud.update_user.call_args.args[1] == {"email_verified": True}


class TestRequireDeletableUser:
    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_deletable_user(_U1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_the_only_administrator_cannot_be_deleted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [_U1]

        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_deletable_user(_U1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_an_administrator_can_be_deleted_while_another_remains(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]

        users_service.require_deletable_user(_U1, mock_db, if_match="*")

    @patch(_CRUD)
    def test_a_regular_user_can_be_deleted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)

        users_service.require_deletable_user(_U1, mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_a_stale_version_is_refused_before_the_administrator_check(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin", version=3)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_service.require_deletable_user(_U1, mock_db, if_match='"2"')

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_the_current_version_is_accepted(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, version=3)

        users_service.require_deletable_user(_U1, mock_db, if_match='"3"')


class TestLastAdminIsProtected:
    @pytest.mark.parametrize(
        ("edit", "action"),
        [({"access_type": "regular"}, "demoted"), ({"active": False}, "deactivated")],
    )
    @patch(_CRUD)
    def test_the_only_administrator_cannot_be_demoted_or_deactivated(self, mock_crud, edit, action, mock_db):
        admin = _user(_U1, access_type="admin")
        mock_crud.get_user_by_id.return_value = admin
        mock_crud.lock_active_admin_ids.return_value = [_U1]

        with pytest.raises(core_exceptions.LastAdministratorError, match=action):
            users_service.stage_user_edit(_U1, _edit(_U1, **{"access_type": "admin", **edit}), mock_db, if_match="*")

        mock_crud.update_user.assert_not_called()

    @patch("modules.users.users.service.users_contributor_registry")
    @patch(_CRUD)
    def test_one_of_several_administrators_can_be_demoted(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        mock_crud.update_user.return_value = _user(_U1)

        users_service.stage_user_edit(_U1, _edit(_U1, access_type="regular"), mock_db, if_match="*")

        mock_crud.update_user.assert_called_once()

    @patch("modules.users.users.service.users_contributor_registry")
    @patch(_CRUD)
    def test_an_edit_that_keeps_the_admin_takes_no_lock(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.update_user.return_value = _user(_U1)

        users_service.stage_user_edit(_U1, _edit(_U1, access_type="admin", name="Renamed"), mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()

    @patch(_CRUD)
    def test_a_regular_user_is_never_locked_against(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="regular")
        mock_crud.update_user.return_value = _user(_U1)

        with patch("modules.users.users.service.users_contributor_registry"):
            users_service.stage_user_edit(_U1, _edit(_U1, access_type="regular", active=False), mock_db, if_match="*")

        mock_crud.lock_active_admin_ids.assert_not_called()


class TestTimezone:
    @patch(_CRUD)
    def test_prefers_the_users_own_zone(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, timezone="Europe/Lisbon")

        assert users_service.resolve_user_timezone(_U1, mock_db) == "Europe/Lisbon"

    @patch("modules.users.users.service.core_timezone")
    @patch(_CRUD)
    def test_falls_back_to_the_server_zone(self, mock_crud, mock_tz, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_tz.or_default.side_effect = lambda tz: tz or "UTC"

        assert users_service.resolve_user_timezone(_U1, mock_db) == "UTC"

    @patch("modules.users.users.service.core_timezone")
    @patch(_CRUD)
    def test_falls_back_when_the_user_is_missing(self, mock_crud, mock_tz, mock_db):
        mock_crud.get_user_by_id.return_value = None
        mock_tz.or_default.side_effect = lambda tz: tz or "UTC"

        assert users_service.resolve_user_timezone(_U1, mock_db) == "UTC"

    @patch("modules.users.users.service.core_timezone")
    def test_today_is_resolved_in_the_resolved_zone(self, mock_tz, mock_db):
        with patch("modules.users.users.service.resolve_user_timezone", return_value="Pacific/Auckland"):
            result = users_service.user_local_today(_U1, mock_db)

        mock_tz.today_in.assert_called_once_with("Pacific/Auckland")
        assert result == mock_tz.today_in.return_value


@patch("modules.users.users.service.users_contributor_registry")
@patch(_CRUD)
class TestSecurityGenerationBump:
    """A change that takes effect on the account's email or active flag advances its security generation."""

    @pytest.mark.usefixtures("email_available")
    def test_an_admin_edit_that_changes_the_email_bumps(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com")

        users_service.stage_user_edit(_U1, _edit(_U1, email="other@example.com"), mock_db, if_match="*")

        generation.stage_bump.assert_called_once_with(_U1, mock_db)

    def test_an_admin_edit_that_deactivates_bumps(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]

        users_service.stage_user_edit(_U1, _edit(_U1, active=False), mock_db, if_match="*")

        generation.stage_bump.assert_called_once_with(_U1, mock_db)

    @pytest.mark.usefixtures("email_available")
    def test_an_edit_changing_both_bumps_once(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, email="other@example.com", active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]

        users_service.stage_user_edit(_U1, _edit(_U1, email="other@example.com", active=False), mock_db, if_match="*")

        generation.stage_bump.assert_called_once_with(_U1, mock_db)

    def test_an_edit_that_changes_neither_does_not_bump(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1, name="Renamed")

        users_service.stage_user_edit(_U1, _edit(_U1, name="Renamed"), mock_db, if_match="*")

        generation.stage_bump.assert_not_called()

    def test_an_edit_that_reactivates_does_not_bump(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, active=False)
        mock_crud.update_user.return_value = _user(_U1, active=True)

        users_service.stage_user_edit(_U1, _edit(_U1, active=True), mock_db, if_match="*")

        generation.stage_bump.assert_not_called()

    def test_an_email_only_requested_does_not_bump(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.get_user_by_email.return_value = None
        mock_crud.update_user.return_value = _user(_U1)

        _admin_edit(_U1, _edit(_U1, email="other@example.com"), _U9, mock_db)

        generation.stage_bump.assert_not_called()

    @pytest.mark.usefixtures("email_available")
    def test_an_email_applied_without_mail_bumps(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")

        users_service.stage_email_change(_U1, "new@example.com", mock_db)

        generation.stage_bump.assert_called_once_with(_U1, mock_db)

    def test_resubmitting_the_current_address_does_not_bump(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="same@example.com")

        users_service.stage_email_change(_U1, "same@example.com", mock_db)

        generation.stage_bump.assert_not_called()

    def test_a_confirmed_new_address_bumps(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")
        mock_crud.get_user_by_email.return_value = None

        users_service.stage_confirmed_email_change(_U1, "New@Example.com", mock_db)

        generation.stage_bump.assert_called_once_with(_U1, mock_db)

    def test_confirming_the_current_address_does_not_bump(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="same@example.com")
        mock_crud.get_user_by_email.return_value = _user(_U1, email="same@example.com")

        users_service.stage_confirmed_email_change(_U1, "Same@Example.com", mock_db)

        generation.stage_bump.assert_not_called()

    @pytest.mark.usefixtures("email_available")
    def test_an_edit_bumps_before_the_administrator_lock_and_the_user_write(
        self, mock_crud, mock_weight, mock_db, generation
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, access_type="admin")
        mock_crud.update_user.return_value = _user(_U1, access_type="admin", email="other@example.com", active=False)
        mock_crud.lock_active_admin_ids.return_value = [_U1, _U2]
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        order.attach_mock(mock_crud.lock_active_admin_ids, "lock_admins")
        order.attach_mock(mock_crud.update_user, "update_user")

        users_service.stage_user_edit(
            1, _edit(_U1, access_type="admin", email="other@example.com", active=False), mock_db, if_match="*"
        )

        assert [call[0] for call in order.mock_calls][:3] == ["bump", "lock_admins", "update_user"]

    def test_an_edit_that_changes_the_email_with_different_case_bumps_only_for_a_new_address(
        self, mock_crud, mock_weight, mock_db, generation
    ):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="same@example.com")
        mock_crud.update_user.return_value = _user(_U1, email="same@example.com")

        users_service.stage_user_edit(_U1, _edit(_U1, email="Same@Example.com"), mock_db, if_match="*")

        generation.stage_bump.assert_not_called()

    @pytest.mark.usefixtures("email_available")
    def test_a_new_address_bumps_before_the_user_write(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        order.attach_mock(mock_crud.update_user, "update_user")

        users_service.stage_email_change(_U1, "new@example.com", mock_db)

        assert [call[0] for call in order.mock_calls][:2] == ["bump", "update_user"]

    def test_a_confirmed_new_address_bumps_before_the_user_write(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")
        mock_crud.get_user_by_email.return_value = None
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        order.attach_mock(mock_crud.update_user, "update_user")

        users_service.stage_confirmed_email_change(_U1, "new@example.com", mock_db)

        assert [call[0] for call in order.mock_calls][:2] == ["bump", "update_user"]

    def test_a_synced_address_bumps_through_the_confirmed_change(self, mock_crud, mock_weight, mock_db, generation):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")
        mock_crud.get_user_by_email.return_value = None

        users_service.stage_synced_email_change(_U1, "new@example.com", mock_db)

        generation.stage_bump.assert_called_once_with(_U1, mock_db)


class TestStageEmailChange:
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_stores_the_lower_cased_address_as_unverified(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")

        changed = users_service.stage_email_change(_U1, "New@Example.COM", mock_db)

        assert changed is True
        mock_crud.update_user.assert_called_once_with(
            _U1, {"email": "new@example.com", "email_verified": False}, mock_db
        )

    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_changed_address_revokes_the_users_unused_tokens(self, mock_crud, mock_db, sign_up):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")

        users_service.stage_email_change(_U1, "new@example.com", mock_db)

        sign_up.revoke_pending_tokens.assert_called_once_with(_U1, mock_db)

    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_a_changed_address_voids_the_reset_tokens(self, mock_crud, mock_db, password_reset):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="old@example.com")

        users_service.stage_email_change(_U1, "new@example.com", mock_db)

        password_reset.revoke_unused_tokens.assert_called_once_with(_U1, mock_db)

    @patch(_CRUD)
    def test_resubmitting_the_current_address_keeps_the_reset_tokens(self, mock_crud, mock_db, password_reset):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="same@example.com")

        users_service.stage_email_change(_U1, "same@example.com", mock_db)

        password_reset.revoke_unused_tokens.assert_not_called()

    @patch(_CRUD)
    def test_resubmitting_the_current_address_keeps_it_verified(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1, email="same@example.com")

        changed = users_service.stage_email_change(_U1, "SAME@example.com", mock_db)

        assert changed is False
        mock_crud.update_user.assert_not_called()

    @patch(_CRUD)
    def test_unknown_user_is_not_found(self, mock_crud, mock_db):
        mock_crud.get_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_email_change(_U1, "a@example.com", mock_db)


@pytest.mark.usefixtures("real_email_availability")
class TestStageConfirmedEmailChange:
    @patch(_CRUD)
    def test_a_confirmed_address_voids_the_reset_tokens(self, mock_crud, mock_db, password_reset):
        mock_crud.get_user_by_email.return_value = None

        users_service.stage_confirmed_email_change(_U1, "New@Example.com", mock_db)

        password_reset.revoke_unused_tokens.assert_called_once_with(_U1, mock_db)

    @patch(_CRUD)
    def test_stores_the_lower_cased_address_as_verified(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = None

        users_service.stage_confirmed_email_change(_U1, "New@Example.COM", mock_db)

        mock_crud.get_user_by_email.assert_called_once_with("new@example.com", mock_db)
        mock_crud.update_user.assert_called_once_with(
            _U1, {"email": "new@example.com", "email_verified": True}, mock_db
        )

    @patch(_CRUD)
    def test_the_users_own_address_is_not_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(_U1, email="same@example.com")

        users_service.stage_confirmed_email_change(_U1, "same@example.com", mock_db)

        mock_crud.update_user.assert_called_once()

    @patch(_CRUD)
    def test_an_address_of_another_account_is_a_conflict(self, mock_crud, mock_db):
        mock_crud.get_user_by_email.return_value = _user(_U2, email="taken@example.com")

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_confirmed_email_change(_U1, "taken@example.com", mock_db)

        mock_crud.update_user.assert_not_called()


class TestAdminEditNormalizesIdentity:
    @patch("modules.users.users.service.users_contributor_registry")
    @patch(_CRUD)
    @pytest.mark.usefixtures("email_available")
    def test_email_is_lower_cased_like_the_username(self, mock_crud, _weight, mock_db):
        mock_crud.get_user_by_id.return_value = _user(_U1)
        mock_crud.update_user.return_value = _user(_U1)

        users_service.stage_user_edit(_U1, _edit(_U1, username="Bob", email="Bob@Example.COM"), mock_db, if_match="*")

        changes = mock_crud.update_user.call_args.args[1]
        assert changes["username"] == "bob"
        assert changes["email"] == "bob@example.com"
