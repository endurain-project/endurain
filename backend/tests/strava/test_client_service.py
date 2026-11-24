"""The Strava client: stored credentials, token refresh, 401 confirmation and rate limits, against a fake Strava."""

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jasil.runtime as platform_runtime
import pytest
import requests
from stravalib.exc import AccessUnauthorized, ObjectNotFound, RateLimitExceeded
from stravalib.exc import Fault as StravaFault

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import modules.notifications.constants as notifications_constants
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.users import make_user

_REVOKE = strava_audit_actions.ACCOUNT_REVOKE.id
_UNLINKED = notifications_constants.NotificationType.STRAVA_TOKEN_EXPIRED.stored


def _linked(db, **link):
    user = make_user(db)
    strava_factories.link_strava(db, user.id, **link)
    db.flush()
    return user


def _stored(user_id):
    """Read a user's integrations in a session of its own, so no cached row hides what the code under test wrote."""
    with core_database.SessionLocal() as session:
        return user_integrations_integration.require_user_integrations(user_id, session)


def _plain(stored: str | None) -> str | None:
    return None if stored is None else core_cryptography.decrypt_token_fernet(stored)


def _refresh_answer(access: str = "new-access", refresh: str = "new-refresh"):
    return strava_factories.ok(strava_factories.token_payload(access, refresh))


def _fault(status: int, *, headers: dict[str, str] | None = None) -> StravaFault:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    fault = StravaFault()
    fault.response = response
    return fault


class TestErrorClassification:
    @pytest.mark.parametrize(
        ("error", "rate_limit", "unauthorized", "not_found", "client_error"),
        [
            (_fault(429), True, False, False, True),
            (RateLimitExceeded("limit"), True, False, False, False),
            (_fault(401), False, True, False, True),
            (AccessUnauthorized(), False, True, False, False),
            (_fault(404), False, False, True, True),
            (ObjectNotFound(), False, False, True, False),
            (_fault(500), False, False, False, False),
            (StravaFault(), False, False, False, False),
            (RuntimeError("429 Too Many Requests"), False, False, False, False),
        ],
        ids=["429", "rate-limit-exc", "401", "unauthorized-exc", "404", "not-found-exc", "500", "no-response", "text"],
    )
    def test_an_error_is_classified_by_what_strava_answered_never_by_its_message(
        self, error, rate_limit, unauthorized, not_found, client_error
    ):
        assert strava_client_service.is_strava_rate_limit_error(error) is rate_limit
        assert strava_client_service.is_strava_unauthorized_error(error) is unauthorized
        assert strava_client_service.is_strava_not_found_error(error) is not_found
        assert strava_client_service.is_strava_client_error(error) is client_error


class TestStoredCredentials:
    def test_the_client_id_and_secret_are_decrypted(self, db):
        user = _linked(db)

        integrations = _stored(user.id)

        assert strava_client_service.get_client_id(integrations) == strava_factories.CLIENT_ID
        assert strava_client_service.get_client_secret(integrations) == strava_factories.CLIENT_SECRET

    def test_a_user_without_a_stored_client_is_told_to_reconnect(self, db):
        user = _linked(db, client_id=None)

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.get_client_id(_stored(user.id))
        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.get_client_secret(_stored(user.id))

    def test_the_client_carries_the_stored_tokens_and_their_expiry(self, db):
        user = _linked(db, expires_in=timedelta(hours=3))
        integrations = _stored(user.id)

        client = strava_client_service.create_strava_client(integrations)

        assert (client.access_token, client.refresh_token) == (
            strava_factories.ACCESS_TOKEN,
            strava_factories.REFRESH_TOKEN,
        )
        assert client.token_expires == int(integrations.strava_token_expires_at.timestamp())

    def test_a_user_who_is_not_linked_has_no_integrations_to_validate(self, db):
        user = make_user(db)

        assert strava_client_service.fetch_user_integrations_and_validate_token(user.id, db) is None

    def test_a_user_without_an_integrations_row_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            strava_client_service.fetch_user_integrations_and_validate_token(uuid.uuid4(), db)


