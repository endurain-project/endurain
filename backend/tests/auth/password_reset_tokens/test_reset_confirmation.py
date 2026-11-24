"""Confirming a reset: what a refusal leaves alone, what a reset secures, and the expired-token purge."""

from datetime import UTC, datetime, timedelta

import jasil.events as platform_events
import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.config as core_config
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.credentials.models as credentials_models
import modules.auth.identity_provider_links.models as identity_links_models
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.password_reset_tokens.audit_actions as reset_audit_actions
import modules.auth.password_reset_tokens.crud as reset_crud
import modules.auth.password_reset_tokens.events as reset_events
import modules.auth.password_reset_tokens.integration_service as reset_integration
import modules.auth.password_reset_tokens.models as reset_models
import modules.auth.password_reset_tokens.scheduled_jobs as reset_scheduled_jobs
import modules.auth.password_reset_tokens.service as reset_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.users.users.models as users_models
from tests._factories.api_keys import make_api_key
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.mail import events
from tests._factories.tokens import audit_rows, make_mfa, make_reset_token
from tests._factories.users import PASSWORD, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public/password-reset"
_NEW_PASSWORD = "Another-Password-5678!"
_UNUSABLE = "urn:endurain:error:invalid-input"


def _confirm(client, token: str, password: str = _NEW_PASSWORD):
    return client.post(f"{_PUBLIC}/confirm", json={"token": token, "password": password})


def _validate(client, token: str):
    return client.post(f"{_PUBLIC}/validate", json={"token": token})


def _with_token(committed_sessions, *, token_options=None, **account):
    with committed_sessions() as db:
        user = make_user(db, **account)
        token = make_reset_token(db, user, **(token_options or {}))
        db.commit()
    return user, token


def _hash(committed_sessions, user_id) -> str | None:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(credentials_models.LocalCredential.password_hash).where(
                credentials_models.LocalCredential.user_id == user_id
            )
        )


def _generation(committed_sessions, user_id) -> int:
    with committed_sessions() as db:
        return security_generation_integration.current_generation(user_id, db)


def _audited(committed_sessions):
    return audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET)


class TestARefusedConfirmation:
    def test_an_inactive_account_is_refused_as_unusable_and_audited_as_denied(self, client, committed_sessions):
        user, token = _with_token(committed_sessions, active=False)
        before = _hash(committed_sessions, user.id)

        response = _confirm(client, token)

        assert response.status_code == 400
        assert response.json()["type"] == _UNUSABLE
        assert _hash(committed_sessions, user.id) == before
        (row,) = _audited(committed_sessions)
        assert (row.outcome, row.target_id) == ("denied", str(user.id))

    def test_an_account_that_lost_its_local_password_is_refused_the_same_way(self, client, committed_sessions):
        user, token = _with_token(committed_sessions, with_password=False)

        response = _confirm(client, token)

        assert (response.status_code, response.json()["type"]) == (400, _UNUSABLE)
        assert _hash(committed_sessions, user.id) is None
        assert [row.outcome for row in _audited(committed_sessions)] == ["denied"]

    def test_the_current_password_is_refused_and_the_token_and_generation_are_untouched(
        self, client, committed_sessions
    ):
        user, token = _with_token(committed_sessions)
        before = _generation(committed_sessions, user.id)

        refused = _confirm(client, token, PASSWORD)

        assert refused.status_code == 422
        assert refused.json()["type"] == "urn:endurain:error:password-unchanged"
        assert _generation(committed_sessions, user.id) == before
        assert _validate(client, token).status_code == 204
        assert _confirm(client, token).status_code == 204

    @pytest.mark.parametrize(("password", "problem"), [("short", "password-too-short"), ("   " * 8, "password-blank")])
    def test_a_password_the_policy_refuses_leaves_the_token_usable(self, client, committed_sessions, password, problem):
        user, token = _with_token(committed_sessions)
        before = _hash(committed_sessions, user.id)

        refused = _confirm(client, token, password)

        assert refused.status_code == 422
        assert refused.json()["type"] == f"urn:endurain:error:{problem}"
        assert _hash(committed_sessions, user.id) == before
        assert _confirm(client, token).status_code == 204

    @pytest.mark.parametrize(
        "body",
        [{"password": _NEW_PASSWORD}, {"token": "t" * 43}, {"token": "t" * 43, "new_password": _NEW_PASSWORD}],
        ids=["no-token", "no-password", "old-field-name"],
    )
    def test_a_malformed_request_is_422(self, client, body):
        assert client.post(f"{_PUBLIC}/confirm", json=body).status_code == 422


