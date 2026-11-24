"""A pending email change from the profile and from the administrator's edit, on the real database."""

import pytest
from sqlalchemy import select

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as session_models
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_profile.service as profile_service
from tests._factories.server_settings import edit_mail_settings
from tests._factories.users import PASSWORD, make_admin, make_user

_REQUESTED = sign_up_events.EMAIL_CHANGE_REQUESTED
_VERIFICATION = sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED
_TAKEN = sign_up_events.EMAIL_CHANGE_ADDRESS_TAKEN
_CHANGED = sign_up_events.EMAIL_CHANGED
_RESET = "auth.password_reset_requested"
_CHANNELS = (_REQUESTED, _VERIFICATION, _TAKEN, _CHANGED, _RESET)


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def events(platform):
    """The email events the bus carries, in order."""
    seen = []
    for channel in _CHANNELS:
        platform.events.subscribe(channel, seen.append)
    return seen


@pytest.fixture
def mail(committed_sessions):
    """Configure a mail server, so a new address can be confirmed by email."""
    with committed_sessions() as db:
        edit_mail_settings(db, host="smtp.example.com")
        db.commit()


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, name="Owner")
        db.commit()
    return created


@pytest.fixture
def holder(committed_sessions):
    """Another account, which holds an address the owner may ask for."""
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def step_up_store(platform):
    return account_security_integration.get_step_up_attempts(platform.state)


def _change(committed_sessions, owner, email, step_up_store, platform, *, session=None, revoke=False):
    change = users_schema.EmailChange(email=email, step_up={"current_password": PASSWORD}, revoke_other_sessions=revoke)
    with committed_sessions() as db:
        return profile_service.change_email(owner.id, change, session or owner.id, step_up_store, platform.state, db)


def _user(committed_sessions, user_id):
    with committed_sessions() as db:
        return users_service.require_user(user_id, db)


def _unused_tokens(committed_sessions, user_id):
    with committed_sessions() as db:
        return db.scalars(select(sign_up_models.SignUpToken).filter_by(user_id=user_id, used=False)).all()


def _names(events):
    return [event.event_type for event in events]


def _session_ids(committed_sessions, user_id):
    with committed_sessions() as db:
        return set(
            db.scalars(select(session_models.UsersSessions.id).where(session_models.UsersSessions.user_id == user_id))
        )