class TestRefreshUserStravaToken:
    def test_a_token_far_from_expiry_is_left_alone(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(hours=6))

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert strava.calls == []

    def test_an_unlinked_user_is_left_alone(self, db, strava, rate_limits):
        user = make_user(db)

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert strava.calls == []

    def test_an_expiring_token_is_refreshed_with_the_stored_credentials_and_the_new_tokens_stored(
        self, db, strava, rate_limits
    ):
        user = _linked(db, expires_in=timedelta(minutes=30))
        strava.on("POST", "/oauth/token", _refresh_answer())

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        (call,) = strava.made("POST", "/oauth/token")
        assert call.form == {
            "client_id": strava_factories.CLIENT_ID,
            "client_secret": strava_factories.CLIENT_SECRET,
            "refresh_token": strava_factories.REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
        stored = _stored(user.id)
        assert (_plain(stored.strava_token), _plain(stored.strava_refresh_token)) == ("new-access", "new-refresh")
        assert stored.strava_token_expires_at > datetime.now(UTC) + timedelta(hours=1)
        assert rate_limits.claim_token_refresh(user.id) is True, "the claim is released once the refresh is over"

    def test_no_database_session_is_open_while_strava_is_called(self, committed_sessions, strava, rate_limits):
        with committed_sessions() as db:
            user = _linked(db, expires_in=timedelta(minutes=30))
            db.commit()
        open_connections = []

        def answer(_call):
            open_connections.append(core_database.engine.pool.checkedout())
            return _refresh_answer()

        strava.on("POST", "/oauth/token", answer)

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert open_connections == [0]

    def test_tokens_another_process_stored_meanwhile_are_not_overwritten(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=30))

        def relinked_meanwhile(_call):
            with core_database.SessionLocal() as session:
                user_integrations_integration.link_strava_account(
                    user.id, strava_factories.token_payload("relinked-access", "relinked-refresh"), session
                )
                session.commit()
            return _refresh_answer()

        strava.on("POST", "/oauth/token", relinked_meanwhile)

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == "relinked-refresh"

    def test_a_rate_limited_refresh_marks_the_limit_and_leaves_the_tokens(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=30))
        strava.on("POST", "/oauth/token", strava_factories.rate_limited())

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert rate_limits.is_rate_limited(strava_factories.CLIENT_ID) is True
        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN

    def test_a_limited_application_skips_the_refresh_but_another_application_does_not(self, db, strava, rate_limits):
        limited = _linked(db, expires_in=timedelta(minutes=30))
        other = _linked(db, expires_in=timedelta(minutes=30), client_id="777")
        rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)
        strava.on("POST", "/oauth/token", _refresh_answer())

        strava_client_service.refresh_user_strava_token(limited.id, rate_limits)
        assert strava.calls == []
        strava_client_service.refresh_user_strava_token(other.id, rate_limits)

        assert [call.form["client_id"] for call in strava.calls] == ["777"]

    def test_a_failed_refresh_of_a_token_still_valid_is_left_to_the_sync(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=30))
        strava.on("POST", "/oauth/token", strava_factories.refused(500))

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN
        assert rate_limits.claim_token_refresh(user.id) is True, "a failed refresh still releases the claim"

    def test_an_expired_token_that_could_not_be_refreshed_is_never_handed_to_the_sync(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        strava.on("POST", "/oauth/token", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

    def test_an_expired_token_is_not_handed_to_the_sync_while_the_application_is_rate_limited(
        self, db, strava, rate_limits
    ):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

    def test_an_expired_token_is_not_used_while_another_process_refreshes_it(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        rate_limits.claim_token_refresh(user.id)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert raised.value.retry_at > datetime.now(UTC)
        assert strava.calls == []

    def test_a_token_still_valid_while_another_process_refreshes_it_is_left_to_it(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=30))
        rate_limits.claim_token_refresh(user.id)

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert strava.calls == []

    def test_tokens_that_cannot_be_stored_leave_the_old_ones_for_a_refresh_that_was_due(
        self, committed_sessions, strava, rate_limits
    ):
        with committed_sessions() as db:
            user = _linked(db, expires_in=timedelta(minutes=30))
            db.commit()
        # Encrypted, an access token this long no longer fits its column.
        strava.on("POST", "/oauth/token", _refresh_answer(access="a" * 600))

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_token) == strava_factories.ACCESS_TOKEN


class TestRefreshRefused:
    @pytest.fixture
    def user(self, db):
        return _linked(db, expires_in=timedelta(minutes=-5))

    @pytest.mark.parametrize("status", [400, 401])
    def test_a_refresh_token_strava_refuses_is_a_revocation_that_unlinks_and_stops_the_sync(
        self, user, db, strava, rate_limits, status
    ):
        strava.on("POST", "/oauth/token", strava_factories.refused(status, resource="RefreshToken"))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        stored = _stored(user.id)
        assert (stored.strava_token, stored.strava_refresh_token) == (None, None)
        assert stored.strava_revoked_at is not None
        assert stored.strava_client_id is not None, "the client stays so relinking is one step"
        assert len(strava_factories.notifications_of(db, user.id, _UNLINKED)) == 1
        assert [row.target_owner_id for row in strava_factories.audit_rows(db, _REVOKE)] == [str(user.id)]

    def test_a_refusal_that_does_not_name_the_refresh_token_keeps_the_tokens(self, user, db, strava, rate_limits):
        strava.on("POST", "/oauth/token", strava_factories.refused(400, resource="Application"))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN
        assert strava_factories.audit_rows(db, _REVOKE) == []


class TestRefusalBodies:
    """Only a body that names the refresh token is a revocation; a body that cannot be read never is."""

    @pytest.mark.parametrize(
        "body",
        [
            "<html>Bad Gateway</html>",
            {"message": "Bad Request"},
            {"errors": "RefreshToken"},
            {"errors": ["RefreshToken", 7]},
        ],
        ids=["not-json", "no-errors", "errors-not-a-list", "entries-not-mappings"],
    )
    def test_a_refusal_whose_body_does_not_name_the_refresh_token_keeps_the_tokens(self, db, strava, rate_limits, body):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        strava.on("POST", "/oauth/token", strava_factories.Reply(400, body))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN

    def test_a_refusal_naming_the_refresh_token_among_unreadable_entries_is_still_a_revocation(
        self, db, strava, rate_limits
    ):
        user = _linked(db, expires_in=timedelta(minutes=-5))
        body = {"errors": ["noise", {"resource": "RefreshToken", "field": "refresh_token", "code": "invalid"}]}
        strava.on("POST", "/oauth/token", strava_factories.Reply(401, body))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)