class TestValidation:
    def test_every_unusable_token_gets_the_same_answer_and_no_audit_row(self, client, committed_sessions):
        _, used = _with_token(committed_sessions)
        assert _confirm(client, used).status_code == 204
        _, expired = _with_token(
            committed_sessions, token_options={"expires_at": datetime.now(UTC) - timedelta(seconds=5)}
        )
        _, inactive = _with_token(committed_sessions, active=False)
        _, no_password = _with_token(committed_sessions, with_password=False)
        before = len(_audited(committed_sessions))

        answers = [_validate(client, token) for token in (used, expired, inactive, no_password, "unknown")]

        assert {(answer.status_code, answer.json()["type"], answer.json()["detail"]) for answer in answers} == {
            (400, _UNUSABLE, answers[0].json()["detail"])
        }
        assert len(_audited(committed_sessions)) == before

    def test_a_token_confirm_would_refuse_stays_unconsumed_by_validation(self, client, committed_sessions):
        _, token = _with_token(committed_sessions, active=False)

        assert _validate(client, token).status_code == 400

        with committed_sessions() as db:
            used = db.scalars(sa.select(reset_models.PasswordResetToken.used)).all()
        assert used == [False]

    def test_a_missing_or_extra_field_is_422(self, client):
        assert client.post(f"{_PUBLIC}/validate", json={}).status_code == 422
        assert client.post(f"{_PUBLIC}/validate", json={"token": "t" * 43, "extra": 1}).status_code == 422


class TestWhatAResetSecures:
    def test_it_advances_the_security_generation_and_publishes_the_completion(self, client, committed_sessions):
        seen: list[platform_events.Event] = []
        events().subscribe(reset_events.PASSWORD_RESET_COMPLETED, seen.append)
        user, token = _with_token(committed_sessions)
        before = _generation(committed_sessions, user.id)

        assert _confirm(client, token).status_code == 204

        assert _generation(committed_sessions, user.id) == before + 1
        assert [event.payload for event in seen] == [{"user_id": str(user.id)}]

    def test_it_revokes_the_users_api_keys_and_no_one_elses(self, client, committed_sessions):
        with committed_sessions() as db:
            user, bystander = make_user(db), make_user(db)
            mine, _ = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACCOUNT])
            theirs, _ = make_api_key(db, bystander, scopes=[api_keys_constants.ApiKeyScope.ACCOUNT])
            token = make_reset_token(db, user)
            db.commit()

        assert _confirm(client, token).status_code == 204

        with committed_sessions() as db:
            revoked = dict(
                db.execute(sa.select(api_keys_models.UsersApiKeys.id, api_keys_models.UsersApiKeys.revoked_at)).all()
            )
        assert revoked[mine.id] is not None
        assert revoked[theirs.id] is None

    def test_an_unverified_account_loses_links_and_factors_and_is_verified(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, email_verified=False)
            idp = make_identity_provider(db, "squatter")
            make_identity_link(db, user.id, idp, "subject-1")
            make_mfa(db, user)
            token = make_reset_token(db, user)
            db.commit()

        assert _confirm(client, token).status_code == 204

        with committed_sessions() as db:
            assert db.scalars(sa.select(identity_links_models.IdentityLink)).all() == []
            assert db.scalar(sa.select(users_models.Users.email_verified).where(users_models.Users.id == user.id))
        from modules.auth.mfa.integration_service import is_mfa_enabled_for_user

        with committed_sessions() as db:
            assert is_mfa_enabled_for_user(user.id, db) is False
        (row,) = _audited(committed_sessions)
        assert row.details == {"unverified_account_cleaned": True}

    def test_an_unverified_account_without_a_second_factor_is_still_verified(self, client, committed_sessions):
        user, token = _with_token(committed_sessions, email_verified=False)

        assert _confirm(client, token).status_code == 204

        with committed_sessions() as db:
            assert db.scalar(sa.select(users_models.Users.email_verified).where(users_models.Users.id == user.id))

    def test_a_verified_account_keeps_its_links_and_factors(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, email_verified=True)
            idp = make_identity_provider(db, "trusted")
            make_identity_link(db, user.id, idp, "subject-2")
            make_mfa(db, user)
            token = make_reset_token(db, user)
            db.commit()

        assert _confirm(client, token).status_code == 204

        from modules.auth.mfa.integration_service import is_mfa_enabled_for_user

        with committed_sessions() as db:
            assert len(db.scalars(sa.select(identity_links_models.IdentityLink)).all()) == 1
            assert is_mfa_enabled_for_user(user.id, db) is True
        (row,) = _audited(committed_sessions)
        assert row.details == {"unverified_account_cleaned": False}

    def test_the_new_password_clears_the_change_required_flag(self, client, committed_sessions):
        user, token = _with_token(committed_sessions)
        with committed_sessions() as db:
            credentials_integration.require_password_change(user.id, db)
            db.commit()

        assert _confirm(client, token).status_code == 204

        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(user.id, db) is False


