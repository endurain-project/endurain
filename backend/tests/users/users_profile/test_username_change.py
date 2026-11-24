"""The dedicated username change: schema, step-up, conflict, no-op, session revocation, audit and notice."""

import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog
from pydantic import ValidationError

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as session_models
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.service as profile_service
from tests._factories.users import PASSWORD, make_user


class TestUsernameChangeSchema:
    def test_revokes_other_sessions_by_default(self):
        assert users_schema.UsernameChange(username="ada", step_up={"current_password": "pw"}).revoke_other_sessions

    @pytest.mark.parametrize("username", ["", "has space", "a" * 251, "bad/char"])
    def test_refuses_what_the_profile_edit_used_to_refuse(self, username):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username=username, step_up={"current_password": "pw"})

    def test_requires_step_up(self):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username="ada")

    def test_refuses_unknown_fields(self):
        with pytest.raises(ValidationError):
            users_schema.UsernameChange(username="ada", step_up={"current_password": "pw"}, email="a@b.co")

    def test_the_profile_update_no_longer_takes_a_username(self):
        with pytest.raises(ValidationError):
            users_schema.ProfileUpdate(username="ada")


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def step_up_store(platform):
    return account_security_integration.get_step_up_attempts(platform.state)


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, username="old")
        db.commit()
    return created


@pytest.fixture
def notices(platform):
    """The account-security notices the bus carries."""
    seen = []
    platform.events.subscribe(account_security_events.ACCOUNT_SECURITY_CHANGED, seen.append)
    return seen


def _change(
    committed_sessions, step_up_store, owner, username="New.Name", *, revoke=True, session=None, password=PASSWORD
):
    change = users_schema.UsernameChange(
        username=username, step_up={"current_password": password}, revoke_other_sessions=revoke
    )
    with committed_sessions() as db:
        return profile_service.change_username(owner.id, change, session or owner.id, step_up_store, db)


def _username(committed_sessions, user_id):
    with committed_sessions() as db:
        return users_integration.require_user(user_id, db).username


def _audit(committed_sessions):
    with committed_sessions() as db:
        return list(
            db.scalars(sa.select(AuditLog).where(AuditLog.action_id == profile_audit_actions.USERNAME_CHANGE.id))
        )


def _sessions(committed_sessions, user_id):
    with committed_sessions() as db:
        return set(db.scalars(sa.select(session_models.UsersSessions.id).filter_by(user_id=user_id)))


class TestChangeUsername:
    def test_the_lower_cased_username_is_stored_and_the_profile_comes_back(
        self, committed_sessions, owner, step_up_store, notices
    ):
        profile = _change(committed_sessions, step_up_store, owner)

        assert profile.username == "new.name"
        assert _username(committed_sessions, owner.id) == "new.name"

    def test_a_failed_step_up_changes_nothing(self, committed_sessions, owner, step_up_store, notices):
        with pytest.raises(core_exceptions.StepUpFailedError):
            _change(committed_sessions, step_up_store, owner, password="wrong")

        assert _username(committed_sessions, owner.id) == "old"
        assert notices == [] and _audit(committed_sessions) == []

    def test_a_taken_username_is_a_conflict_and_changes_nothing(
        self, committed_sessions, owner, step_up_store, notices
    ):
        with committed_sessions() as db:
            holder = make_user(db, username="taken")
            db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            _change(committed_sessions, step_up_store, owner, "TAKEN")

        assert _username(committed_sessions, owner.id) == "old"
        assert _username(committed_sessions, holder.id) == "taken"
        assert _audit(committed_sessions) == []

    def test_resubmitting_the_current_username_in_any_case_is_a_no_op(
        self, committed_sessions, owner, step_up_store, notices, sign_in
    ):
        mine, other = sign_in(owner), sign_in(owner)

        _change(committed_sessions, step_up_store, owner, "OLD", session=mine.session_id)

        assert notices == [] and _audit(committed_sessions) == []
        assert _sessions(committed_sessions, owner.id) == {mine.session_id, other.session_id}

    def test_other_sessions_end_when_asked_and_stay_when_the_client_opts_out(
        self, committed_sessions, owner, step_up_store, notices, sign_in
    ):
        mine, other = sign_in(owner), sign_in(owner)

        _change(committed_sessions, step_up_store, owner, "first", revoke=False, session=mine.session_id)
        assert _sessions(committed_sessions, owner.id) == {mine.session_id, other.session_id}

        _change(committed_sessions, step_up_store, owner, "second", revoke=True, session=mine.session_id)
        assert _sessions(committed_sessions, owner.id) == {mine.session_id}

    def test_the_account_owner_is_told(self, committed_sessions, owner, step_up_store, notices):
        _change(committed_sessions, step_up_store, owner)

        assert [(event.payload["user_id"], event.payload["change"]) for event in notices] == [
            (str(owner.id), account_security_events.AccountSecurityChange.USERNAME_CHANGED.value)
        ]

    @pytest.mark.parametrize("revoke", [True, False])
    def test_the_change_is_audited_without_the_username(
        self, committed_sessions, owner, step_up_store, notices, revoke
    ):
        _change(committed_sessions, step_up_store, owner, "audited.name", revoke=revoke)

        (row,) = _audit(committed_sessions)
        assert row.details == {"other_sessions_revoked": revoke}
        assert (row.target_id, row.target_owner_id) == (str(owner.id), str(owner.id))
        assert "audited.name" not in str(row.details)

    def test_the_security_generation_stays_as_it_is(self, committed_sessions, owner, step_up_store, notices):
        with committed_sessions() as db:
            before = security_generation_integration.current_generation(owner.id, db)

        _change(committed_sessions, step_up_store, owner)

        with committed_sessions() as db:
            assert security_generation_integration.current_generation(owner.id, db) == before
