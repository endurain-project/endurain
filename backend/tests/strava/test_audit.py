"""Audit rows of the Strava client, the account link, unlink and revocation, and the gear import."""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
import pytest
from fastapi import UploadFile
from sqlalchemy.orm.exc import StaleDataError
from stravalib.exc import AccessUnauthorized, RateLimitExceeded
from stravalib.exc import Fault as StravaFault

import core.exceptions as core_exceptions
import modules.gears.gear.schema as gears_schema
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.gear_service as strava_gear_service
import modules.strava.link_service as strava_link_service
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store

LINK = strava_constants.SyncKind.LINK
UNLINK = strava_constants.SyncKind.UNLINK


@pytest.fixture
def states():
    return strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())


@pytest.fixture
def rate_limits():
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


def _fault(status_code: int, cls=StravaFault) -> StravaFault:
    fault = cls()
    fault.response = Mock(status_code=status_code, headers={})
    return fault


class TestClientUpdate:
    def _set(self, db, **store_kwargs):
        credentials = strava_schema.StravaClientCredentials(client_id=123, client_secret="the-secret")
        with (
            patch.object(strava_service.user_integrations_integration, "set_strava_client", **store_kwargs),
            patch.object(
                strava_service.user_integrations_integration, "get_user_integrations", return_value=MagicMock(version=3)
            ),
        ):
            return strava_service.set_client(7, credentials, db, if_match='"2"')

    def test_storing_the_client_is_audited_without_the_id_or_secret(self):
        with jasil_testing.capture_audit() as audit:
            self._set(MagicMock())

        entry = audit.assert_audited(
            strava_audit_actions.CLIENT_UPDATE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details is None

    def test_a_stale_write_is_not_audited(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PreconditionFailedError):
            self._set(MagicMock(), side_effect=StaleDataError())

        audit.assert_not_audited(strava_audit_actions.CLIENT_UPDATE.id)


def _run(states, *, exchange_error=None, stage_error=None):
    states.begin(1, LINK)
    client = MagicMock()
    client.exchange_code_for_token.return_value = {"access_token": "t"}
    if exchange_error:
        client.exchange_code_for_token.side_effect = exchange_error
    sessions = MagicMock()
    sessions.return_value.__enter__.return_value = MagicMock()
    integrations = SimpleNamespace(strava_client_id="123", strava_client_secret="stored")
    with (
        patch.object(strava_link_service.core_database, "SessionLocal", sessions),
        patch.object(
            strava_link_service.user_integrations_integration, "require_user_integrations", return_value=integrations
        ),
        patch.object(strava_link_service.user_integrations_integration, "link_strava_account"),
        patch.object(strava_link_service.strava_client_service, "create_strava_client", return_value=client),
        patch.object(
            strava_link_service.strava_client_service.core_cryptography, "decrypt_token_fernet", side_effect=str
        ),
        patch.object(strava_link_service.websocket_integration, "push_job_changed"),
    ):
        strava_link_service.run_link(1, "the-code", states)


class TestAccountLink:
    def test_a_completed_link_is_audited(self, states):
        with jasil_testing.capture_audit() as audit:
            _run(states)

        entry = audit.assert_audited(
            strava_audit_actions.ACCOUNT_LINK.id,
            outcome="success",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )
        assert entry.details == {"reason": None}

    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (_fault(401, AccessUnauthorized), "unauthorized"),
            (_fault(400), "rejected"),
            (_fault(403), "rejected"),
            (_fault(429), "too_many_requests"),
            (RateLimitExceeded("limit"), "too_many_requests"),
        ],
    )
    def test_a_refused_exchange_is_audited_with_its_reason_only(self, states, error, reason):
        with jasil_testing.capture_audit() as audit:
            _run(states, exchange_error=error)

        entry = audit.assert_audited(
            strava_audit_actions.ACCOUNT_LINK.id,
            outcome="failure",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )
        assert entry.details == {"reason": reason}

    @pytest.mark.parametrize("error", [_fault(502), RuntimeError("token-123 broke"), ConnectionError("down")])
    def test_a_failure_that_is_not_a_refusal_leaves_no_row(self, states, error):
        with jasil_testing.capture_audit() as audit:
            _run(states, exchange_error=error)

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_LINK.id)