class TestAConnectionThatFails:
    def test_a_refresh_that_cannot_reach_strava_is_not_a_revocation(self, db, strava, rate_limits):
        user = _linked(db, expires_in=timedelta(minutes=-5))

        def unreachable(_call):
            raise requests.ConnectionError("no route to Strava")

        strava.on("POST", "/oauth/token", unreachable)

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN


class _RefreshedByAnotherProcess(strava_rate_limit_store.StravaRateLimitStore):
    """A rate-limit store whose claim is taken just after another process stored fresh tokens."""

    def __init__(self, state, user_id):
        super().__init__(state)
        self._user_id = user_id

    def claim_token_refresh(self, user_id):
        with core_database.SessionLocal() as session:
            user_integrations_integration.link_strava_account(
                self._user_id, strava_factories.token_payload("theirs", "their-refresh"), session
            )
            session.commit()
        return super().claim_token_refresh(user_id)


class TestAnotherProcessRefreshedFirst:
    def test_a_refresh_another_process_just_finished_is_not_repeated(self, db, strava):
        user = _linked(db, expires_in=timedelta(minutes=30))
        rate_limits = _RefreshedByAnotherProcess(platform_runtime.get_state(), user.id)

        strava_client_service.refresh_user_strava_token(user.id, rate_limits)

        assert strava.calls == []
        assert _plain(_stored(user.id).strava_refresh_token) == "their-refresh"


