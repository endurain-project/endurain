"""An unverified self sign-up is removed once its link expired, expired tokens are deleted, and nothing else goes."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.database as core_database
import modules.auth.sign_up_tokens.audit_actions  # noqa: F401  (registers the module's actions with the catalog)
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_scheduled_jobs
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.tokens import audit_rows, make_email_change, make_sign_up_token
from tests._factories.users import make_sign_up, make_user

_OLD = datetime.now(UTC) - sign_up_service.SIGN_UP_TOKEN_TTL - timedelta(hours=1)
_RECENT = datetime.now(UTC) - sign_up_service.SIGN_UP_TOKEN_TTL + timedelta(hours=1)
_PAST = datetime.now(UTC) - timedelta(hours=1)


def _old_sign_up(db, **fields):
    return make_sign_up(db, with_password=False, created_at=_OLD, **fields)


def _remaining(committed_sessions) -> set:
    with committed_sessions() as db:
        return set(db.scalars(sa.select(users_models.Users.id)))


def _purge(committed_sessions) -> int:
    with committed_sessions() as db:
        return sign_up_service.purge_unverified_sign_ups(db)


class TestPurgingUnverifiedSignUps:
    def test_an_old_unverified_sign_up_without_a_password_or_a_provider_is_deleted_and_audited(
        self, committed_sessions
    ):
        with committed_sessions() as db:
            user = _old_sign_up(db)
            db.commit()

        assert _purge(committed_sessions) == 1

        assert _remaining(committed_sessions) == set()
        (row,) = audit_rows(committed_sessions, users_audit_actions.USER_PURGE)
        assert (row.outcome, row.target_id, row.target_owner_id) == ("success", str(user.id), str(user.id))

    def test_an_expired_or_used_token_does_not_keep_the_account(self, committed_sessions):
        with committed_sessions() as db:
            expired, used = _old_sign_up(db), _old_sign_up(db)
            make_sign_up_token(db, expired, expires_at=_PAST)
            make_sign_up_token(db, used)
            db.execute(
                sa.update(sign_up_models.SignUpToken)
                .where(sign_up_models.SignUpToken.user_id == used.id)
                .values(used=True)
            )
            db.commit()

        assert _purge(committed_sessions) == 2
        assert _remaining(committed_sessions) == set()

    @pytest.mark.parametrize(
        "keep",
        [
            pytest.param(lambda db: make_sign_up(db, with_password=False, created_at=_RECENT), id="younger-than-link"),
            pytest.param(lambda db: make_user(db, with_password=False, created_at=_OLD), id="active"),
            pytest.param(
                lambda db: make_sign_up(db, with_password=False, email_verified=True, created_at=_OLD), id="verified"
            ),
            pytest.param(
                lambda db: make_sign_up(db, pending_admin_approval=True, created_at=_OLD), id="approval-with-password"
            ),
            pytest.param(lambda db: make_sign_up(db, created_at=_OLD), id="inactive-with-password"),
            pytest.param(
                lambda db: make_user(db, active=False, with_password=False, email_verified=False, created_at=_OLD),
                id="deactivated",
            ),
            pytest.param(
                lambda db: make_sign_up(db, with_password=False, created_at=_OLD, deletion_requested_at=_OLD),
                id="deletion-requested",
            ),
        ],
    )
    def test_an_account_that_is_not_an_expired_unverified_sign_up_is_kept(self, committed_sessions, keep):
        with committed_sessions() as db:
            user = keep(db)
            db.commit()

        assert _purge(committed_sessions) == 0
        assert _remaining(committed_sessions) == {user.id}
        assert audit_rows(committed_sessions, users_audit_actions.USER_PURGE) == []

    def test_a_linked_identity_provider_or_a_live_token_keeps_the_account(self, committed_sessions):
        with committed_sessions() as db:
            linked, resent = _old_sign_up(db), _old_sign_up(db)
            make_identity_link(db, linked.id, make_identity_provider(db, "keeper"), "subject")
            make_sign_up_token(db, resent)
            db.commit()

        assert _purge(committed_sessions) == 0
        assert _remaining(committed_sessions) == {linked.id, resent.id}

    def test_only_the_purgeable_accounts_go_when_mixed_with_kept_ones(self, committed_sessions):
        with committed_sessions() as db:
            gone_a, gone_b = _old_sign_up(db), _old_sign_up(db)
            kept_password = make_sign_up(db, created_at=_OLD)
            kept_recent = make_sign_up(db, with_password=False, created_at=_RECENT)
            db.commit()

        assert _purge(committed_sessions) == 2

        assert _remaining(committed_sessions) == {kept_password.id, kept_recent.id}
        purged = audit_rows(committed_sessions, users_audit_actions.USER_PURGE)
        assert sorted(row.target_id for row in purged) == sorted([str(gone_a.id), str(gone_b.id)])

    def test_it_deletes_in_bounded_batches(self, committed_sessions, monkeypatch):
        with committed_sessions() as db:
            for _ in range(5):
                _old_sign_up(db)
            db.commit()
        monkeypatch.setattr(core_database, "PURGE_BATCH_SIZE", 2)

        assert _purge(committed_sessions) == 5
        assert _remaining(committed_sessions) == set()

    def test_a_verification_in_flight_holds_its_row_and_wins(self, committed_sessions):
        with committed_sessions() as db:
            user = _old_sign_up(db)
            db.commit()

        with committed_sessions() as verification:
            verification.execute(
                sa.select(users_models.Users.id).where(users_models.Users.id == user.id).with_for_update()
            )
            assert _purge(committed_sessions) == 0
            verification.rollback()

        assert _remaining(committed_sessions) == {user.id}
        assert _purge(committed_sessions) == 1

    def test_the_scheduled_job_purges_and_deletes_expired_tokens(self, committed_sessions):
        with committed_sessions() as db:
            _old_sign_up(db)
            owner = make_user(db)
            make_sign_up_token(db, owner, expires_at=_PAST)
            db.commit()

        sign_up_scheduled_jobs.delete_unverified_sign_ups_from_db()
        sign_up_scheduled_jobs.delete_expired_tokens_from_db()

        with committed_sessions() as db:
            assert db.scalars(sa.select(sign_up_models.SignUpToken)).all() == []
            assert db.scalars(sa.select(users_models.Users.id)).all() == [owner.id]

    def test_the_jobs_run_under_their_own_locks(self):
        jobs = sign_up_scheduled_jobs.recurring_jobs()

        assert {job.func for job in jobs} == {
            sign_up_scheduled_jobs.delete_expired_tokens_from_db,
            sign_up_scheduled_jobs.delete_unverified_sign_ups_from_db,
        }
        assert len({job.lock_name for job in jobs}) == 2


class TestExpiredTokens:
    def test_an_expired_sign_up_token_is_deleted_and_a_live_one_kept(self, committed_sessions):
        with committed_sessions() as db:
            expired_owner, live_owner = make_user(db), make_user(db)
            make_sign_up_token(db, expired_owner, expires_at=_PAST)
            make_sign_up_token(db, live_owner)
            db.commit()

        with committed_sessions() as db:
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 1

        with committed_sessions() as db:
            assert [t.user_id for t in db.scalars(sa.select(sign_up_models.SignUpToken))] == [live_owner.id]

    def test_an_email_change_row_is_kept_until_its_revert_window_ends(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            make_email_change(db, user, "new@example.com", expires_at=_PAST)
            db.commit()

        with committed_sessions() as db:
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 0
            db.execute(sa.update(sign_up_models.SignUpToken).values(revert_until=_PAST))
            db.commit()
        with committed_sessions() as db:
            assert sign_up_service.delete_expired_sign_up_tokens(db) == 1
