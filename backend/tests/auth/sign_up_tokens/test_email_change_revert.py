"""The "this wasn't me" link of an email change: valid for 7 days, before and after the change is confirmed."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.integration_service as users_integration
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session, ensure_user

_OWNER_EMAIL = f"user{MOCK_USER_ID.hex}@example.com"
_OTHER_EMAIL = f"user{OTHER_USER_ID.hex}@example.com"

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"
_ACTION = "auth.email_change.cancel"
_OLD = _OWNER_EMAIL
_NEW = "new@example.com"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, MOCK_USER_ID)
    ensure_user(factory, OTHER_USER_ID)
    session.query(users_models.Users).update({"preferred_language": "en", "active": True, "email_verified": False})
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def platform():
    """Mail is configured, the sign-up policy needs no verification and sessions and keys are counted."""
    settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
    with (
        patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True),
        patch(f"{_SERVICE}.server_settings_integration.get_server_settings", return_value=settings),
        patch(f"{_SERVICE}.sessions_integration.delete_sessions_by_user", return_value=2) as sessions,
        patch(f"{_SERVICE}.api_keys_integration.revoke_user_api_keys", return_value=1) as keys,
    ):
        yield MagicMock(sessions=sessions, keys=keys)


def _user(db, user_id=MOCK_USER_ID):
    db.expire_all()
    return db.get(users_models.Users, user_id)


def _extract(html_body: str) -> str:
    return html_body.split("cancel-email-change?token=")[1].split('"')[0].split("<")[0].split("&")[0]


def _request(db, new=_NEW, previous=_OLD) -> str:
    """Request a change as the owner and return the link mailed to the current address."""
    with patch(_PUBLISH):
        sign_up_service.request_self_service_email_change(MOCK_USER_ID, new, previous, MemoryState(), db)
    db.commit()
    message = sign_up_service.prepare_email_change_requested_email(MOCK_USER_ID, _HOST, db)
    assert message is not None
    return _extract(message[2])


def _confirm(db, event="event-1") -> uuid.UUID:
    """Deliver the confirmation mail and open its link; return the id of the notice's token."""
    message = sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, event, _HOST, db)
    assert message is not None
    raw = message[2].split("?token=")[1].split('"')[0].split("<")[0].split("&")[0]
    with patch(_PUBLISH) as publish:
        sign_up_service.confirm_email_change(raw, db)
    return uuid.UUID(publish.call_args.args[1]["token_id"])


def _revert(db, token):
    return sign_up_service.cancel_email_change(token, db)


def _seed_reset_token(db) -> uuid.UUID:
    """Store an unused password-reset token of the owner and return its id."""
    now = datetime.now(UTC)
    row = password_reset_models.PasswordResetToken(
        user_id=MOCK_USER_ID, token_hash=uuid.uuid4().hex, created_at=now, expires_at=now + timedelta(hours=1)
    )
    db.add(row)
    db.commit()
    return row.id


def _reset_token_used(db, token_id: uuid.UUID) -> bool:
    db.expire_all()
    return db.get(password_reset_models.PasswordResetToken, token_id).used


