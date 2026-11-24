"""Unlinking and the sessions of a linked Garmin Connect account: stored token, refresh claim, rate limit."""

import uuid
from datetime import UTC, datetime, timedelta

import garminconnect
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.service as garmin_service
import modules.notifications.constants as notifications_constants
import modules.users.users_integrations.models as user_integrations_models
from tests._factories import garmin as garmin_factories
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user
from tests.garmin.conftest import UnavailableState, notifications_of, stored_access_token, stored_token

_STEP_UP = auth_schema.StepUpVerification(current_password="pw")


def _approve(_step_up, _action) -> None:
    """A step-up verifier that accepts."""


def _session(
    account: garmin_factories.GarminAccount, token: dict, access: str = "access-1"
) -> garmin_service.GarminSession:
    """Build a session as a restore builds it: a client holding the token's secrets, and the token it came from."""
    client = garmin_factories.FakeGarmin(account)
    client.client.di_token = access
    client.client.di_refresh_token = "refresh-1"
    return garmin_service.GarminSession(client, token)


class TestLinkedIntegrations:
    def test_a_user_without_integrations_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            garmin_service.get_linked_user_integrations(uuid.uuid4(), db)

    def test_an_unlinked_user_has_no_integrations_to_use(self, db):
        user = make_user(db)

        assert garmin_service.get_linked_user_integrations(user.id, db) is None

    def test_a_linked_user_is_returned_with_the_stored_token(self, db):
        user = make_user(db)
        token = garmin_factories.link_garmin(db, user.id)

        found = garmin_service.get_linked_user_integrations(user.id, db)

        assert found is not None and found.garminconnect_token == token


class TestRestoreSession:
    def test_a_linked_user_gets_a_client_holding_the_stored_secrets_and_the_token_it_came_from(
        self, account, linked, committed_sessions
    ):
        with committed_sessions() as db:
            session = garmin_service.get_user_garminconnect_session(linked.id, db)

        assert session is not None
        assert session.client.client.di_token == "access-1"
        assert session.client.client.di_refresh_token == "refresh-1"
        assert session.token == stored_token(committed_sessions, linked.id)

    def test_a_china_account_is_restored_for_its_region(self, account, make_linked, committed_sessions):
        user = make_linked(is_cn=True)

        with committed_sessions() as db:
            garmin_service.get_user_garminconnect_session(user.id, db)

        assert account.clients[0].is_cn is True

    def test_an_unlinked_user_has_no_session(self, account, unlinked, committed_sessions):
        with committed_sessions() as db:
            assert garmin_service.get_user_garminconnect_session(unlinked.id, db) is None

        assert account.clients == []

    def test_a_user_without_integrations_is_simply_not_linked(self, account, db, caplog):
        """The same "not linked" event Strava reports, at the same level."""
        with caplog.at_level("DEBUG", logger=garmin_service.logger.name):
            assert garmin_service.get_user_garminconnect_session(uuid.uuid4(), db) is None

        assert {record.levelname for record in caplog.records} == {"DEBUG"}

    def test_a_session_garmin_rejects_is_no_session_and_the_account_stays_linked(
        self, account, linked, committed_sessions
    ):
        account.restore_error = garminconnect.GarminConnectAuthenticationError("401")

        with committed_sessions() as db:
            assert garmin_service.get_user_garminconnect_session(linked.id, db) is None

        assert stored_token(committed_sessions, linked.id) is not None

    def test_a_token_the_key_cannot_read_fails_the_sync_and_the_account_stays_linked(
        self, account, linked, committed_sessions
    ):
        """A key that cannot read the stored token says nothing about the token: the account stays linked."""
        foreign = Fernet(Fernet.generate_key()).encrypt(b"secret").decode()
        with committed_sessions() as db:
            token = {**stored_token(committed_sessions, linked.id), "di_token": foreign}
            db.execute(
                update(user_integrations_models.UsersIntegrations)
                .where(user_integrations_models.UsersIntegrations.user_id == linked.id)
                .values(garminconnect_token=token)
            )
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.UndecryptableError):
            garmin_service.get_user_garminconnect_session(linked.id, db)

        assert stored_token(committed_sessions, linked.id) is not None
        assert notifications_of(committed_sessions, linked.id) == []