class TestAccountUnlink:
    @staticmethod
    def _settings(jobs_enabled: bool):
        return patch.object(strava_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=jobs_enabled))

    def test_with_durable_jobs_the_row_is_staged_before_the_event_commits(self, states, rate_limits):
        db = MagicMock()
        staged_at_publish = []
        with (
            self._settings(True),
            patch.object(
                strava_sync_service.strava_event_publishers,
                "publish_sync_requested",
                side_effect=lambda *a, **k: staged_at_publish.append(len(audit.entries)),
            ),
            patch.object(strava_sync_service.jasil_audit, "record_detached") as detached,
            jasil_testing.capture_audit() as audit,
        ):
            strava_sync_service.request_unlink(7, states, rate_limits, db)

        entry = audit.assert_audited(
            strava_audit_actions.ACCOUNT_UNLINK.id,
            outcome="success",
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert entry.details is None
        assert staged_at_publish == [1]
        detached.assert_not_called()

    def test_without_durable_jobs_the_row_is_written_once_the_pool_took_the_unlink(self, states, rate_limits):
        with (
            self._settings(False),
            patch.object(strava_sync_service, "_sync_pool") as pool,
            jasil_testing.capture_audit() as audit,
        ):
            strava_sync_service.request_unlink(7, states, rate_limits, MagicMock())

        pool.submit.assert_called_once()
        entry = audit.assert_audited(
            strava_audit_actions.ACCOUNT_UNLINK.id,
            outcome="success",
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert entry.details is None

    def test_with_durable_jobs_an_unlink_already_pending_never_commits_its_row(self, states, rate_limits):
        states.begin(7, UNLINK)
        db = MagicMock()
        with (
            self._settings(True),
            patch.object(strava_sync_service.strava_event_publishers, "publish_sync_requested") as publish,
            pytest.raises(core_exceptions.ConflictError),
        ):
            strava_sync_service.request_unlink(7, states, rate_limits, db)

        publish.assert_not_called()
        db.commit.assert_not_called()

    def test_without_durable_jobs_an_unlink_already_pending_is_not_audited(self, states, rate_limits):
        states.begin(7, UNLINK)
        with (
            self._settings(False),
            patch.object(strava_sync_service, "_sync_pool"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ConflictError),
        ):
            strava_sync_service.request_unlink(7, states, rate_limits, MagicMock())

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_UNLINK.id)

    def test_a_full_pool_is_not_audited(self, states, rate_limits):
        with (
            self._settings(False),
            patch.object(strava_sync_service, "_sync_pool") as pool,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            pool.submit.side_effect = core_exceptions.ServiceUnavailableError("full")
            strava_sync_service.request_unlink(7, states, rate_limits, MagicMock())

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_UNLINK.id)

    def test_a_gear_sync_request_is_not_audited(self, states, rate_limits):
        with (
            self._settings(False),
            patch.object(strava_sync_service, "_sync_pool"),
            jasil_testing.capture_audit() as audit,
        ):
            strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_UNLINK.id)

    def test_the_unlink_job_itself_writes_no_row(self):
        with (
            patch.object(strava_service.core_database, "SessionLocal"),
            patch.object(
                strava_service.strava_client_service, "fetch_user_integrations_and_validate_token", return_value=None
            ),
            jasil_testing.capture_audit() as audit,
        ):
            strava_service.unlink_account(7)

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_UNLINK.id)


class TestAccountRevoke:
    def _reject(self, *, unlinked: bool):
        sessions = MagicMock()
        sessions.return_value.__enter__.return_value = MagicMock()
        with (
            patch.object(strava_client_service.core_database, "SessionLocal", sessions),
            patch.object(
                strava_client_service.user_integrations_integration,
                "unlink_strava_tokens_if_refresh_token",
                return_value=unlinked,
            ),
            patch.object(
                strava_client_service.notifications_integration,
                "create_strava_token_expired_notification",
                return_value=("n", "ws"),
            ),
            patch.object(strava_client_service.notifications_integration, "push_notification"),
            jasil_testing.capture_audit() as audit,
        ):
            strava_client_service.handle_rejected_token(7, "enc-refresh", ValueError("401"))
        return audit

    def test_an_account_unlinked_because_strava_rejected_its_token_is_audited(self):
        audit = self._reject(unlinked=True)

        entry = audit.assert_audited(
            strava_audit_actions.ACCOUNT_REVOKE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details is None

    def test_a_token_relinked_since_leaves_no_row(self):
        audit = self._reject(unlinked=False)

        audit.assert_not_audited(strava_audit_actions.ACCOUNT_REVOKE.id)


BIKES = b"Bike Name,Bike Brand,Bike Model\nCommuter,Trek,Domane\nRoad,Canyon,Ultimate\n"
SHOES = b"Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Pegasus\n"


def _upload(content: bytes) -> UploadFile:
    return UploadFile(filename="secret-name.csv", file=io.BytesIO(content))


class TestGearImport:
    def test_imported_bikes_are_audited_with_the_type_and_count_only(self):
        with (
            patch.object(strava_gear_service.gears_integration, "create_multiple_gears"),
            jasil_testing.capture_audit() as audit,
        ):
            strava_gear_service.import_gear(_upload(BIKES), 7, gears_schema.GearType.BIKE, MagicMock())

        entry = audit.assert_audited(
            strava_audit_actions.GEAR_IMPORT.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"gear_type": "bikes", "count": 2}

    def test_imported_shoes_are_audited_with_their_type(self):
        with (
            patch.object(strava_gear_service.gears_integration, "create_multiple_gears"),
            patch.object(strava_gear_service.gears_integration, "get_gear_user", return_value=[]),
            jasil_testing.capture_audit() as audit,
        ):
            strava_gear_service.import_gear(_upload(SHOES), 7, gears_schema.GearType.SHOES, MagicMock())

        entry = audit.assert_audited(strava_audit_actions.GEAR_IMPORT.id)
        assert entry.details == {"gear_type": "shoes", "count": 1}

    def test_a_file_listing_no_gear_is_not_audited(self):
        with jasil_testing.capture_audit() as audit:
            strava_gear_service.import_gear(
                _upload(b"Bike Name,Bike Brand,Bike Model\n"), 7, gears_schema.GearType.BIKE, MagicMock()
            )

        audit.assert_not_audited(strava_audit_actions.GEAR_IMPORT.id)

    def test_a_file_that_cannot_be_parsed_is_not_audited(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            strava_gear_service.import_gear(_upload(b"Name\nx\n"), 7, gears_schema.GearType.BIKE, MagicMock())

        audit.assert_not_audited(strava_audit_actions.GEAR_IMPORT.id)