class TestTheLinkSurvivesConfirmation:
    def test_confirming_then_using_the_link_reverts_the_change(self, db, platform, security_generations):
        link = _request(db)
        _confirm(db)
        assert _user(db).email == _NEW

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert result.email_restored is True
        user = _user(db)
        assert (user.email, user.email_verified) == (_OLD, True)
        assert set(security_generations.bumps) == {MOCK_USER_ID}
        platform.sessions.assert_called_once_with(MOCK_USER_ID, db)
        platform.keys.assert_called_once_with(MOCK_USER_ID, db)
        entry = audit.assert_audited(
            _ACTION, target_type="user", target_id=str(MOCK_USER_ID), target_owner_id=str(MOCK_USER_ID)
        )
        assert entry.details["email_restored"] is True
        assert entry.details["change_applied"] is True

    def test_the_link_mailed_before_a_resend_still_works(self, db):
        link = _request(db)
        sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "first-delivery", _HOST, db)

        result = _revert(db, link)

        assert result.email_restored is False
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0

    def test_the_confirmation_notice_carries_the_same_link(self, db):
        link = _request(db)
        token_id = _confirm(db)

        message = sign_up_service.prepare_email_changed_email(MOCK_USER_ID, token_id, _HOST, db)

        assert message is not None
        recipient, _subject, html_body, text_body = message
        assert recipient == _OLD
        assert _extract(html_body) == link
        assert f"{_HOST}/cancel-email-change?token={link}" in text_body

    def test_works_six_days_after_the_request_and_not_after_seven(self, db):
        link = _request(db)
        _confirm(db)

        with patch(f"{_SERVICE}.datetime") as clock, pytest.raises(core_exceptions.InvalidInputError):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=7, minutes=1)
            _revert(db, link)
        db.rollback()
        assert _user(db).email == _NEW

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=6)
            assert _revert(db, link).email_restored is True

    def test_works_once(self, db):
        link = _request(db)
        _confirm(db)
        _revert(db, link)

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, link)

    def test_a_change_purged_before_the_locked_read_is_refused(self, db, platform):
        # The purge job can delete the change's rows between the link check and the read under the generation lock.
        link = _request(db)
        _confirm(db)

        real = sign_up_service.sign_up_crud.get_email_change_tokens
        reads = iter([real, lambda *_: []])
        with (
            patch(f"{_SERVICE}.sign_up_crud.get_email_change_tokens", side_effect=lambda *a: next(reads)(*a)),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            _revert(db, link)

        platform.sessions.assert_not_called()

    def test_a_revert_after_a_later_confirmed_change_restores_the_mailed_address_and_voids_the_later_link(
        self, db, platform
    ):
        first = _request(db)
        _confirm(db)
        second = _request(db, new="third@example.com", previous=_NEW)
        _confirm(db, event="event-2")

        result = _revert(db, first)

        assert (result.change_applied, result.email_restored) == (True, True)
        assert _user(db).email == _OLD
        platform.sessions.assert_called_once_with(MOCK_USER_ID, db)
        platform.keys.assert_called_once_with(MOCK_USER_ID, db)
        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, second)

    def test_a_revert_while_a_later_change_is_pending_voids_it(self, db, platform):
        first = _request(db)
        _confirm(db)
        _request(db, new="third@example.com", previous=_NEW)

        result = _revert(db, first)

        assert (result.change_applied, result.email_restored) == (True, True)
        assert _user(db).email == _OLD
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        platform.sessions.assert_called_once_with(MOCK_USER_ID, db)

    def test_a_later_changes_own_link_after_the_first_revert_is_refused(self, db, platform):
        first = _request(db)
        _confirm(db)
        second = _request(db, new="third@example.com", previous=_NEW)
        _revert(db, first)
        platform.sessions.reset_mock()

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, second)
        db.rollback()

        assert _user(db).email == _OLD
        platform.sessions.assert_not_called()

    def test_the_later_changes_link_reverts_only_its_own_change(self, db):
        first = _request(db)
        _confirm(db)
        second = _request(db, new="third@example.com", previous=_NEW)
        _confirm(db, event="event-2")

        assert _revert(db, second).email_restored is True
        assert _user(db).email == _NEW
        assert _revert(db, first).email_restored is True
        assert _user(db).email == _OLD

    def test_a_revert_after_a_round_trip_back_to_the_same_address_restores_the_mailed_address(self, db):
        first = _request(db)
        _confirm(db)
        _request(db, new="third@example.com", previous=_NEW)
        _confirm(db, event="event-2")
        _request(db, new=_NEW, previous="third@example.com")
        _confirm(db, event="event-3")

        assert _revert(db, first).email_restored is True
        assert _user(db).email == _OLD

    def test_an_address_the_account_has_since_been_given_by_an_administrator_is_replaced(self, db):
        link = _request(db)
        _confirm(db)
        db.query(users_models.Users).filter_by(id=MOCK_USER_ID).update({"email": "admin-set@example.com"})
        db.commit()

        assert _revert(db, link).email_restored is True
        assert _user(db).email == _OLD

    def test_an_address_taken_despite_the_reservation_is_not_restored_but_the_account_is_secured(
        self, db, platform, security_generations
    ):
        link = _request(db)
        _confirm(db)
        db.query(users_models.Users).filter_by(id=OTHER_USER_ID).update({"email": _OLD})
        db.commit()

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert result.email_restored is False
        assert _user(db).email == _NEW
        assert MOCK_USER_ID in security_generations.bumps
        platform.sessions.assert_called_once_with(MOCK_USER_ID, db)
        platform.keys.assert_called_once_with(MOCK_USER_ID, db)
        assert audit.assert_audited(_ACTION, target_id=str(MOCK_USER_ID)).details["email_restored"] is False

    def test_an_address_not_restored_revokes_the_reset_tokens_and_audits_it(self, db, platform, security_generations):
        link = _request(db)
        _confirm(db)
        db.query(users_models.Users).filter_by(id=OTHER_USER_ID).update({"email": _OLD})
        db.commit()
        reset_token = _seed_reset_token(db)

        with jasil_testing.capture_audit() as audit:
            _revert(db, link)

        assert _reset_token_used(db, reset_token) is True
        assert audit.assert_audited(_ACTION, target_id=str(MOCK_USER_ID)).details["reset_tokens_revoked"] is True

    def test_a_restored_address_revokes_the_reset_tokens_and_audits_it(self, db, platform, security_generations):
        link = _request(db)
        _confirm(db)
        reset_token = _seed_reset_token(db)

        with jasil_testing.capture_audit() as audit:
            _revert(db, link)

        assert _reset_token_used(db, reset_token) is True
        assert audit.assert_audited(_ACTION, target_id=str(MOCK_USER_ID)).details["reset_tokens_revoked"] is True


