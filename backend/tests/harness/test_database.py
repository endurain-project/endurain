"""The test database harness isolates tests, runs on the application's own engine and schema, and fails loudly."""

import uuid

import jasil.audit as jasil_audit
import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog
from sqlalchemy.exc import IntegrityError, OperationalError, SAWarning

import core.database as core_database
import modules.server_settings.audit_actions as server_settings_audit_actions
import modules.server_settings.models as server_settings_models
import modules.users.users.models as users_models
from tests._helpers import database as test_database


def _user(user_id: uuid.UUID | None = None) -> users_models.Users:
    user_id = user_id or uuid.uuid4()
    return users_models.Users(
        id=user_id,
        name="Harness User",
        username=f"harness{user_id.hex}",
        email=f"harness{user_id.hex}@example.com",
        preferred_language="en",
        access_type="regular",
    )


class TestWorkerDatabase:
    def test_the_application_engine_works_in_this_processs_own_database(self, db):
        assert db.execute(sa.text("SELECT current_database()")).scalar_one() == test_database.worker_database()

    def test_the_schema_is_the_migrated_one_with_the_rows_the_migrations_seed(self, db):
        assert db.execute(sa.text("SELECT count(*) FROM alembic_version")).scalar_one() == 1
        assert db.get(server_settings_models.ServerSettings, 1) is not None

    def test_a_database_whose_name_does_not_say_test_is_refused(self, monkeypatch):
        monkeypatch.setenv(test_database.TEST_DATABASE_URL_ENV, "postgresql+psycopg://endurain:x@localhost/endurain")

        with pytest.raises(RuntimeError, match="disposable"):
            test_database.maintenance_url()


class TestRolledBackSession:
    def test_what_a_test_commits_is_gone_for_the_next_one(self, _worker_database):
        user = _user()

        with test_database.rolled_back_session(core_database.engine, core_database.SessionLocal) as first:
            first.add(user)
            first.commit()
            assert first.get(users_models.Users, user.id) is not None

        with test_database.rolled_back_session(core_database.engine, core_database.SessionLocal) as second:
            assert second.get(users_models.Users, user.id) is None

    def test_the_session_factory_is_bound_back_to_the_engine_afterwards(self, _worker_database):
        with test_database.rolled_back_session(core_database.engine, core_database.SessionLocal):
            pass

        assert core_database.SessionLocal.kw["bind"] is core_database.engine
        assert "join_transaction_mode" not in core_database.SessionLocal.kw

    def test_a_session_the_code_opens_itself_sees_the_rows_the_test_wrote(self, db):
        user = _user()
        db.add(user)
        db.flush()

        with core_database.SessionLocal() as code:
            assert code.get(users_models.Users, user.id) is not None

    def test_a_commit_in_the_code_under_test_stays_invisible_to_other_connections(self, db):
        user_id = uuid.uuid4()
        with core_database.SessionLocal() as code:
            code.add(_user(user_id))
            code.commit()

        with core_database.engine.connect() as other:
            assert (
                other.execute(sa.select(users_models.Users.id).where(users_models.Users.id == user_id)).first() is None
            )
        assert db.get(users_models.Users, user_id) is not None

    def test_a_failed_statement_in_the_code_leaves_the_tests_session_usable(self, db):
        user = _user()
        db.add(user)
        db.flush()

        with core_database.SessionLocal() as code:
            code.add(_user(user.id))
            with pytest.raises(IntegrityError):
                code.flush()
            code.rollback()

        assert db.get(users_models.Users, user.id) is not None

    def test_sessions_that_end_out_of_order_fail_instead_of_passing(self, db):
        first = core_database.SessionLocal()
        second = core_database.SessionLocal()
        first.add(_user())
        first.flush()
        second.add(_user())
        second.flush()
        with pytest.warns(SAWarning, match="deassociated"):
            first.commit()

        with pytest.raises(OperationalError, match="savepoint"):
            second.commit()
        first.close()
        second.close()

    def test_a_rollback_also_discards_what_a_detached_write_committed_meanwhile(self, db):
        """Why refusals and failure paths are tested with ``committed_sessions``: production keeps this row."""
        with core_database.SessionLocal() as request_session:
            request_session.execute(sa.text("SELECT 1"))
            jasil_audit.record_detached(
                server_settings_audit_actions.SETTINGS_UPDATE,
                outcome=jasil_audit.Outcome.FAILURE,
                details=server_settings_audit_actions.SettingsChangeDetails(changed_fields=["units"]),
            )
            request_session.rollback()

        assert db.scalar(sa.select(sa.func.count()).select_from(AuditLog)) == 0


class TestCommittedSessions:
    def test_a_detached_write_survives_the_rollback_of_the_request_around_it(self, committed_sessions):
        with committed_sessions() as request_session:
            request_session.execute(sa.text("SELECT 1"))
            jasil_audit.record_detached(
                server_settings_audit_actions.SETTINGS_UPDATE,
                outcome=jasil_audit.Outcome.FAILURE,
                details=server_settings_audit_actions.SettingsChangeDetails(changed_fields=["units"]),
            )
            request_session.rollback()

        with committed_sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(AuditLog)) == 1

    def test_a_session_does_not_see_what_another_has_not_committed(self, committed_sessions):
        user = _user()
        with committed_sessions() as writer, committed_sessions() as reader:
            writer.add(user)
            writer.flush()

            assert reader.get(users_models.Users, user.id) is None
            writer.commit()
            assert reader.get(users_models.Users, user.id) is not None

    def test_a_reset_returns_the_database_to_the_template(self, committed_sessions):
        user_id = uuid.uuid4()
        with committed_sessions() as session:
            session.add(_user(user_id))
            session.commit()

        test_database.reset_worker_database(core_database.engine)

        with committed_sessions() as session:
            assert session.get(users_models.Users, user_id) is None
            assert session.get(server_settings_models.ServerSettings, 1) is not None


class TestProductionBehaviour:
    def test_a_test_on_the_real_database_writes_audit_rows_in_its_transaction(self, db):
        details = server_settings_audit_actions.SettingsChangeDetails(changed_fields=["units"])
        jasil_audit.stage(db, server_settings_audit_actions.SETTINGS_UPDATE, details=details)
        db.flush()

        stored = db.scalars(
            sa.select(AuditLog).where(AuditLog.action_id == server_settings_audit_actions.SETTINGS_UPDATE.id)
        )

        assert [row.details for row in stored] == [{"changed_fields": ["units"]}]

    def test_an_audit_row_rolls_back_with_its_transaction(self, db):
        with core_database.SessionLocal() as code:
            details = server_settings_audit_actions.SettingsChangeDetails(changed_fields=["units"])
            jasil_audit.stage(code, server_settings_audit_actions.SETTINGS_UPDATE, details=details)
            code.flush()
            code.rollback()

        assert db.scalar(sa.select(sa.func.count()).select_from(AuditLog)) == 0