class TestUnlinkAccount:
    def test_unlinking_clears_the_token_and_gear_sync_and_is_audited(self, make_linked, committed_sessions):
        user = make_linked(sync_gear=True)

        with committed_sessions() as db:
            garmin_service.unlink_account(user.id, _STEP_UP, _approve, db)

        assert stored_token(committed_sessions, user.id) is None
        with committed_sessions() as db:
            assert garmin_service.get_linked_user_integrations(user.id, db) is None
            row = db.scalars(select(user_integrations_models.UsersIntegrations).filter_by(user_id=user.id)).one()
            assert row.garminconnect_sync_gear is False
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK)
        assert (row.target_type, row.target_id, row.target_owner_id, row.details) == (
            "user",
            str(user.id),
            str(user.id),
            None,
        )

    def test_the_step_up_is_verified_for_the_unlink_action_before_anything_changes(self, linked, committed_sessions):
        asked: list[tuple[object, object]] = []
        read_back: list[object] = []

        def verify(step_up, action):
            asked.append((step_up, action))
            read_back.append(stored_token(committed_sessions, linked.id))

        with committed_sessions() as db:
            garmin_service.unlink_account(linked.id, _STEP_UP, verify, db)

        assert asked == [(_STEP_UP, identity_providers_constants.StepUpAction.GARMIN_UNLINK)]
        assert read_back[0] is not None

    def test_a_refused_step_up_unlinks_and_audits_nothing(self, linked, committed_sessions):
        def refuse(_step_up, _action):
            raise core_exceptions.StepUpFailedError("no")

        with committed_sessions() as db, pytest.raises(core_exceptions.StepUpFailedError):
            garmin_service.unlink_account(linked.id, _STEP_UP, refuse, db)

        assert stored_token(committed_sessions, linked.id) is not None
        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK) == []

    def test_a_user_without_integrations_is_not_audited(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            garmin_service.unlink_account(uuid.uuid4(), _STEP_UP, _approve, db)

        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK) == []


class TestUnlinkExpiredAccount:
    def test_the_rejected_token_is_unlinked_and_the_user_told_and_audited_together(
        self, linked, committed_sessions, hints
    ):
        token = stored_token(committed_sessions, linked.id)

        with committed_sessions() as db:
            garmin_service.unlink_expired_account(linked.id, token, db)

        assert stored_token(committed_sessions, linked.id) is None
        [notification] = notifications_of(committed_sessions, linked.id)
        assert notification.type == notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED.stored
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_REVOKE)
        assert (row.target_type, row.target_id, row.target_owner_id, row.details) == (
            "user",
            str(linked.id),
            str(linked.id),
            None,
        )
        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK) == []
        assert [hint["notification_id"] for _, hint in hints if "notification_id" in hint] == [str(notification.id)]

    def test_a_token_linked_since_is_left_alone_and_nobody_is_notified(self, linked, committed_sessions, hints):
        rejected = stored_token(committed_sessions, linked.id)
        with committed_sessions() as db:
            relinked = garmin_factories.link_garmin(db, linked.id, di_token="access-2")
            db.commit()

        with committed_sessions() as db:
            garmin_service.unlink_expired_account(linked.id, rejected, db)

        assert stored_token(committed_sessions, linked.id) == relinked
        assert notifications_of(committed_sessions, linked.id) == []
        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_REVOKE) == []
        assert hints == []

    def test_a_token_a_rejection_handled_already_is_not_told_again(self, linked, committed_sessions):
        token = stored_token(committed_sessions, linked.id)
        for _ in range(2):
            with committed_sessions() as db:
                garmin_service.unlink_expired_account(linked.id, token, db)

        assert len(notifications_of(committed_sessions, linked.id)) == 1
        assert len(audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_REVOKE)) == 1

    def test_a_rejected_session_unlinks_the_account_it_was_stored_as(self, account, linked, committed_sessions):
        token = stored_token(committed_sessions, linked.id)

        garmin_service.handle_rejected_token(
            linked.id, _session(account, token), garminconnect.GarminConnectAuthenticationError("401")
        )

        assert stored_token(committed_sessions, linked.id) is None
        assert len(notifications_of(committed_sessions, linked.id)) == 1


