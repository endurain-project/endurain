"""Audit rows of the Garmin Connect account link, unlink and revocation."""

from unittest.mock import MagicMock, patch

import garminconnect
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.link_service as garmin_link_service
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.service as garmin_service


@pytest.fixture
def stores():
    state = MemoryState()
    return mfa_code_store.GarminMFACodeStore(state=state), link_state_store.GarminLinkStateStore(state=state)


def _link(stores, *, login=None, has_token=True, prompt_mfa=False):
    mfa_codes, link_states = stores
    link_states.begin(1)
    garmin = MagicMock()
    garmin.client.di_token = "enc" if has_token else None

    def do_login():
        if prompt_mfa:
            garmin_link_service.garminconnect.Garmin.call_args.kwargs["prompt_mfa"]()
        if login is not None:
            raise login

    garmin.login.side_effect = do_login
    with (
        patch.object(garmin_link_service.websocket_integration, "push_job_changed"),
        patch.object(garmin_link_service.garminconnect, "Garmin", return_value=garmin),
        patch.object(garmin_link_service.core_database, "SessionLocal"),
        patch.object(garmin_link_service.user_integrations_integration, "link_garminconnect_account"),
        patch.object(garmin_link_service, "wait_for_mfa_code", return_value=None),
        patch.object(
            garmin_link_service.garmin_token_utils, "serialize_garmin_token", return_value={"di_token": "enc"}
        ),
        jasil_testing.capture_audit() as audit,
    ):
        garmin_link_service.link_garminconnect(1, "me@example.com", "pw-secret", mfa_codes, link_states)
    return audit


class TestAccountLink:
    def test_a_completed_link_is_audited(self, stores):
        audit = _link(stores)

        entry = audit.assert_audited(
            garmin_audit_actions.ACCOUNT_LINK.id,
            outcome="success",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )
        assert entry.details == {"reason": None}

    @pytest.mark.parametrize(
        ("kwargs", "reason"),
        [
            ({"login": garminconnect.GarminConnectAuthenticationError("bad")}, "invalid_credentials"),
            ({"has_token": False}, "invalid_credentials"),
            (
                {"login": garminconnect.GarminConnectAuthenticationError("mfa"), "prompt_mfa": True},
                "incorrect_mfa",
            ),
            ({"login": garminconnect.GarminConnectTooManyRequestsError("slow")}, "too_many_requests"),
        ],
    )
    def test_a_refused_link_is_audited_with_its_reason_only(self, stores, kwargs, reason):
        audit = _link(stores, **kwargs)

        entry = audit.assert_audited(
            garmin_audit_actions.ACCOUNT_LINK.id,
            outcome="failure",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )
        assert entry.details == {"reason": reason}

    @pytest.mark.parametrize(
        "error", [garminconnect.GarminConnectConnectionError("down"), RuntimeError("boom"), TypeError("bug")]
    )
    def test_an_internal_error_leaves_no_row(self, stores, error):
        audit = _link(stores, login=error)

        audit.assert_not_audited(garmin_audit_actions.ACCOUNT_LINK.id)


class TestAccountUnlink:
    def test_unlinking_is_audited(self):
        db = MagicMock()
        with (
            patch.object(garmin_service.user_integrations_integration, "unlink_garminconnect_account"),
            jasil_testing.capture_audit() as audit,
        ):
            garmin_service.unlink_account(5, db)

        entry = audit.assert_audited(
            garmin_audit_actions.ACCOUNT_UNLINK.id, target_type="user", target_id="5", target_owner_id="5"
        )
        assert entry.details is None
        db.commit.assert_called_once()

    def test_an_unlink_that_fails_is_not_audited(self):
        with (
            patch.object(
                garmin_service.user_integrations_integration,
                "unlink_garminconnect_account",
                side_effect=RuntimeError("no integrations"),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(RuntimeError),
        ):
            garmin_service.unlink_account(5, MagicMock())

        audit.assert_not_audited(garmin_audit_actions.ACCOUNT_UNLINK.id)


class TestAccountRevoke:
    def _expire(self, *, unlinked: bool):
        with (
            patch.object(
                garmin_service.user_integrations_integration,
                "unlink_garminconnect_account_if_token",
                return_value=unlinked,
            ),
            patch.object(
                garmin_service.notifications_integration,
                "create_garmin_token_expired_notification",
                return_value=("n", "ws"),
            ),
            patch.object(garmin_service.notifications_integration, "push_notification"),
            jasil_testing.capture_audit() as audit,
        ):
            garmin_service.unlink_expired_account(5, {"di_token": "old"}, MagicMock())
        return audit

    def test_an_account_unlinked_because_its_token_was_rejected_is_audited_as_a_revocation(self):
        audit = self._expire(unlinked=True)

        entry = audit.assert_audited(
            garmin_audit_actions.ACCOUNT_REVOKE.id, target_type="user", target_id="5", target_owner_id="5"
        )
        assert entry.details is None
        audit.assert_not_audited(garmin_audit_actions.ACCOUNT_UNLINK.id)

    def test_a_token_relinked_since_leaves_no_row(self):
        audit = self._expire(unlinked=False)

        audit.assert_not_audited(garmin_audit_actions.ACCOUNT_REVOKE.id)