def _reserve_for_owner(db):
    """Request and confirm a change of the owner, so that the old address is reserved for it."""
    link = _request(db)
    _confirm(db)
    return link


class TestThePreviousAddressIsReserved:
    def test_it_is_reserved_for_the_account_it_came_from_and_only_during_the_window(self, db):
        _reserve_for_owner(db)

        assert sign_up_service.get_email_reserver_id(_OLD, OTHER_USER_ID, db) == MOCK_USER_ID
        assert sign_up_service.get_email_reserver_id(_OLD.upper(), OTHER_USER_ID, db) == MOCK_USER_ID
        assert sign_up_service.get_email_reserver_id(_OLD, None, db) == MOCK_USER_ID
        assert sign_up_service.get_email_reserver_id(_OLD, MOCK_USER_ID, db) is None
        assert sign_up_service.get_email_reserver_id("free@example.com", OTHER_USER_ID, db) is None
        db.query(sign_up_models.SignUpToken).update({"revert_until": datetime.now(UTC) - timedelta(seconds=1)})
        assert sign_up_service.get_email_reserver_id(_OLD, OTHER_USER_ID, db) is None

    def test_it_is_not_reserved_before_the_change_is_confirmed(self, db):
        _request(db)

        assert sign_up_service.get_email_reserver_id(_OLD, OTHER_USER_ID, db) is None

    def test_it_is_released_by_the_revert(self, db):
        link = _reserve_for_owner(db)
        _revert(db, link)

        assert sign_up_service.get_email_reserver_id(_OLD, OTHER_USER_ID, db) is None

    def test_a_change_made_by_an_administrator_reserves_nothing(self, db):
        with patch(_PUBLISH):
            sign_up_service.stage_email_changed_notice(MOCK_USER_ID, _NEW, _OLD, db)
        db.commit()

        assert sign_up_service.get_email_reserver_id(_OLD, OTHER_USER_ID, db) is None

    def test_the_account_can_take_its_own_previous_address_back(self, db):
        _reserve_for_owner(db)

        assert users_service.is_email_available(MOCK_USER_ID, _OLD, db) is True
        assert users_service.is_email_available(OTHER_USER_ID, _OLD, db) is False
        assert users_service.is_email_available(None, _OLD, db) is False
        assert users_service.is_email_available(OTHER_USER_ID, "free@example.com", db) is True

    def test_the_revert_restores_it_when_nobody_could_take_it(self, db):
        link = _reserve_for_owner(db)
        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_email_available(OTHER_USER_ID, _OLD, db)

        assert _revert(db, link).email_restored is True
        assert _user(db).email == _OLD

    def test_an_administrator_cannot_create_an_account_on_it(self, db):
        _reserve_for_owner(db)
        created = users_schema.UserCreate(
            name="N", username="newone", email=_OLD, password="SecurePass1!", access_type="regular", active=True
        )

        with (
            patch("modules.users.users.service.credentials_integration"),
            pytest.raises(core_exceptions.ConflictError),
        ):
            users_service._stage_user(created, users_service.users_audit_actions.UserCreateMethod.ADMIN, db)

        assert db.query(users_models.Users).filter_by(username="newone").count() == 0

    def test_an_administrator_cannot_set_it_on_another_account(self, db):
        _reserve_for_owner(db)
        edit = users_schema.UserEdit.from_read(users_integration.get_user(OTHER_USER_ID, db)).model_copy(
            update={"email": _OLD}
        )

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_user_edit(OTHER_USER_ID, edit, db, if_match="*")

    def test_an_administrator_edit_that_asks_for_confirmation_is_refused_too(self, db):
        _reserve_for_owner(db)
        edit = users_schema.UserEdit.from_read(users_integration.get_user(OTHER_USER_ID, db)).model_copy(
            update={"email": _OLD, "email_verified": False}
        )

        with pytest.raises(core_exceptions.ConflictError):
            users_service._stage_edit_with_email_change(
                users_integration.get_user(OTHER_USER_ID, db), edit, _OLD.lower(), db, if_match="*"
            )

    def test_the_change_without_mail_is_refused(self, db):
        _reserve_for_owner(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_email_change(OTHER_USER_ID, _OLD, db)

    def test_a_confirmation_of_it_by_another_account_is_refused(self, db):
        _reserve_for_owner(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_confirmed_email_change(OTHER_USER_ID, _OLD, db)

    def test_a_provider_sync_does_not_copy_it(self, db):
        import modules.auth.identity_providers.user_provisioning_service as provisioning

        _reserve_for_owner(db)
        user = users_integration.get_user(OTHER_USER_ID, db)
        idp = MagicMock(sync_email=True)

        with (
            patch.object(provisioning.claim_mapping, "is_email_verified", return_value=True),
            patch.object(provisioning.claim_mapping, "map_user_claims", return_value={"email": _OLD}),
        ):
            assert provisioning._synced_email(user, idp, {"email": _OLD}, {}, db) is None

    def test_a_provider_created_account_cannot_take_it(self, db):
        _reserve_for_owner(db)
        settings = MagicMock(signup_require_email_verification=False, signup_require_admin_approval=False)
        profile = users_schema.UserBase(name="N", username="sso-new", email=_OLD)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.create_sso_user(profile, settings, db, email_verified=True)

    def test_a_sign_up_with_it_gets_the_answer_a_held_address_gets_and_creates_nothing(self, db):
        _reserve_for_owner(db)
        signup = users_schema.UserSignup(name="N", username="signer", email=_OLD, password="SecurePass1!")
        state = MemoryState()

        with patch(_PUBLISH) as publish, patch("modules.users.users.service.credentials_integration"):
            answer = sign_up_service.signup(signup, state, db)

        assert answer.next_step == sign_up_service.sign_up_schema.SignUpNextStep.SIGN_IN
        assert db.query(users_models.Users).filter_by(username="signer").count() == 0
        publish.assert_called_once()
        assert publish.call_args.args[1]["user_id"] == str(MOCK_USER_ID)

    def test_a_sign_up_with_it_answers_like_one_with_a_held_address(self, db):
        _reserve_for_owner(db)
        held = users_schema.UserSignup(name="N", username="signer", email=_NEW, password="SecurePass1!")
        reserved = users_schema.UserSignup(name="N", username="signer", email=_OLD, password="SecurePass1!")

        with patch(_PUBLISH), patch("modules.users.users.service.credentials_integration"):
            assert sign_up_service.signup(held, MemoryState(), db) == sign_up_service.signup(
                reserved, MemoryState(), db
            )

    def test_a_self_service_change_to_it_is_staged_like_a_held_address_and_tells_the_reserving_account(self, db):
        _reserve_for_owner(db)

        with patch(_PUBLISH) as publish:
            staged = sign_up_service.request_self_service_email_change(
                OTHER_USER_ID, _OLD, _OTHER_EMAIL, MemoryState(), db
            )
        db.commit()

        assert staged is True
        names = [call.args[0] for call in publish.call_args_list]
        assert "auth.email_change_address_taken" in names
        assert "auth.email_change_verification_requested" not in names
        taken = next(call for call in publish.call_args_list if call.args[0] == "auth.email_change_address_taken")
        assert taken.args[1]["user_id"] == str(MOCK_USER_ID)
        assert sign_up_service.prepare_email_change_verification_email(OTHER_USER_ID, "event-x", _HOST, db) is None

    def test_a_resend_for_it_sends_no_link(self, db):
        _reserve_for_owner(db)
        with patch(_PUBLISH):
            sign_up_service.request_self_service_email_change(OTHER_USER_ID, _OLD, _OTHER_EMAIL, MemoryState(), db)
        db.commit()

        with patch(_PUBLISH) as publish:
            sign_up_service.request_email_change_resend(OTHER_USER_ID, MemoryState(), db)

        assert [call.args[0] for call in publish.call_args_list] == ["auth.email_change_address_taken"]


def _assert_secured(db, platform, security_generations, reset_token: uuid.UUID) -> None:
    """Assert that the owner's account was secured: generation moved, sessions and keys ended, reset links void."""
    assert MOCK_USER_ID in security_generations.bumps
    platform.sessions.assert_called_once_with(MOCK_USER_ID, db)
    platform.keys.assert_called_once_with(MOCK_USER_ID, db)
    assert _reset_token_used(db, reset_token) is True


class TestTheLinkBeforeConfirmation:
    def test_cancels_the_pending_change(self, db, platform, security_generations):
        link = _request(db)
        reset_token = _seed_reset_token(db)

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, link)

        assert (result.email_restored, result.change_applied) == (False, False)
        assert _user(db).email == _OLD
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        _assert_secured(db, platform, security_generations, reset_token)
        details = audit.assert_audited(_ACTION, target_id=str(MOCK_USER_ID)).details
        assert (details["change_applied"], details["reset_tokens_revoked"]) == (False, True)

    def test_works_once(self, db):
        link = _request(db)
        _revert(db, link)

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, link)

    def test_an_earlier_requests_link_voids_the_later_pending_request_and_secures_the_account(
        self, db, platform, security_generations
    ):
        first = _request(db)
        second = _request(db, new="other@example.com")
        reset_token = _seed_reset_token(db)

        with jasil_testing.capture_audit() as audit:
            result = _revert(db, first)

        assert (result.email_restored, result.change_applied) == (False, False)
        assert _user(db).email == _OLD
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        assert sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-2", _HOST, db) is None
        _assert_secured(db, platform, security_generations, reset_token)
        details = audit.assert_audited(_ACTION, target_id=str(MOCK_USER_ID)).details
        assert (details["change_applied"], details["reset_tokens_revoked"]) == (False, True)
        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, second)

    @pytest.mark.parametrize("later_confirmed", [False, True])
    def test_a_replaced_changes_link_works_whether_or_not_the_later_change_was_confirmed(
        self, db, platform, later_confirmed
    ):
        first = _request(db)
        _request(db, new="third@example.com")
        if later_confirmed:
            _confirm(db, event="event-2")

        result = _revert(db, first)

        assert (result.change_applied, result.email_restored) == (later_confirmed, later_confirmed)
        assert _user(db).email == _OLD
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0
        platform.sessions.assert_called_once_with(MOCK_USER_ID, db)

    def test_a_replaced_changes_link_works_once(self, db, platform):
        first = _request(db)
        _request(db, new="third@example.com")
        _revert(db, first)
        platform.sessions.reset_mock()

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, first)

        platform.sessions.assert_not_called()

    def test_a_replaced_changes_link_is_refused_seven_days_after_the_request(self, db, platform):
        first = _request(db)
        _request(db, new="third@example.com")

        with patch(f"{_SERVICE}.datetime") as clock, pytest.raises(core_exceptions.InvalidInputError):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=7, minutes=1)
            _revert(db, first)
        db.rollback()

        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).one().email == "third@example.com"
        platform.sessions.assert_not_called()

    def test_an_expired_unconfirmed_change_is_still_reported_and_secures_the_account(
        self, db, platform, security_generations
    ):
        link = _request(db)
        reset_token = _seed_reset_token(db)

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=2)
            result = _revert(db, link)

        assert (result.email_restored, result.change_applied) == (False, False)
        assert _user(db).email == _OLD
        _assert_secured(db, platform, security_generations, reset_token)

    def test_an_expired_unconfirmed_changes_link_works_once(self, db, platform):
        link = _request(db)

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=2)
            _revert(db, link)
            platform.sessions.reset_mock()
            with pytest.raises(core_exceptions.InvalidInputError):
                _revert(db, link)

        platform.sessions.assert_not_called()

    def test_an_expired_unconfirmed_changes_link_is_refused_seven_days_after_the_request(self, db, platform):
        link = _request(db)

        with patch(f"{_SERVICE}.datetime") as clock, pytest.raises(core_exceptions.InvalidInputError):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=7, minutes=1)
            _revert(db, link)

        platform.sessions.assert_not_called()