class TestSaveRefreshedToken:
    def test_a_refreshed_token_is_stored_while_the_old_one_is_still_linked(self, account, linked, committed_sessions):
        old = stored_token(committed_sessions, linked.id)
        session = _session(account, old)
        session.client.client.di_token = "access-rotated"
        session.client.client.di_refresh_token = "refresh-rotated"

        garmin_service.save_refreshed_token(linked.id, session)

        assert stored_token(committed_sessions, linked.id) != old
        assert stored_access_token(committed_sessions, linked.id) == "access-rotated"

    def test_an_unchanged_token_writes_nothing(self, account, linked, committed_sessions):
        old = stored_token(committed_sessions, linked.id)

        garmin_service.save_refreshed_token(linked.id, _session(account, old))

        assert stored_token(committed_sessions, linked.id) == old

    def test_a_token_linked_since_is_not_overwritten(self, account, linked, committed_sessions):
        old = stored_token(committed_sessions, linked.id)
        with committed_sessions() as db:
            relinked = garmin_factories.link_garmin(db, linked.id, di_token="access-2")
            db.commit()
        session = _session(account, old)
        session.client.client.di_token = "access-rotated"

        garmin_service.save_refreshed_token(linked.id, session)

        assert stored_token(committed_sessions, linked.id) == relinked

    def test_a_failure_to_store_is_logged_not_raised(self, account, linked, committed_sessions, caplog):
        old = stored_token(committed_sessions, linked.id)
        session = _session(account, old)
        # A lone surrogate cannot be encrypted, so the refreshed token cannot be stored.
        session.client.client.di_token = "\ud800"

        garmin_service.save_refreshed_token(linked.id, session)

        assert stored_token(committed_sessions, linked.id) == old
        assert "Failed to store the refreshed Garmin Connect token" in caplog.text

    def test_a_bug_is_not_swallowed(self, linked, committed_sessions):
        old = stored_token(committed_sessions, linked.id)

        with pytest.raises(AttributeError):
            garmin_service.save_refreshed_token(linked.id, garmin_service.GarminSession(object(), old))


