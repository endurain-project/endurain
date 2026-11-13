"""Tests for the marker that tells an administrator-deactivated account from a sign-up awaiting verification."""

import uuid
from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import jasil.testing as jasil_testing
import pytest
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import core.exceptions as core_exceptions
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_U1, _U7, _U9 = (uuid.UUID(int=n) for n in (1, 7, 9))

_SERVICE = "modules.users.users.service"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, _U7)
    session.query(users_models.Users).update({"preferred_language": "en"})
    session.commit()
    yield session
    session.close()


def _user(db, user_id=_U7):
    db.expire_all()
    return db.get(users_models.Users, user_id)


def _edit(db, **changes):
    edit = users_schema.UserEdit.from_read(users_service.require_user(_U7, db)).model_copy(update=changes)
    with patch(f"{_SERVICE}.sign_up_tokens_integration"):
        users_service.stage_user_edit(_U7, edit, db, if_match="*")
    db.commit()


class TestAdministrativeEdit:
    def test_deactivating_records_when_and_reactivating_clears_it(self, db):
        _edit(db, active=False)
        assert _user(db).active is False
        assert _user(db).deactivated_at is not None

        _edit(db, active=True)
        assert _user(db).active is True
        assert _user(db).deactivated_at is None

    def test_an_edit_that_leaves_an_inactive_account_inactive_keeps_the_original_time(self, db):
        _edit(db, active=False)
        first = _user(db).deactivated_at

        _edit(db, active=False, name="Renamed")

        assert _user(db).deactivated_at == first

    def test_an_edit_that_leaves_an_active_account_active_records_nothing(self, db):
        _edit(db, name="Renamed")

        assert _user(db).deactivated_at is None


class TestApprovalAndVerification:
    def test_approving_a_sign_up_leaves_no_marker(self, db):
        user = _user(db)
        user.active, user.pending_admin_approval, user.email_verified = False, True, True
        db.commit()
        with (
            patch(f"{_SERVICE}.sign_up_tokens_integration"),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=MagicMock()) as settings,
        ):
            settings.return_value.signup_require_email_verification = False
            users_service.approve_user(_U7, db)

        assert _user(db).active is True
        assert _user(db).deactivated_at is None

    @pytest.mark.parametrize("state", ["active", "deactivated", "deletion_queued"])
    def test_approving_a_user_who_is_not_awaiting_approval_changes_nothing(self, db, state):
        if state == "deactivated":
            _edit(db, active=False)
        elif state == "deletion_queued":
            users_crud.stage_deletion_request(_U7, db)
            db.commit()
        before = (_user(db).active, _user(db).deactivated_at, _user(db).deletion_requested_at, _user(db).version)
        with (
            patch(f"{_SERVICE}.sign_up_tokens_integration") as sign_up,
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=MagicMock()) as settings,
            jasil_testing.capture_audit() as audit,
        ):
            settings.return_value.signup_require_email_verification = False
            with pytest.raises(core_exceptions.ConflictError, match="not awaiting approval"):
                users_service.approve_user(_U7, db)

        sign_up.request_sign_up_approved_email.assert_not_called()
        assert len(audit.matching(users_audit_actions.USER_APPROVE.id)) == 1
        audit.assert_audited(
            users_audit_actions.USER_APPROVE.id, outcome=jasil_audit.Outcome.DENIED, target_id=str(_U7)
        )
        db.rollback()
        assert (
            _user(db).active,
            _user(db).deactivated_at,
            _user(db).deletion_requested_at,
            _user(db).version,
        ) == before


class TestStageEmailVerification:
    @staticmethod
    def _settings(*, approval):
        return MagicMock(signup_require_admin_approval=approval)

    @pytest.mark.parametrize("approval", [False, True])
    def test_a_deactivated_account_is_verified_but_never_activated(self, db, approval):
        _edit(db, active=False)

        users_service.stage_email_verification(_U7, self._settings(approval=approval), db)

        user = _user(db)
        assert user.email_verified is True
        assert user.active is False
        assert user.deactivated_at is not None

    def test_a_sign_up_awaiting_verification_is_activated(self, db):
        user = _user(db)
        user.active, user.email_verified = False, False
        db.commit()

        users_service.stage_email_verification(_U7, self._settings(approval=False), db)

        assert (_user(db).active, _user(db).email_verified) == (True, True)

    def test_is_deactivated_reports_the_marker(self, db):
        assert users_service.is_deactivated(_U7, db) is False
        _edit(db, active=False)
        assert users_service.is_deactivated(_U7, db) is True


class TestDeletionRequest:
    def test_a_deletion_request_deactivates_and_records_it(self, db):
        users_crud.stage_deletion_request(_U7, db)
        db.commit()

        assert _user(db).active is False
        assert _user(db).deactivated_at is not None


class TestCreation:
    """The row is staged through a mocked crud: the sign-up enums are not bindable by the SQLite test engine."""

    @staticmethod
    def _create(*, active):
        user = users_schema.UserCreate(
            name="New",
            username="newuser",
            email="new@example.com",
            preferred_language="en",
            password="password123",
            access_type="regular",
            active=active,
        )
        with (
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration") as credentials,
            patch(f"{_SERVICE}.users_crud") as crud,
            patch(f"{_SERVICE}._stage_default_data"),
        ):
            credentials.validate_and_hash_password_for_user.return_value = "hash"
            crud.create_user.return_value = MagicMock(id=_U1)
            users_service.create_user(user, None, _U9, "sid-9", MagicMock(), MagicMock())
        return crud.create_user.call_args.args[0]

    @pytest.mark.usefixtures("email_available")
    def test_an_administrator_created_inactive_account_is_marked(self):
        assert self._create(active=False)["deactivated_at"] is not None

    @pytest.mark.usefixtures("email_available")
    def test_an_administrator_created_active_account_is_not(self):
        assert self._create(active=True).get("deactivated_at") is None

    @pytest.mark.parametrize(("verification", "approval"), [(True, False), (False, True), (True, True)])
    @pytest.mark.usefixtures("email_available")
    def test_a_sign_up_awaiting_verification_or_approval_is_not_marked(self, verification, approval):
        settings = MagicMock(signup_require_email_verification=verification, signup_require_admin_approval=approval)
        signup = users_schema.UserSignup(
            name="New", username="newuser", email="new@example.com", preferred_language="en", password="password123"
        )
        with (
            patch(f"{_SERVICE}.credentials_integration") as credentials,
            patch(f"{_SERVICE}.users_crud") as crud,
            patch(f"{_SERVICE}._stage_default_data"),
        ):
            credentials.validate_and_hash_password_for_user.return_value = "hash"
            crud.create_user.return_value = MagicMock(id=_U1)
            users_service.stage_signup_user(signup, settings, MagicMock())

        fields = crud.create_user.call_args.args[0]
        assert fields["active"] is False
        assert fields.get("deactivated_at") is None