class TestChangesTheOwnerDidNotRequest:
    def test_an_applied_change_notice_has_no_revert_link_and_no_link_can_be_made_for_it(self, db, platform):
        sign_up_service.request_email_change(MOCK_USER_ID, _NEW, _OLD, db)
        db.commit()
        message = sign_up_service.prepare_email_change_verification_email(MOCK_USER_ID, "event-1", _HOST, db)
        assert message is not None
        raw = message[2].split("?token=")[1].split('"')[0].split("<")[0].split("&")[0]
        with patch(_PUBLISH) as publish:
            sign_up_service.confirm_email_change(raw, db)

        notice = sign_up_service.prepare_email_changed_email(
            MOCK_USER_ID, uuid.UUID(publish.call_args.args[1]["token_id"]), _HOST, db
        )

        assert notice is not None
        assert "cancel-email-change" not in notice[2] + notice[3]
        rows = db.query(sign_up_models.SignUpToken).all()
        assert all(row.change_id is None and row.revert_until is None for row in rows)
        for row in rows:
            forged = f"{row.id}.{sign_up_service._revert_mac(row.id, datetime.now(UTC) + timedelta(days=7))}"
            with pytest.raises(core_exceptions.InvalidInputError):
                _revert(db, forged)
        assert _user(db).email == _NEW
        platform.sessions.assert_not_called()

    def test_a_synced_change_notice_has_no_revert_link(self, db):
        sign_up_service.stage_email_changed_notice(MOCK_USER_ID, _NEW, _OLD, db)
        db.commit()
        row = db.query(sign_up_models.SignUpToken).one()

        notice = sign_up_service.prepare_email_changed_email(MOCK_USER_ID, row.id, _HOST, db)

        assert notice is not None
        assert "cancel-email-change" not in notice[2] + notice[3]
        assert (row.change_id, row.revert_until) == (None, None)