class TestForcedRefresh:
    def test_tokens_that_cannot_be_stored_stop_a_sync_that_asked_for_the_refresh(
        self, committed_sessions, strava, rate_limits
    ):
        with committed_sessions() as db:
            user = _linked(db)
            db.commit()
        strava.on("POST", "/oauth/token", _refresh_answer(access="a" * 600))
        stored = _stored(user.id)

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_client_service.refresh_user_strava_token(
                user.id, rate_limits, rejected_refresh_token=stored.strava_refresh_token
            )

        assert _plain(_stored(user.id).strava_token) == strava_factories.ACCESS_TOKEN


class TestHandleRejectedToken:
    def test_the_rejected_token_is_unlinked_and_the_user_told_and_audited(self, db):
        user = _linked(db)
        stored = _stored(user.id)

        strava_client_service.handle_rejected_token(user.id, stored.strava_refresh_token, AccessUnauthorized())

        after = _stored(user.id)
        assert (after.strava_token, after.strava_refresh_token, after.strava_revoked_at) == (None, None, None)
        (notice,) = strava_factories.notifications_of(db, user.id, _UNLINKED)
        assert notice.options == {}
        assert len(strava_factories.audit_rows(db, _REVOKE)) == 1

    def test_a_revocation_stores_its_time_and_names_the_day_the_data_goes(self, db):
        user = _linked(db)

        strava_client_service.handle_rejected_token(
            user.id, _stored(user.id).strava_refresh_token, AccessUnauthorized(), revoked=True
        )

        revoked_at = _stored(user.id).strava_revoked_at
        (notice,) = strava_factories.notifications_of(db, user.id, _UNLINKED)
        assert revoked_at is not None
        assert notice.options == {"delete_on": (revoked_at + timedelta(days=_grace_days())).date().isoformat()}

    def test_a_token_linked_since_is_left_alone_and_nobody_is_told(self, db):
        user = _linked(db)
        stale = _stored(user.id).strava_refresh_token
        with core_database.SessionLocal() as session:
            user_integrations_integration.link_strava_account(
                user.id, strava_factories.token_payload("a", "relinked"), session
            )
            session.commit()

        strava_client_service.handle_rejected_token(user.id, stale, AccessUnauthorized())

        assert _plain(_stored(user.id).strava_refresh_token) == "relinked"
        assert strava_factories.notifications_of(db, user.id, _UNLINKED) == []
        assert strava_factories.audit_rows(db, _REVOKE) == []

    def test_an_account_with_no_refresh_token_has_nothing_to_unlink(self, db):
        user = make_user(db)

        strava_client_service.handle_rejected_token(user.id, None, AccessUnauthorized())

        assert strava_factories.notifications_of(db, user.id, _UNLINKED) == []


def _grace_days() -> int:
    import modules.users.users_integrations.constants as user_integrations_constants

    return user_integrations_constants.STRAVA_REVOKED_DATA_GRACE_DAYS