class TestSelfServiceEmailChange:
    def test_the_address_and_verified_flag_stay_while_a_token_and_the_events_are_staged(
        self, committed_sessions, platform, owner, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, "New@Example.com", step_up_store, platform)

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.email_verified) == (owner.email, True)
        tokens = _unused_tokens(committed_sessions, owner.id)
        assert [(t.email, t.previous_email) for t in tokens] == [("new@example.com", owner.email)]
        assert _names(events) == [_REQUESTED, _VERIFICATION]
        assert all(event.payload["user_id"] == str(owner.id) for event in events)

    def test_the_answer_is_the_profile_with_the_change_pending(
        self, committed_sessions, platform, owner, step_up_store, mail, events
    ):
        profile = _change(committed_sessions, owner, "new@example.com", step_up_store, platform)

        assert profile.pending_email == "new@example.com"
        assert profile.pending_email_expires_at is not None
        assert profile.email == owner.email

    def test_a_second_change_replaces_the_first(self, committed_sessions, platform, owner, step_up_store, mail, events):
        _change(committed_sessions, owner, "first@example.com", step_up_store, platform)
        _change(committed_sessions, owner, "second@example.com", step_up_store, platform)

        assert [t.email for t in _unused_tokens(committed_sessions, owner.id)] == ["second@example.com"]
        assert _user(committed_sessions, owner.id).email == owner.email

    def test_resubmitting_the_current_address_cancels_a_pending_change_and_keeps_the_sessions(
        self, committed_sessions, platform, owner, step_up_store, mail, events, sign_in
    ):
        mine, other_session = sign_in(owner), sign_in(owner)
        _change(committed_sessions, owner, "new@example.com", step_up_store, platform, session=mine.session_id)

        profile = _change(
            committed_sessions,
            owner,
            owner.email.upper(),
            step_up_store,
            platform,
            session=mine.session_id,
            revoke=True,
        )

        assert _unused_tokens(committed_sessions, owner.id) == []
        assert profile.pending_email is None
        assert _user(committed_sessions, owner.id).email_verified is True
        assert _session_ids(committed_sessions, owner.id) == {mine.session_id, other_session.session_id}

    def test_an_address_of_another_account_is_pending_like_a_free_one_and_its_holder_is_told(
        self, committed_sessions, platform, owner, holder, step_up_store, mail, events
    ):
        profile = _change(committed_sessions, owner, holder.email.capitalize(), step_up_store, platform)

        assert profile.pending_email == holder.email
        assert [(t.email, t.previous_email) for t in _unused_tokens(committed_sessions, owner.id)] == [
            (holder.email, owner.email)
        ]
        assert _user(committed_sessions, holder.id).email == holder.email
        assert _names(events) == [_REQUESTED, _TAKEN]
        assert events[1].payload["user_id"] == str(holder.id)

    def test_a_second_attempt_inside_the_hour_answers_the_same_without_telling_the_holder_again(
        self, committed_sessions, platform, owner, holder, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, holder.email, step_up_store, platform)
        _change(committed_sessions, owner, holder.email, step_up_store, platform)

        assert [t.email for t in _unused_tokens(committed_sessions, owner.id)] == [holder.email]
        assert _names(events) == [_REQUESTED, _TAKEN, _REQUESTED]

    def test_a_taken_address_without_mail_is_a_conflict_and_changes_nothing(
        self, committed_sessions, platform, owner, holder, step_up_store, events
    ):
        with pytest.raises(core_exceptions.ConflictError):
            _change(committed_sessions, owner, holder.email, step_up_store, platform)

        assert _user(committed_sessions, owner.id).email == owner.email
        assert events == []

    def test_without_mail_the_address_changes_at_once_unverified_and_pending_links_are_voided(
        self, committed_sessions, platform, owner, step_up_store, events
    ):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()
        _change(committed_sessions, owner, "pending@example.com", step_up_store, platform)
        assert len(_unused_tokens(committed_sessions, owner.id)) == 1
        with committed_sessions() as db:
            edit_mail_settings(db, host=None)
            db.commit()
        events.clear()

        profile = _change(committed_sessions, owner, "new@example.com", step_up_store, platform)

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.email_verified) == ("new@example.com", False)
        assert profile.email == "new@example.com"
        assert _unused_tokens(committed_sessions, owner.id) == []
        assert events == []

    def test_a_requested_address_leaves_the_security_generation_alone_and_an_applied_one_advances_it(
        self, committed_sessions, platform, owner, step_up_store, events
    ):
        with committed_sessions() as db:
            before = security_generation_integration.current_generation(owner.id, db)
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()

        _change(committed_sessions, owner, "requested@example.com", step_up_store, platform)
        with committed_sessions() as db:
            after_request = security_generation_integration.current_generation(owner.id, db)
            edit_mail_settings(db, host=None)
            db.commit()
        _change(committed_sessions, owner, "applied@example.com", step_up_store, platform)

        with committed_sessions() as db:
            after_applied = security_generation_integration.current_generation(owner.id, db)
        assert after_request == before
        assert after_applied > before

    def test_other_sessions_are_revoked_when_asked(
        self, committed_sessions, platform, owner, step_up_store, mail, events, sign_in
    ):
        mine, other_session = sign_in(owner), sign_in(owner)

        _change(
            committed_sessions, owner, "new@example.com", step_up_store, platform, session=mine.session_id, revoke=True
        )

        assert _session_ids(committed_sessions, owner.id) == {mine.session_id}
        assert other_session.session_id not in _session_ids(committed_sessions, owner.id)

    def test_other_sessions_stay_when_the_client_opts_out(
        self, committed_sessions, platform, owner, step_up_store, mail, events, sign_in
    ):
        mine, other_session = sign_in(owner), sign_in(owner)

        _change(committed_sessions, owner, "new@example.com", step_up_store, platform, session=mine.session_id)

        assert _session_ids(committed_sessions, owner.id) == {mine.session_id, other_session.session_id}

    def test_a_failed_step_up_changes_nothing(self, committed_sessions, platform, owner, step_up_store, mail, events):
        change = users_schema.EmailChange(email="new@example.com", step_up={"current_password": "wrong"})

        with committed_sessions() as db, pytest.raises(core_exceptions.StepUpFailedError):
            profile_service.change_email(owner.id, change, owner.id, step_up_store, platform.state, db)

        assert _unused_tokens(committed_sessions, owner.id) == []
        assert events == []


