"""The OAuth state of a login, link or step-up on the real database: its secrets, its claim and its purge."""

from datetime import UTC, datetime

import sqlalchemy as sa

import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.oauth_state.scheduled_jobs as oauth_state_jobs
import modules.auth.oauth_state.service as oauth_state_service
from tests._factories.users import make_user

LOGIN = oauth_state_constants.OAuthStatePurpose.LOGIN
LINK = oauth_state_constants.OAuthStatePurpose.LINK
NONCE = "n" * 43
VERIFIER = "v" * 64


def _create(db, state_id="s" * 43, **kwargs):
    kwargs.setdefault("purpose", LOGIN)
    return oauth_state_integration.create_oauth_state(state_id, NONCE, "web", None, db, **kwargs)


def _expire(db, state_id, *, minutes=1):
    db.execute(
        sa.update(oauth_state_models.OAuthState)
        .where(oauth_state_models.OAuthState.id == state_id)
        .values(expires_at=sa.text(f"now() - interval '{minutes} minute'"))
    )
    db.flush()


def _count(db) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(oauth_state_models.OAuthState))


class TestSecrets:
    def test_the_nonce_and_the_provider_verifier_are_stored_encrypted_and_read_back_in_plain_text(self, db):
        created = _create(db, idp_code_verifier=VERIFIER)

        stored = db.execute(
            sa.select(oauth_state_models.OAuthState.nonce, oauth_state_models.OAuthState.idp_code_verifier)
        ).one()
        assert stored.nonce != NONCE and NONCE not in stored.nonce
        assert stored.idp_code_verifier != VERIFIER and VERIFIER not in stored.idp_code_verifier
        assert (created.nonce, created.idp_code_verifier) == (NONCE, VERIFIER)
        for read in (
            oauth_state_integration.get_oauth_state_by_id_and_not_used,
            oauth_state_integration.get_oauth_state_by_id_not_expired,
        ):
            state = read("s" * 43, db)
            assert (state.nonce, state.idp_code_verifier) == (NONCE, VERIFIER)

    def test_a_state_without_a_provider_verifier_stores_none(self, db):
        _create(db)

        assert oauth_state_integration.get_oauth_state_by_id_not_expired("s" * 43, db).idp_code_verifier is None


class TestCreating:
    def test_a_link_state_keeps_who_started_it_and_the_digest_of_its_browser_binding(self, db):
        user = make_user(db)

        created = _create(db, user_id=user.id, browser_binding_hash="d" * 64, purpose=LINK)

        read = oauth_state_crud.get_oauth_state_by_id_and_not_used("s" * 43, db)
        assert (created.user_id, created.purpose) == (user.id, LINK)
        assert (read.browser_binding_hash, read.user_id) == ("d" * 64, user.id)

    def test_a_state_expires_after_its_fixed_lifetime(self, db):
        created = _create(db)

        remaining = (created.expires_at - created.created_at).total_seconds()

        assert abs(remaining - oauth_state_constants.STATE_TTL_SECONDS) < 5

    def test_a_state_created_with_a_generation_keeps_it_and_one_made_without_is_stamped_later(self, db):
        stamped_at_creation = _create(db, "a" * 43, security_generation=0)
        later = _create(db, "b" * 43)

        assert stamped_at_creation.security_generation == 0
        assert later.security_generation is None
        assert oauth_state_integration.stamp_security_generation("b" * 43, 5, db) is True
        assert oauth_state_crud.get_oauth_state_by_id_and_not_used("b" * 43, db).security_generation == 5
        assert oauth_state_integration.stamp_security_generation("x" * 43, 5, db) is False

    def test_the_state_id_and_nonce_are_distinct_random_values(self):
        first = oauth_state_integration.create_state_id_and_nonce()
        second = oauth_state_integration.create_state_id_and_nonce()

        assert len(first[0]) >= 32 and len(first[1]) >= 32
        assert first[0] != first[1]
        assert first != second


class TestReadingAndClaiming:
    def test_an_unused_state_is_read_until_it_is_claimed_and_the_claim_is_one_shot(self, db):
        _create(db)

        assert oauth_state_integration.get_oauth_state_by_id_and_not_used("s" * 43, db) is not None
        assert oauth_state_integration.mark_oauth_state_used("s" * 43, db) is True
        assert oauth_state_integration.mark_oauth_state_used("s" * 43, db) is False
        assert oauth_state_integration.get_oauth_state_by_id_and_not_used("s" * 43, db) is None
        assert oauth_state_integration.get_oauth_state_by_id_not_expired("s" * 43, db) is not None

    def test_an_expired_state_is_neither_read_nor_claimed(self, db):
        _create(db)
        _expire(db, "s" * 43)

        assert oauth_state_integration.get_oauth_state_by_id_and_not_used("s" * 43, db) is None
        assert oauth_state_integration.get_oauth_state_by_id_not_expired("s" * 43, db) is None
        assert oauth_state_integration.mark_oauth_state_used("s" * 43, db) is False

    def test_an_unknown_state_is_none_and_cannot_be_claimed(self, db):
        assert oauth_state_integration.get_oauth_state_by_id_and_not_used("nope", db) is None
        assert oauth_state_integration.mark_oauth_state_used("nope", db) is False


class TestDeleting:
    def test_states_are_deleted_one_by_one_or_by_list(self, db):
        for state_id in ("a", "b", "c"):
            _create(db, state_id * 43)

        assert oauth_state_integration.delete_oauth_state("a" * 43, db) == 1
        assert oauth_state_integration.delete_oauth_state("a" * 43, db) == 0
        assert oauth_state_integration.delete_oauth_states(["b" * 43, "c" * 43, "d" * 43], db) == 2
        assert _count(db) == 0

    def test_the_purge_removes_only_expired_states_in_bounded_batches(self, db):
        for n in range(5):
            _create(db, f"{n}" * 43)
            if n < 3:
                _expire(db, f"{n}" * 43)

        assert oauth_state_crud.delete_expired_oauth_states(datetime.now(UTC), 2, db) == 2
        assert oauth_state_service.delete_expired_oauth_states(db) == 1
        assert _count(db) == 2

    def test_the_scheduled_purge_runs_every_five_minutes_and_clears_what_expired(self, committed_sessions):
        with committed_sessions() as db:
            _create(db, "e" * 43)
            _create(db, "f" * 43)
            _expire(db, "e" * 43)
            db.commit()

        oauth_state_jobs.delete_expired_oauth_states_from_db()

        with committed_sessions() as db:
            assert [state_id for (state_id,) in db.execute(sa.select(oauth_state_models.OAuthState.id))] == ["f" * 43]
        assert oauth_state_jobs.recurring_jobs()[0].minutes == 5