class TestCallStrava:
    @pytest.fixture
    def user(self, db):
        return _linked(db)

    def _call(self, user, rate_limits, integrations=None):
        integrations = integrations or _stored(user.id)
        return strava_client_service.call_strava(
            lambda client: client.get_athlete(),
            strava_client_service.create_strava_client(integrations),
            user.id,
            integrations,
            rate_limits,
        )

    def test_a_successful_call_makes_no_refresh(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload()))

        athlete = self._call(user, rate_limits)

        assert athlete.id == 12345
        assert strava.made("POST", "/oauth/token") == []

    def test_an_error_other_than_a_401_passes_through_untouched(self, user, db, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(500))

        with pytest.raises(StravaFault):
            self._call(user, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN

    def test_a_401_is_confirmed_with_a_refresh_and_the_call_made_again_with_the_new_token(
        self, user, strava, rate_limits
    ):
        strava.on(
            "GET",
            "/athlete",
            strava_factories.refused(401),
            strava_factories.ok(strava_factories.athlete_payload()),
        )
        strava.on("POST", "/oauth/token", _refresh_answer())

        athlete = self._call(user, rate_limits)

        assert athlete.id == 12345
        first, second = strava.made("GET", "/athlete")
        assert first.headers["Authorization"] == f"Bearer {strava_factories.ACCESS_TOKEN}"
        assert second.headers["Authorization"] == "Bearer new-access"
        assert _plain(_stored(user.id).strava_refresh_token) == "new-refresh"

    def test_a_401_whose_refresh_token_is_refused_is_a_revocation(self, user, db, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        strava.on("POST", "/oauth/token", strava_factories.refused(400, resource="RefreshToken"))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            self._call(user, rate_limits)

        assert _stored(user.id).strava_revoked_at is not None

    def test_a_401_again_on_the_new_token_is_a_revocation(self, user, db, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        strava.on("POST", "/oauth/token", _refresh_answer())

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            self._call(user, rate_limits)

        stored = _stored(user.id)
        assert (stored.strava_token, stored.strava_revoked_at is not None) == (None, True)
        assert len(strava_factories.audit_rows(db, _REVOKE)) == 1

    def test_a_refresh_that_fails_transiently_keeps_the_tokens_and_stops_the_sync(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        strava.on("POST", "/oauth/token", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            self._call(user, rate_limits)

        stored = _stored(user.id)
        assert _plain(stored.strava_refresh_token) == strava_factories.REFRESH_TOKEN
        assert stored.strava_revoked_at is None

    def test_an_error_other_than_a_401_on_the_retry_passes_through_and_clears_nothing(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401), strava_factories.refused(500))
        strava.on("POST", "/oauth/token", _refresh_answer())

        with pytest.raises(StravaFault):
            self._call(user, rate_limits)

        assert _plain(_stored(user.id).strava_refresh_token) == "new-refresh"

    def test_a_rate_limit_while_confirming_a_401_defers_the_sync_with_when_it_clears(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        strava.on("POST", "/oauth/token", strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            self._call(user, rate_limits)

        assert raised.value.retry_at == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)
        assert _plain(_stored(user.id).strava_refresh_token) == strava_factories.REFRESH_TOKEN

    def test_a_limited_application_defers_the_confirmation_without_calling_strava_again(
        self, user, strava, rate_limits
    ):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(user, rate_limits)

        assert strava.made("POST", "/oauth/token") == []

    def test_another_process_refreshing_defers_the_confirmation(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        rate_limits.claim_token_refresh(user.id)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(user, rate_limits)

        assert strava.made("POST", "/oauth/token") == []

    def test_a_refresh_token_another_process_already_replaced_is_not_refreshed_again(self, user, strava, rate_limits):
        stale = _stored(user.id)
        with core_database.SessionLocal() as session:
            user_integrations_integration.link_strava_account(
                user.id, strava_factories.token_payload("a", "relinked"), session
            )
            session.commit()
        strava.on(
            "GET", "/athlete", strava_factories.refused(401), strava_factories.ok(strava_factories.athlete_payload())
        )

        athlete = self._call(user, rate_limits, integrations=stale)

        assert athlete.id == 12345
        assert strava.made("POST", "/oauth/token") == []

    def test_an_account_unlinked_meanwhile_stops_the_sync(self, user, db, strava, rate_limits):
        stale = _stored(user.id)
        with core_database.SessionLocal() as session:
            user_integrations_integration.unlink_strava_account(user.id, session)
            session.commit()
        strava.on("GET", "/athlete", strava_factories.refused(401))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            self._call(user, rate_limits, integrations=stale)

    def test_a_client_without_a_refresh_token_cannot_confirm_a_401(self, user, strava, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(401))
        integrations = _stored(user.id).model_copy(update={"strava_refresh_token": None})

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            self._call(user, rate_limits, integrations=integrations)

    def test_strava_is_called_with_no_database_session_open(self, committed_sessions, strava, rate_limits):
        with committed_sessions() as db:
            user = _linked(db)
            db.commit()
        open_connections = []

        def answer(_call):
            open_connections.append(core_database.engine.pool.checkedout())
            return (
                strava_factories.refused(401)
                if len(open_connections) == 1
                else strava_factories.ok(strava_factories.athlete_payload())
            )

        strava.on("GET", "/athlete", answer)
        strava.on(
            "POST",
            "/oauth/token",
            lambda _call: (open_connections.append(core_database.engine.pool.checkedout()), _refresh_answer())[1],
        )

        self._call(user, rate_limits)

        assert open_connections == [0, 0, 0]


class TestRateLimitRefusal:
    """A provider 429 becomes a TooManyRequestsError that says when the application may call again."""

    @pytest.fixture
    def user(self, db):
        return _linked(db)

    def _hit(self, strava, rate_limits, user, reply):
        strava.on("GET", "/athlete", reply)
        integrations = _stored(user.id)
        client = strava_client_service.create_strava_client(integrations)
        with pytest.raises(StravaFault) as raised:
            client.get_athlete()
        return raised.value

    def test_a_429_is_recorded_for_the_application_and_refused_with_its_retry_time(self, user, strava, rate_limits):
        error = self._hit(strava, rate_limits, user, strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_client_service.raise_if_rate_limited(error, strava_factories.CLIENT_ID, rate_limits)

        cooldown = timedelta(seconds=15 * 60)
        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER
        assert raised.value.retry_at == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)
        assert datetime.now(UTC) < raised.value.retry_at <= datetime.now(UTC) + cooldown
        assert rate_limits.is_rate_limited("another-application") is False

    def test_the_daily_limit_reads_from_the_usage_headers_and_clears_at_midnight(self, user, strava, rate_limits):
        error = self._hit(strava, rate_limits, user, strava_factories.rate_limited(daily=True))

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_client_service.raise_if_rate_limited(error, strava_factories.CLIENT_ID, rate_limits)

        assert (raised.value.retry_at.hour, raised.value.retry_at.minute) == (0, 0)

    def test_an_error_that_is_not_a_rate_limit_passes_through(self, user, strava, rate_limits):
        error = self._hit(strava, rate_limits, user, strava_factories.refused(500))

        strava_client_service.raise_if_rate_limited(error, strava_factories.CLIENT_ID, rate_limits)

        assert rate_limits.is_rate_limited(strava_factories.CLIENT_ID) is False

    def test_a_rate_limit_without_a_response_is_a_short_term_one(self, rate_limits):
        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_client_service.raise_if_rate_limited(
                RateLimitExceeded("limit"), strava_factories.CLIENT_ID, rate_limits
            )

        assert raised.value.retry_at <= datetime.now(UTC) + timedelta(minutes=15)

    def test_an_active_limit_refuses_the_call_and_says_when_it_clears(self, rate_limits):
        until = rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_client_service.raise_if_rate_limit_active(strava_factories.CLIENT_ID, uuid.uuid4(), rate_limits)

        assert raised.value.retry_at == until

    def test_no_limit_lets_the_call_through(self, rate_limits):
        strava_client_service.raise_if_rate_limit_active(strava_factories.CLIENT_ID, uuid.uuid4(), rate_limits)


class TestClientConstruction:
    def test_a_process_that_never_loaded_the_api_builds_a_client_without_stravalib_warnings(self):
        """A worker imports the Strava module without main.py; stravalib must still not log its credential warnings."""
        app_dir = Path(__file__).resolve().parents[2] / "app"
        environment = {k: v for k, v in os.environ.items() if k != "SILENCE_TOKEN_WARNINGS"}
        script = (
            "import modules.strava.client_service as client_service\n"
            "import modules.users.users_integrations.schema as schema\n"
            "integrations = schema.UserIntegrationsRead.model_construct("
            "strava_token=None, strava_refresh_token=None, strava_token_expires_at=None)\n"
            "client_service.create_strava_client(integrations)\n"
        )

        async def run() -> tuple[int | None, str]:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                cwd=app_dir,
                env={**environment, "PYTHONPATH": str(app_dir)},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            return process.returncode, stderr.decode()

        returncode, stderr = asyncio.run(run())

        assert returncode == 0, stderr
        assert "STRAVA_CLIENT_ID" not in stderr