class TestLinkedSession:
    def test_an_unlinked_user_yields_no_session_and_stores_nothing(self, account, unlinked, rate_limits):
        with garmin_service.linked_session(unlinked.id, rate_limits) as session:
            assert session is None

        assert account.clients == []

    def test_a_token_the_client_refreshed_is_stored_when_the_body_succeeds(
        self, account, linked, rate_limits, committed_sessions
    ):
        with garmin_service.linked_session(linked.id, rate_limits) as session:
            session.client.client.di_token = "access-rotated"

        assert stored_access_token(committed_sessions, linked.id) == "access-rotated"

    def test_a_token_the_client_refreshed_is_stored_when_the_body_fails(
        self, account, linked, rate_limits, committed_sessions
    ):
        with pytest.raises(RuntimeError), garmin_service.linked_session(linked.id, rate_limits) as session:
            session.client.client.di_token = "access-rotated"
            raise RuntimeError("boom")

        assert stored_access_token(committed_sessions, linked.id) == "access-rotated"

    def test_no_database_session_is_open_while_the_body_runs(self, account, linked, rate_limits):
        with garmin_service.linked_session(linked.id, rate_limits):
            assert core_database.engine.pool.checkedout() == 0

    def test_an_expiring_token_is_refreshed_before_the_body_runs(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.expiring_tokens.add("access-1")

        with garmin_service.linked_session(linked.id, rate_limits) as session:
            assert session.client.client.di_token == "access-refreshed-1"

        assert stored_access_token(committed_sessions, linked.id) == "access-refreshed-1"


class TestRateLimit:
    """A Garmin Connect 429 is remembered for every process, and refuses the calls that follow."""

    def test_a_rate_limit_is_recorded_and_its_clearing_time_returned(self, unlinked, rate_limits):
        error = garmin_service.rate_limit_error(RuntimeError("429"), unlinked.id, rate_limits)

        assert isinstance(error, core_exceptions.TooManyRequestsError)
        assert error.retry_at == rate_limits.rate_limited_until(unlinked.id)
        assert error.scope == core_exceptions.TooManyRequestsScope.PROVIDER
        cooldown = timedelta(seconds=garmin_constants.RATE_LIMIT_COOLDOWN_SECONDS)
        assert abs(error.retry_at - (datetime.now(UTC) + cooldown)) < timedelta(minutes=1)

    def test_a_call_is_refused_while_the_account_is_limited(self, unlinked, rate_limits):
        until = rate_limits.mark_rate_limited(unlinked.id)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            garmin_service.raise_if_rate_limited(unlinked.id, rate_limits)

        assert raised.value.retry_at == until
        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER

    def test_a_call_skipped_for_an_active_limit_logs_no_warning(self, unlinked, rate_limits, caplog):
        rate_limits.mark_rate_limited(unlinked.id)

        with (
            caplog.at_level("DEBUG", logger=garmin_service.logger.name),
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            garmin_service.raise_if_rate_limited(unlinked.id, rate_limits)

        skipped = [r for r in caplog.records if "skipping the call" in r.getMessage()]
        assert [r.levelname for r in skipped] == ["DEBUG"]

    def test_a_call_is_allowed_when_nothing_is_limited(self, unlinked, rate_limits):
        garmin_service.raise_if_rate_limited(unlinked.id, rate_limits)

    def test_a_limited_account_gets_no_session_and_no_token_is_restored(self, account, linked, rate_limits):
        rate_limits.mark_rate_limited(linked.id)

        with pytest.raises(core_exceptions.TooManyRequestsError), garmin_service.linked_session(linked.id, rate_limits):
            pass

        assert account.clients == []


class TestRefreshSerialisation:
    """Two syncs of one user never refresh the Garmin Connect token at once, and a refreshed token is kept."""

    def test_a_live_token_is_used_without_a_claim(self, account, linked, rate_limits, committed_sessions):
        session = _session(account, stored_token(committed_sessions, linked.id))

        assert garmin_service.fresh_session(linked.id, session, rate_limits) is session

        assert account.refreshes == 0
        assert rate_limits.claim_token_refresh(linked.id)

    def test_an_expiring_token_is_refreshed_stored_and_the_claim_released(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.expiring_tokens.add("access-1")
        session = _session(account, stored_token(committed_sessions, linked.id))

        fresh = garmin_service.fresh_session(linked.id, session, rate_limits)

        assert fresh.client.client.di_token == "access-refreshed-1"
        assert stored_access_token(committed_sessions, linked.id) == "access-refreshed-1"
        assert account.refreshes == 1
        assert rate_limits.claim_token_refresh(linked.id)

    def test_a_token_another_process_refreshed_is_used_without_refreshing_again(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.expiring_tokens.add("access-1")
        session = _session(account, stored_token(committed_sessions, linked.id))
        with committed_sessions() as db:
            garmin_factories.link_garmin(db, linked.id, di_token="access-2")
            db.commit()

        fresh = garmin_service.fresh_session(linked.id, session, rate_limits)

        assert fresh.client.client.di_token == "access-2"
        assert account.refreshes == 0

    def test_a_held_claim_makes_the_caller_wait_and_use_the_refreshed_token(
        self, account, linked, rate_limits, committed_sessions, monkeypatch
    ):
        account.expiring_tokens.add("access-1")
        session = _session(account, stored_token(committed_sessions, linked.id))
        assert rate_limits.claim_token_refresh(linked.id)
        waits: list[float] = []

        def holder_finishes(seconds):
            waits.append(seconds)
            with committed_sessions() as db:
                garmin_factories.link_garmin(db, linked.id, di_token="access-2")
                db.commit()
            rate_limits.release_token_refresh(linked.id)

        monkeypatch.setattr(garmin_service.time, "sleep", holder_finishes)

        fresh = garmin_service.fresh_session(linked.id, session, rate_limits)

        assert fresh.client.client.di_token == "access-2"
        assert waits == [garmin_constants.TOKEN_REFRESH_POLL_SECONDS]
        assert account.refreshes == 0

    def test_a_claim_held_past_the_wait_defers_the_sync(
        self, account, linked, rate_limits, committed_sessions, monkeypatch, no_waiting
    ):
        monkeypatch.setattr(garmin_constants, "TOKEN_REFRESH_WAIT_SECONDS", 0)
        account.expiring_tokens.add("access-1")
        session = _session(account, stored_token(committed_sessions, linked.id))
        assert rate_limits.claim_token_refresh(linked.id)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            garmin_service.fresh_session(linked.id, session, rate_limits)

        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER
        assert raised.value.retry_at > datetime.now(UTC)
        assert account.refreshes == 0

    def test_the_claim_is_released_when_the_refresh_raises(self, account, linked, rate_limits, committed_sessions):
        account.expiring_tokens.add("access-1")
        account.refresh_error = RuntimeError("network")
        session = _session(account, stored_token(committed_sessions, linked.id))

        with pytest.raises(RuntimeError):
            garmin_service.fresh_session(linked.id, session, rate_limits)

        assert rate_limits.claim_token_refresh(linked.id)

    def test_a_refused_refresh_leaves_the_session_to_the_library_and_releases_the_claim(
        self, account, linked, rate_limits, committed_sessions
    ):
        account.expiring_tokens.add("access-1")
        account.refresh_error = garminconnect.GarminConnectAuthenticationError("refused")
        old = stored_token(committed_sessions, linked.id)

        fresh = garmin_service.fresh_session(linked.id, _session(account, old), rate_limits)

        assert fresh.client.client.di_token == "access-1"
        assert stored_token(committed_sessions, linked.id) == old
        assert rate_limits.claim_token_refresh(linked.id)

    def test_a_user_unlinked_meanwhile_gets_no_session(self, account, linked, rate_limits, committed_sessions):
        account.expiring_tokens.add("access-1")
        session = _session(account, stored_token(committed_sessions, linked.id))
        with committed_sessions() as db:
            garmin_service.unlink_account(linked.id, _STEP_UP, _approve, db)

        assert garmin_service.fresh_session(linked.id, session, rate_limits) is None

    def test_an_unreachable_state_does_not_stop_the_refresh(self, account, linked, committed_sessions):
        account.expiring_tokens.add("access-1")
        down = garmin_rate_limit_store.GarminRateLimitStore(UnavailableState())
        session = _session(account, stored_token(committed_sessions, linked.id))

        fresh = garmin_service.fresh_session(linked.id, session, down)

        assert fresh.client.client.di_token == "access-refreshed-1"
        assert stored_access_token(committed_sessions, linked.id) == "access-refreshed-1"


def test_the_linked_user_ids_are_paged_in_ascending_order(make_linked, unlinked):
    users = sorted(make_linked().id for _ in range(3))

    first_page = garmin_service.linked_user_ids(None, 2)
    second_page = garmin_service.linked_user_ids(first_page[-1], 2)

    assert first_page == users[:2]
    assert second_page == users[2:]
    assert unlinked.id not in first_page + second_page