class TestResendAndCancel:
    def test_cancelling_lapses_the_link_and_clears_the_pending_change(
        self, committed_sessions, platform, owner, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, "new@example.com", step_up_store, platform)

        with committed_sessions() as db:
            profile_service.cancel_email_change(owner.id, db)

        assert _unused_tokens(committed_sessions, owner.id) == []
        assert _user(committed_sessions, owner.id).email == owner.email

    def test_resending_stages_the_event_once_per_cooldown(
        self, committed_sessions, platform, owner, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, "new@example.com", step_up_store, platform)
        events.clear()

        for _ in range(2):
            with committed_sessions() as db:
                profile_service.resend_email_change(owner.id, platform.state, db)

        assert _names(events) == [_VERIFICATION]

    def test_resending_with_nothing_pending_does_nothing(self, committed_sessions, platform, owner, mail, events):
        with committed_sessions() as db:
            profile_service.resend_email_change(owner.id, platform.state, db)

        assert events == []


class TestPasswordResetWhilePending:
    def test_the_reset_still_targets_the_old_address(
        self, committed_sessions, platform, owner, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, "new@example.com", step_up_store, platform)
        events.clear()

        with committed_sessions() as db:
            password_reset_service.request_password_reset_email("new@example.com", "203.0.113.7", "agent", db)
            password_reset_service.request_password_reset_email(owner.email, "203.0.113.7", "agent", db)

        assert [event.payload["user_id"] for event in events if event.event_type == _RESET] == [None, str(owner.id)]