class TestRefusals:
    @pytest.mark.parametrize("token", ["", "garbage", "a.b", "7.9999999999.deadbeef", "x.1.2"])
    def test_a_malformed_or_forged_link_is_refused_and_changes_nothing(self, db, platform, token):
        _request(db)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, token)

        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 1
        platform.sessions.assert_not_called()
        audit.assert_audited(_ACTION, outcome="failure")

    def test_a_link_minted_from_the_canonical_text_of_the_id_still_resolves(self, db, platform):
        _request(db)
        row = db.query(sign_up_models.SignUpToken).filter(sign_up_models.SignUpToken.change_id.is_not(None)).one()
        mac = access_tokens_integration.derive_email_token(
            f"email-change-revert:{row.change_id!s}:{int(row.revert_until.timestamp())}"
        )

        result = _revert(db, f"{row.change_id}.{mac}")

        assert result.change_applied is False
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 0

    def test_a_link_whose_id_part_is_not_a_uuid_is_refused_like_a_bad_proof(self, db, platform):
        _request(db)
        row = db.query(sign_up_models.SignUpToken).filter(sign_up_models.SignUpToken.change_id.is_not(None)).one()
        mac = sign_up_service._revert_mac(row.change_id, row.revert_until)

        with pytest.raises(core_exceptions.InvalidInputError) as refused:
            _revert(db, f"not-a-uuid.{mac}")

        with pytest.raises(core_exceptions.InvalidInputError) as forged:
            _revert(db, f"{row.change_id}.forged")
        assert str(refused.value) == str(forged.value)
        assert db.query(sign_up_models.SignUpToken).filter_by(used=False).count() == 1
        platform.sessions.assert_not_called()

    def test_a_link_with_a_forged_proof_is_refused(self, db, platform):
        link = _request(db)
        change_id = link.split(".")[0]

        with pytest.raises(core_exceptions.InvalidInputError):
            _revert(db, f"{change_id}.forged")

        platform.sessions.assert_not_called()


class TestRowsOutliveTheRevertWindow:
    def test_an_email_change_row_is_kept_for_seven_days(self, db):
        _request(db)
        _confirm(db)

        now = datetime.now(UTC)
        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = now + timedelta(days=2)
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 0
            clock.now.return_value = now + timedelta(days=8)
            assert sign_up_service.delete_expired_sign_up_tokens(db) > 0
        assert db.query(sign_up_models.SignUpToken).count() == 0

    def test_a_sign_up_token_is_still_deleted_when_it_expires(self, db):
        sign_up_service.create_sign_up_token(MOCK_USER_ID, _OLD, "event-1", db)

        with patch(f"{_SERVICE}.datetime") as clock:
            clock.now.return_value = datetime.now(UTC) + timedelta(days=2)
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 1
