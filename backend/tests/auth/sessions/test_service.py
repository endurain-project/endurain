"""Sessions are created, rotated, claimed, listed and ended against real rows, with their audit rows and events."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.constants as auth_constants
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.rotated_refresh_tokens.integration_service as rotated_refresh_tokens_integration
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.events as sessions_events
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.service as sessions_service
from tests._factories.auth import make_session
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_STEP_UP = auth_schema.StepUpVerification(current_password="admin-password")
_ABSOLUTE_TIMEOUT = timedelta(hours=720)
_FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"


def _accepting(step_up) -> None:
    """A step-up verifier that accepts."""


def _refusing(step_up) -> None:
    raise core_exceptions.StepUpFailedError


def _audit(db, action) -> list[AuditLog]:
    return list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action.id)))


def _state(db, state_id: str) -> str:
    oauth_state_integration.create_oauth_state(
        state_id, "n" * 32, "web", "127.0.0.1", db, purpose=oauth_state_constants.OAuthStatePurpose.LOGIN
    )
    db.flush()
    return state_id


def _state_ids(db) -> set[str]:
    return set(db.scalars(sa.select(oauth_state_models.OAuthState.id)))


def _session_ids(db) -> set[uuid.UUID]:
    return set(db.scalars(sa.select(sessions_models.UsersSessions.id)))


_RAW_TOKEN = "raw-refresh-token"


def _create(db, user, *, refresh_token: str | None = _RAW_TOKEN, expires_at=None, **kwargs):
    return sessions_service.create_session(
        kwargs.pop("session_id", uuid.uuid4()),
        user,
        auth_constants.ClientType.WEB,
        "203.0.113.5",
        _FIREFOX,
        refresh_token,
        expires_at or datetime.now(UTC) + timedelta(days=1),
        db,
        amr=["pwd"],
        device_hash=kwargs.pop("device_hash", None),
        **kwargs,
    )


class TestCreate:
    def test_a_session_stores_a_digest_and_the_clients_details_not_the_token(self, db):
        user = make_user(db)
        session_id = uuid.uuid4()

        session = _create(db, user, session_id=session_id, device_hash="d" * 64)

        assert session.refresh_token == sessions_service.hash_refresh_token("raw-refresh-token")
        assert "raw-refresh-token" not in repr(session)
        assert (session.token_family_id, session.tokens_exchanged, session.rotation_count) == (session_id, True, 0)
        assert (session.ip_address, session.browser, session.operating_system) == ("203.0.113.5", "Firefox", "Linux")
        assert (session.device_hash, session.amr) == ("d" * 64, ["pwd"])
        assert sessions_crud.get_session_by_id(session_id, db) == session

    def test_a_session_created_without_a_refresh_token_awaits_its_exchange(self, db):
        user = make_user(db)

        session = _create(db, user, refresh_token=None, oauth_state_id=_state(db, "state-1"))

        assert (session.refresh_token, session.tokens_exchanged) == (None, False)
        assert session.oauth_state_id == "state-1"

    def test_a_session_records_the_app_redirect_uri_of_a_native_sign_in(self, db):
        session = _create(db, make_user(db), app_redirect_uri="endurain://callback")

        assert sessions_crud.get_session_by_id(session.id, db).app_redirect_uri == "endurain://callback"

    def test_the_expiry_is_capped_at_the_absolute_timeout(self, db):
        session = _create(db, make_user(db), expires_at=datetime.now(UTC) + timedelta(days=3650))

        assert session.expires_at == pytest.approx(session.created_at + _ABSOLUTE_TIMEOUT, abs=timedelta(seconds=1))

    def test_an_earlier_expiry_is_kept(self, db):
        expires_at = datetime.now(UTC) + timedelta(hours=2)

        session = _create(db, make_user(db), expires_at=expires_at)

        assert session.expires_at == expires_at


class TestRotation:
    def test_a_rotation_digests_the_new_token_counts_it_and_keeps_the_sessions_other_details(self, db):
        session = _create(db, make_user(db), device_hash="d" * 64, app_redirect_uri="endurain://callback")

        rotated = sessions_service.edit_session(
            session,
            "198.51.100.9",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "new-token",
            session.expires_at,
            db,
        )

        assert rotated.refresh_token == sessions_service.hash_refresh_token("new-token")
        assert (rotated.rotation_count, rotated.ip_address) == (1, "198.51.100.9")
        assert rotated.last_rotation_at is not None
        assert rotated.device_type == "Mobile"
        assert (rotated.device_hash, rotated.app_redirect_uri) == ("d" * 64, "endurain://callback")
        assert (rotated.created_at, rotated.token_family_id) == (session.created_at, session.token_family_id)

    def test_the_rotated_expiry_is_capped_at_creation_plus_the_absolute_timeout(self, db):
        user = make_user(db)
        session = make_session(db, user, created_at=datetime.now(UTC) - timedelta(hours=700))

        rotated = sessions_service.edit_session(
            session, "127.0.0.1", _FIREFOX, "new", datetime.now(UTC) + timedelta(days=7), db
        )

        assert rotated.expires_at == session.created_at + _ABSOLUTE_TIMEOUT

    def test_an_earlier_rotated_expiry_is_kept(self, db):
        session = make_session(db, make_user(db))
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        rotated = sessions_service.edit_session(session, "127.0.0.1", _FIREFOX, "new", expires_at, db)

        assert rotated.expires_at == expires_at

    def test_rotating_a_session_that_is_gone_is_not_found(self, db):
        session = make_session(db, make_user(db))
        db.execute(sa.delete(sessions_models.UsersSessions))

        with pytest.raises(core_exceptions.NotFoundError):
            sessions_service.edit_session(session, "127.0.0.1", _FIREFOX, "new", session.expires_at, db)


class TestClaim:
    def test_the_claim_stores_the_digest_extends_the_session_clears_its_state_and_marks_it_exchanged(self, db):
        user = make_user(db)
        state_id = _state(db, "state-1")
        pending = make_session(
            db, user, exchanged=False, expires_at=datetime.now(UTC) + timedelta(minutes=5), oauth_state_id=state_id
        )
        refresh_exp = datetime.now(UTC) + timedelta(days=7)

        expires_at = sessions_service.claim_session_for_token_exchange(
            pending.id, "digest", refresh_exp, ["fed", "otp", "mfa"], db
        )

        claimed = sessions_crud.get_session_by_id(pending.id, db)
        assert expires_at == refresh_exp
        assert claimed.tokens_exchanged is True
        assert (claimed.refresh_token, claimed.expires_at, claimed.amr) == (
            "digest",
            refresh_exp,
            ["fed", "otp", "mfa"],
        )
        assert claimed.oauth_state_id is None
        assert state_id not in _state_ids(db)

    def test_the_new_expiry_is_capped_at_the_absolute_timeout(self, db):
        pending = make_session(db, make_user(db), exchanged=False, created_at=datetime.now(UTC) - timedelta(hours=718))

        expires_at = sessions_service.claim_session_for_token_exchange(
            pending.id, "digest", datetime.now(UTC) + timedelta(days=7), ["pwd"], db
        )

        assert expires_at == pending.created_at + _ABSOLUTE_TIMEOUT

    def test_a_second_claim_of_the_same_session_is_refused(self, db):
        pending = make_session(db, make_user(db), exchanged=False)
        refresh_exp = datetime.now(UTC) + timedelta(days=7)
        assert sessions_service.claim_session_for_token_exchange(pending.id, "first", refresh_exp, ["pwd"], db)

        assert sessions_service.claim_session_for_token_exchange(pending.id, "second", refresh_exp, ["pwd"], db) is None
        assert sessions_crud.get_session_by_id(pending.id, db).refresh_token == "first"

    def test_a_missing_session_is_refused(self, db):
        refresh_exp = datetime.now(UTC) + timedelta(days=7)

        assert (
            sessions_service.claim_session_for_token_exchange(uuid.uuid4(), "digest", refresh_exp, ["pwd"], db) is None
        )

    def test_the_session_and_its_oauth_state_are_read_together_until_the_state_is_cleared(self, db):
        state_id = _state(db, "state-1")
        pending = make_session(db, make_user(db), exchanged=False, oauth_state_id=state_id)

        found = sessions_service.get_session_with_oauth_state(pending.id, db)

        assert found is not None
        session, state = found
        assert (session.id, state.id) == (pending.id, state_id)
        sessions_service.claim_session_for_token_exchange(
            pending.id, "digest", datetime.now(UTC) + timedelta(days=1), ["pwd"], db
        )
        assert sessions_service.get_session_with_oauth_state(pending.id, db)[1] is None

    def test_an_expired_session_is_not_found(self, db):
        expired = make_session(db, make_user(db), expires_at=datetime.now(UTC) - timedelta(minutes=1))

        assert sessions_service.get_session_with_oauth_state(expired.id, db) is None


class TestListing:
    def test_a_page_holds_the_exchanged_sessions_newest_first_with_the_total(self, db):
        user = make_user(db)
        now = datetime.now(UTC)
        oldest = make_session(db, user, created_at=now - timedelta(hours=3))
        newest = make_session(db, user, created_at=now - timedelta(hours=1))
        middle = make_session(db, user, created_at=now - timedelta(hours=2))
        make_session(db, user, exchanged=False)
        make_session(db, make_user(db))

        page = sessions_service.list_user_sessions(
            user.id, core_pagination.PageParams(page_number=1, num_records=2), db
        )
        second = sessions_service.list_user_sessions(
            user.id, core_pagination.PageParams(page_number=2, num_records=2), db
        )

        assert [item.id for item in page.items] == [newest.id, middle.id]
        assert [item.id for item in second.items] == [oldest.id]
        assert page.total == second.total == 3

    def test_only_the_callers_own_session_is_marked_current(self, db):
        user = make_user(db)
        own, other = make_session(db, user), make_session(db, user)

        page = sessions_service.list_user_sessions(
            user.id, core_pagination.PageParams(page_number=1, num_records=10), db, own.id
        )

        assert {item.id: item.is_current for item in page.items} == {own.id: True, other.id: False}

    def test_the_demo_environment_lists_none(self, db, monkeypatch):
        user = make_user(db)
        make_session(db, user)
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        page = sessions_service.list_user_sessions(
            user.id, core_pagination.PageParams(page_number=1, num_records=10), db
        )

        assert (page.items, page.total) == ([], 0)


class TestDeleteOne:
    def test_an_administrators_delete_ends_the_session_cleans_its_records_audits_and_announces(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        state_id = _state(db, "state-1")
        session = make_session(db, user, oauth_state_id=state_id)
        rotated_refresh_tokens_integration.store_rotated_token(
            "old-token",
            session.token_family_id,
            0,
            db,
            ip_address="127.0.0.1",
            user_agent="agent",
            refresh_token_exp=datetime.now(UTC) + timedelta(days=1),
            replacement_refresh_token="new",
            replacement_refresh_token_exp=datetime.now(UTC) + timedelta(days=1),
        )

        sessions_service.delete_session(session.id, user.id, _STEP_UP, _accepting, db)

        assert session.id not in _session_ids(db)
        assert state_id not in _state_ids(db)
        assert rotated_refresh_tokens_integration.check_token_reuse(
            "old-token", db, ip_address="127.0.0.1", user_agent="agent"
        ) == (False, False)
        (row,) = _audit(db, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_type, row.target_id, row.target_owner_id) == ("session", str(session.id), str(user.id))
        assert row.details == {"sessions_revoked": 1}
        assert [e.payload for e in events] == [
            {"user_id": str(user.id), "session_id": str(session.id), "except_session_id": None}
        ]

    def test_a_refused_step_up_deletes_nothing(self, db):
        user = make_user(db)
        session = make_session(db, user)

        with pytest.raises(core_exceptions.StepUpFailedError):
            sessions_service.delete_session(session.id, user.id, _STEP_UP, _refusing, db)

        assert session.id in _session_ids(db)
        assert _audit(db, sessions_audit_actions.SESSION_REVOKE) == []

    def test_another_users_session_is_not_found_and_not_audited(self, db):
        owner, other = make_user(db), make_user(db)
        session = make_session(db, owner)

        with pytest.raises(core_exceptions.NotFoundError):
            sessions_service.delete_session(session.id, other.id, _STEP_UP, _accepting, db)

        assert session.id in _session_ids(db)
        assert _audit(db, sessions_audit_actions.SESSION_REVOKE) == []

    def test_the_staged_delete_used_by_logout_adds_no_audit_row_and_announces(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        session = make_session(db, user)

        sessions_service.stage_delete_session(session.id, user.id, db)
        db.commit()

        assert session.id not in _session_ids(db)
        assert _audit(db, sessions_audit_actions.SESSION_REVOKE) == []
        assert len(events) == 1

    def test_deleting_a_session_that_may_be_gone_reports_whether_it_was_there(self, db):
        user = make_user(db)
        session = make_session(db, user)

        assert sessions_service.stage_delete_session_if_present(session.id, user.id, db) is True
        assert sessions_service.stage_delete_session_if_present(session.id, user.id, db) is False


class TestDeleteAllOfAUser:
    def test_an_administrators_revoke_ends_every_session_bumps_the_generation_audits_the_count_and_announces(
        self, db, published
    ):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        sessions = [make_session(db, user) for _ in range(3)]
        other = make_session(db, make_user(db))
        before = security_generation_integration.current_generation(user.id, db)

        deleted = sessions_service.delete_sessions_by_user_and_commit(user.id, _STEP_UP, _accepting, db)

        assert deleted == 3
        assert _session_ids(db) == {other.id}
        assert security_generation_integration.current_generation(user.id, db) == before + 1
        (row,) = _audit(db, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_type, row.target_id, row.details) == ("user", str(user.id), {"sessions_revoked": 3})
        assert [e.payload["user_id"] for e in events] == [str(user.id)]
        assert events[0].payload["session_id"] is None
        assert all(s.id not in _session_ids(db) for s in sessions)

    def test_revoking_when_none_are_open_still_bumps_the_generation_and_audits_nothing(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        before = security_generation_integration.current_generation(user.id, db)

        assert sessions_service.delete_sessions_by_user_and_commit(user.id, _STEP_UP, _accepting, db) == 0

        assert security_generation_integration.current_generation(user.id, db) == before + 1
        assert _audit(db, sessions_audit_actions.SESSION_REVOKE) == []
        assert events == []

    def test_keeping_one_session_does_not_bump_the_generation_and_names_the_kept_session(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        kept, gone = make_session(db, user), make_session(db, user)
        before = security_generation_integration.current_generation(user.id, db)

        deleted = sessions_service.delete_sessions_by_user_and_commit(
            user.id, _STEP_UP, _accepting, db, exclude_session_id=kept.id
        )

        assert deleted == 1
        assert _session_ids(db) == {kept.id}
        assert security_generation_integration.current_generation(user.id, db) == before
        assert [e.payload["except_session_id"] for e in events] == [str(kept.id)]
        assert gone.id not in _session_ids(db)

    def test_a_refused_step_up_deletes_nothing_and_does_not_bump(self, db):
        user = make_user(db)
        session = make_session(db, user)
        before = security_generation_integration.current_generation(user.id, db)

        with pytest.raises(core_exceptions.StepUpFailedError):
            sessions_service.delete_sessions_by_user_and_commit(user.id, _STEP_UP, _refusing, db)

        assert session.id in _session_ids(db)
        assert security_generation_integration.current_generation(user.id, db) == before

    def test_the_oauth_states_of_the_deleted_sessions_go_and_the_kept_ones_stay(self, db):
        user, other = make_user(db), make_user(db)
        kept = make_session(db, user, exchanged=False, oauth_state_id=_state(db, "st-kept"))
        make_session(db, user, exchanged=False, oauth_state_id=_state(db, "st-gone"))
        make_session(db, other, exchanged=False, oauth_state_id=_state(db, "st-other"))

        sessions_service.delete_sessions_by_user(user.id, db, kept.id)
        db.commit()

        assert _state_ids(db) == {"st-kept", "st-other"}

    def test_a_staged_delete_of_nothing_announces_nothing(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)

        assert sessions_service.delete_sessions_by_user(make_user(db).id, db) == 0

        assert events == []


class TestFamilyInvalidation:
    def test_it_ends_the_family_sessions_and_their_rotated_tokens_and_announces_each(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        session = make_session(db, user)
        kept = make_session(db, user)
        rotated_refresh_tokens_integration.store_rotated_token(
            "old-token",
            session.token_family_id,
            0,
            db,
            ip_address="127.0.0.1",
            user_agent="agent",
            refresh_token_exp=datetime.now(UTC) + timedelta(days=1),
            replacement_refresh_token="new",
            replacement_refresh_token_exp=datetime.now(UTC) + timedelta(days=1),
        )

        deleted = sessions_service.invalidate_token_family(session.token_family_id, db)
        db.commit()

        assert deleted == 1
        assert _session_ids(db) == {kept.id}
        assert rotated_refresh_tokens_integration.check_token_reuse(
            "old-token", db, ip_address="127.0.0.1", user_agent="agent"
        ) == (False, False)
        assert [e.payload["session_id"] for e in events] == [str(session.id)]

    def test_the_log_names_a_fingerprint_not_the_family_id(self, db, caplog):
        session = make_session(db, make_user(db))

        with caplog.at_level("WARNING"):
            sessions_service.invalidate_token_family(session.token_family_id, db)

        assert str(session.token_family_id) not in caplog.text


class TestDeviceSessions:
    def test_the_sessions_of_a_device_end_with_their_records_and_only_that_users(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user, other = make_user(db), make_user(db)
        first = make_session(db, user, device_hash="a" * 64, oauth_state_id=_state(db, "st-1"))
        second = make_session(db, user, device_hash="a" * 64)
        elsewhere = make_session(db, user, device_hash="b" * 64)
        theirs = make_session(db, other, device_hash="a" * 64)

        deleted = sessions_service.delete_sessions_by_device(user.id, "a" * 64, db)
        db.commit()

        assert deleted == 2
        assert _session_ids(db) == {elsewhere.id, theirs.id}
        assert "st-1" not in _state_ids(db)
        assert {e.payload["session_id"] for e in events} == {str(first.id), str(second.id)}

    def test_a_session_is_tied_to_the_device_it_signed_in_from(self, db):
        session = make_session(db, make_user(db))

        sessions_service.set_session_device_hash(session.id, "c" * 64, db)

        assert sessions_crud.get_session_by_id(session.id, db).device_hash == "c" * 64


class TestPurge:
    def test_the_expired_purge_ends_expired_sessions_in_batches_and_announces_each(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        user = make_user(db)
        now = datetime.now(UTC)
        live = make_session(db, user)
        count = core_database.PURGE_BATCH_SIZE + 1
        template = {c.name: getattr(live, c.name, None) for c in sessions_models.UsersSessions.__table__.columns}
        rows = []
        for _ in range(count):
            expired_id = uuid.uuid4()
            rows.append(
                template
                | {
                    "id": expired_id,
                    "token_family_id": expired_id,
                    "refresh_token": expired_id.hex,
                    "expires_at": now - timedelta(minutes=1),
                }
            )
        db.execute(sa.insert(sessions_models.UsersSessions), rows)

        total = sessions_service.delete_expired_sessions(db)

        assert total == count
        assert _session_ids(db) == {live.id}
        assert len(events) == count

    def test_the_idle_purge_ends_sessions_idle_longer_than_the_timeout_and_announces_them(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        edit_server_settings(
            db, session_idle_timeout_enabled=True, session_idle_timeout_hours=1, access_token_expire_minutes=15
        )
        user = make_user(db)
        idle = make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(hours=2))
        active = make_session(db, user)

        assert sessions_service.delete_idle_sessions(db) == 1

        assert _session_ids(db) == {active.id}
        assert [e.payload["session_id"] for e in events] == [str(idle.id)]

    def test_without_an_idle_timeout_nothing_ends(self, db, published):
        events = published(sessions_events.SESSIONS_REVOKED)
        edit_server_settings(db, session_idle_timeout_enabled=False)
        make_session(db, make_user(db), last_activity_at=datetime.now(UTC) - timedelta(days=100))

        assert sessions_service.delete_idle_sessions(db) == 0

        assert len(_session_ids(db)) == 1
        assert events == []