class TestAdminEmailEdit:
    @pytest.fixture
    def admin(self, committed_sessions):
        with committed_sessions() as db:
            created = make_admin(db)
            db.commit()
        return created

    def _edit(self, committed_sessions, step_up_store, admin, target, **overrides):
        with committed_sessions() as db:
            current = users_service.require_user(target.id, db)
            edit = users_schema.UserEdit.from_read(current).model_copy(update=overrides)
            return users_service.edit_user(
                target.id,
                edit,
                auth_schema.StepUpVerification(current_password=PASSWORD),
                admin.id,
                admin.id,
                step_up_store,
                db,
                if_match=core_etag.format_etag(current.version),
            )

    def test_an_unchanged_email_edits_as_before(
        self, committed_sessions, platform, owner, admin, step_up_store, mail, events, sign_in
    ):
        session = sign_in(owner)

        updated = self._edit(committed_sessions, step_up_store, admin, owner, name="Renamed")

        assert (updated.name, updated.pending_email) == ("Renamed", None)
        assert events == []
        assert _session_ids(committed_sessions, owner.id) == {session.session_id}

    def test_a_changed_unverified_email_is_pending_and_ends_the_sessions(
        self, committed_sessions, platform, owner, admin, step_up_store, mail, events, sign_in
    ):
        sign_in(owner)

        updated = self._edit(
            committed_sessions, step_up_store, admin, owner, email="New@Example.com", email_verified=False
        )

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.email_verified) == (owner.email, True)
        assert (updated.email, updated.email_verified) == (owner.email, True)
        assert updated.pending_email == "new@example.com"
        assert updated.pending_email_expires_at is not None
        assert _names(events) == [_REQUESTED, _VERIFICATION]
        assert _session_ids(committed_sessions, owner.id) == set()

    def test_a_changed_email_marked_verified_applies_at_once_and_cancels_a_pending_change(
        self, committed_sessions, platform, owner, admin, step_up_store, mail, events, sign_in
    ):
        sign_in(owner)
        _change(committed_sessions, owner, "pending@example.com", step_up_store, platform)

        updated = self._edit(
            committed_sessions, step_up_store, admin, owner, email="New@Example.com", email_verified=True
        )

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.email_verified) == ("new@example.com", True)
        assert updated.pending_email is None
        assert _unused_tokens(committed_sessions, owner.id) == []
        assert _session_ids(committed_sessions, owner.id) == set()

    def test_an_applied_address_tells_the_previous_one(
        self, committed_sessions, platform, owner, admin, step_up_store, mail, events
    ):
        self._edit(committed_sessions, step_up_store, admin, owner, email="New@Example.com", email_verified=True)

        with committed_sessions() as db:
            notice = db.scalars(select(sign_up_models.SignUpToken).filter_by(user_id=owner.id)).one()
        assert (notice.previous_email, notice.email, notice.used) == (owner.email, "new@example.com", True)
        assert _names(events) == [_CHANGED]
        assert events[0].payload == {"user_id": str(owner.id), "token_id": str(notice.id)}

    def test_without_mail_an_applied_address_stages_no_notice_and_voids_pending_links(
        self, committed_sessions, platform, owner, admin, step_up_store, events
    ):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()
        _change(committed_sessions, owner, "pending@example.com", step_up_store, platform)
        with committed_sessions() as db:
            edit_mail_settings(db, host=None)
            db.commit()
        events.clear()

        self._edit(committed_sessions, step_up_store, admin, owner, email="new@example.com", email_verified=True)

        assert _user(committed_sessions, owner.id).email == "new@example.com"
        assert _unused_tokens(committed_sessions, owner.id) == []
        assert events == []

    def test_without_mail_a_changed_email_applies_unverified(
        self, committed_sessions, platform, owner, admin, step_up_store, events, sign_in
    ):
        sign_in(owner)

        updated = self._edit(
            committed_sessions, step_up_store, admin, owner, email="new@example.com", email_verified=False
        )

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.email_verified) == ("new@example.com", False)
        assert (updated.email, updated.email_verified, updated.pending_email) == ("new@example.com", False, None)
        assert _session_ids(committed_sessions, owner.id) == set()

    def test_deactivating_with_a_changed_email_leaves_no_link_that_could_reactivate(
        self, committed_sessions, platform, owner, admin, step_up_store, mail, events
    ):
        updated = self._edit(
            committed_sessions, step_up_store, admin, owner, email="new@example.com", email_verified=False, active=False
        )

        user = _user(committed_sessions, owner.id)
        assert (user.email, user.active) == (owner.email, False)
        assert updated.pending_email is None
        assert _unused_tokens(committed_sessions, owner.id) == []

    def test_a_changed_email_of_another_account_is_a_conflict_and_changes_nothing(
        self, committed_sessions, platform, owner, holder, admin, step_up_store, mail, events
    ):
        with pytest.raises(core_exceptions.ConflictError):
            self._edit(committed_sessions, step_up_store, admin, owner, email=holder.email, name="Renamed")

        assert _user(committed_sessions, owner.id).name == "Owner"
        assert _unused_tokens(committed_sessions, owner.id) == []
        assert events == []

    def test_the_admin_read_and_the_list_carry_the_pending_change(
        self, committed_sessions, platform, owner, holder, step_up_store, mail, events
    ):
        _change(committed_sessions, owner, "new@example.com", step_up_store, platform)

        with committed_sessions() as db:
            assert users_service.require_user_with_pending_email(owner.id, db).pending_email == "new@example.com"
            listed = {user.id: user for user in users_service.list_users(db).items}
        assert listed[owner.id].pending_email == "new@example.com"
        assert listed[holder.id].pending_email is None