class TestTokenStorage:
    def test_a_token_hash_is_unique(self, db):
        user = make_user(db)
        make_reset_token(db, user)
        stored = db.scalars(sa.select(reset_models.PasswordResetToken)).one()

        with pytest.raises(IntegrityError):
            db.add(
                reset_models.PasswordResetToken(
                    user_id=user.id,
                    token_hash=stored.token_hash,
                    expires_at=stored.expires_at,
                    used=False,
                )
            )
            db.flush()

    def test_revoking_a_users_unused_tokens_voids_only_theirs(self, db):
        mine, other = make_user(db), make_user(db)
        make_reset_token(db, mine)
        make_reset_token(db, other)

        reset_integration.revoke_unused_tokens(mine.id, db)

        used = dict(
            db.execute(sa.select(reset_models.PasswordResetToken.user_id, reset_models.PasswordResetToken.used)).all()
        )
        assert used == {mine.id: True, other.id: False}

    def test_the_tokens_go_with_their_user(self, committed_sessions):
        user, _ = _with_token(committed_sessions)
        with committed_sessions() as db:
            db.execute(sa.delete(users_models.Users).where(users_models.Users.id == user.id))
            db.commit()
        with committed_sessions() as db:
            assert db.scalars(sa.select(reset_models.PasswordResetToken)).all() == []


class TestPurge:
    def _hashes(self, committed_sessions) -> set[bool]:
        with committed_sessions() as db:
            return {token.used for token in db.scalars(sa.select(reset_models.PasswordResetToken))}

    def test_the_job_deletes_expired_tokens_and_keeps_live_and_used_unexpired_ones(self, committed_sessions):
        _with_token(committed_sessions)
        _with_token(committed_sessions, token_options={"expires_at": datetime.now(UTC) - timedelta(minutes=1)})
        with committed_sessions() as db:
            db.execute(
                sa.update(reset_models.PasswordResetToken)
                .where(reset_models.PasswordResetToken.expires_at > datetime.now(UTC))
                .values(used=True)
            )
            db.commit()

        reset_scheduled_jobs.delete_expired_tokens_from_db()

        with committed_sessions() as db:
            remaining = db.scalars(sa.select(reset_models.PasswordResetToken)).all()
        assert len(remaining) == 1
        assert remaining[0].expires_at > datetime.now(UTC)

    def test_the_job_with_nothing_expired_deletes_nothing(self, committed_sessions):
        _with_token(committed_sessions)

        reset_scheduled_jobs.delete_expired_tokens_from_db()

        assert self._hashes(committed_sessions) == {False}

    def test_the_service_reports_how_many_it_deleted_in_batches(self, committed_sessions):
        with committed_sessions() as db:
            for _ in range(3):
                user = make_user(db)
                make_reset_token(db, user, expires_at=datetime.now(UTC) - timedelta(hours=1))
            db.commit()
        with committed_sessions() as db:
            assert reset_service.delete_expired_password_reset_tokens(db) == 3
            assert reset_crud.delete_expired_password_reset_tokens(datetime.now(UTC), 10, db) == 0

    def test_the_cleanup_runs_every_minute_under_its_own_lock(self):
        (job,) = reset_scheduled_jobs.recurring_jobs()

        assert job.func is reset_scheduled_jobs.delete_expired_tokens_from_db
        assert job.lock_name == reset_scheduled_jobs.PURGE_LOCK_NAME


class TestAResetLiftsTheAccountWideLocks:
    def test_an_account_locked_against_every_network_signs_in_again_after_a_reset(self, client, committed_sessions):
        """A reset proves the owner: the lock that held the account across every address must not outlive it."""
        user, token = _with_token(committed_sessions)
        store = failed_login_store.FailedLoginAttempts(platform_runtime.get_active_platform().state)
        record = None
        # One failure per network, so only the account-wide count reaches its cap.
        for network in range(lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0]):
            record = store.record_failed_attempt(
                user.username, f"198.51.{network // 250}.{network % 250}", user_id=user.id
            )
        assert record is not None and record.account_locked_now
        assert store.is_locked_out(user.username, "203.0.113.9", user_id=user.id)

        assert _confirm(client, token).status_code == 204

        assert not store.is_locked_out(user.username, "203.0.113.9", user_id=user.id)
        signed_in = client.post(
            f"{core_config.ROOT_PATH}/auth/login",
            data={"username": user.username, "password": _NEW_PASSWORD},
            headers={"X-Client-Type": "web"},
        )
        assert signed_in.status_code == 200, signed_in.text

    def test_an_account_locked_for_wrong_mfa_codes_on_every_network_is_released_by_a_reset(
        self, client, committed_sessions
    ):
        """Whoever sent the wrong codes held the old password, so the account-wide MFA lock ends with it."""
        user, token = _with_token(committed_sessions)
        store = pending_login_store.PendingMFALogin(platform_runtime.get_active_platform().state)
        record = None
        for network in range(lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS[0][0]):
            record = store.record_failed_attempt(
                user.username, f"198.51.{network // 250}.{network % 250}", user_id=user.id
            )
        assert record is not None and record.account_locked_now
        assert store.is_locked_out(user.username, "203.0.113.9", user_id=user.id)

        assert _confirm(client, token).status_code == 204

        assert not store.is_locked_out(user.username, "203.0.113.9", user_id=user.id)
