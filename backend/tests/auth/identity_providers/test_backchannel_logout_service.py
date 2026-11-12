"""Tests for OIDC back-channel logout: provider resolution, token checks, replay, matching, audit and transactions.

The sign-ins and links live in a real SQLite database; logout tokens are signed with a real RSA key. Only the
provider's discovery document and JWKS, and the sessions surface the sign-ins end through, are stand-ins.
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.service as identity_links_service
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.backchannel_logout_service as backchannel_logout_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.sessions.audit_actions as sessions_audit_actions
from tests._helpers.db import create_sqlite_session

IDP_ID = uuid.uuid4()
OTHER_IDP_ID = uuid.uuid4()
ISS = "https://idp.example.com"
CLIENT_ID = "endurain-client"
JWKS_URI = "https://idp.example.com/jwks"
EVENT = "http://schemas.openid.net/event/backchannel-logout"

#: (session_id, user_id, idp_id, sid) of each stored sign-in.
_SIGN_INS = (
    ("s1", 7, IDP_ID, "sid-a"),
    ("s2", 7, IDP_ID, "sid-a"),
    ("s3", 8, IDP_ID, "sid-a"),
    ("s4", 7, IDP_ID, "sid-b"),
    ("s5", 7, IDP_ID, None),
    ("s6", 7, OTHER_IDP_ID, "sid-a"),
)


@pytest.fixture(scope="module")
def rsa_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": "k1"})


@pytest.fixture
def db():
    session = create_sqlite_session()
    for session_id, user_id, idp_id, sid in _SIGN_INS:
        identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, None, None, session, idp_sid=sid)
    identity_links_crud.create_user_identity_provider(7, IDP_ID, "subject-7", session)
    identity_links_crud.create_user_identity_provider(8, IDP_ID, "subject-8", session)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def oidc(rsa_key):
    client = oidc_client_service.OidcClientService(MemoryState(), "test")
    with (
        patch.object(client, "get_oidc_configuration", return_value={"issuer": ISS, "jwks_uri": JWKS_URI}),
        patch.object(client, "fetch_jwks", return_value={"keys": [rsa_key.as_dict(private=False)]}),
        patch.object(client, "decrypt_client_id", return_value=CLIENT_ID),
    ):
        yield client


@pytest.fixture
def service(oidc, state):
    return backchannel_logout_service.BackchannelLogoutService(oidc, state)


def _idp(**overrides):
    values = {"id": IDP_ID, "name": "Pocket ID", "slug": "pocket-id", "enabled": True, "provider_type": "oidc"}
    values.update(overrides)
    return SimpleNamespace(**values)


def _token(key: RSAKey, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISS,
        "aud": CLIENT_ID,
        "iat": now,
        "exp": now + 120,
        "jti": "jti-1",
        "events": {EVENT: {}},
        **overrides,
    }
    return jwt.encode(
        {"alg": "RS256", "kid": "k1", "typ": "logout+jwt"}, {k: v for k, v in claims.items() if v is not None}, key
    )


class _Run:
    """One logout request, with the sessions that are still live and what the sessions surface was asked to end."""

    def __init__(self, service, db, *, idp=None, live=("s1", "s2", "s3", "s4", "s5", "s6")):
        self.service = service
        self.db = db
        self.idp = idp if idp is not None else _idp()
        self.live = set(live)
        self.deleted: list[tuple[str, int]] = []

    def _delete(self, session_id: str, user_id: int, _db) -> bool:
        if session_id not in self.live:
            return False
        self.deleted.append((session_id, user_id))
        return True

    def __call__(self, token: str) -> None:
        with (
            patch.object(backchannel_logout_service.idp_crud, "get_identity_provider_by_slug", return_value=self.idp),
            patch.object(
                identity_links_service.sessions_integration,
                "delete_session_if_present",
                side_effect=self._delete,
            ),
        ):
            self.service.logout("pocket-id", token, self.db)


class TestProviderResolution:
    @pytest.mark.parametrize(
        "idp",
        [None, _idp(provider_type="oauth2", scopes="profile email")],
        ids=["unknown", "without-id-tokens"],
    )
    def test_a_provider_without_back_channel_logout_is_not_found(self, service, db, rsa_key, idp):
        run = _Run(service, db)
        run.idp = idp
        with (
            patch.object(backchannel_logout_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            service.logout("pocket-id", _token(rsa_key, sid="sid-a"), db)

        audit.assert_not_audited(idp_audit_actions.BACKCHANNEL_LOGOUT_REFUSE.id)

    def test_a_disabled_provider_still_ends_the_sessions_signed_in_through_it(self, service, db, rsa_key):
        run = _Run(service, db, idp=_idp(enabled=False))

        run(_token(rsa_key, sid="sid-b"))

        assert run.deleted == [("s4", 7)]

    def test_an_oauth2_provider_asked_for_openid_has_back_channel_logout(self, service, db, rsa_key):
        run = _Run(service, db, idp=_idp(provider_type="oauth2", scopes="openid profile"))

        run(_token(rsa_key, sid="sid-b"))

        assert run.deleted == [("s4", 7)]

    def test_the_read_transaction_ends_before_the_provider_is_reached(self, service, oidc, rsa_key):
        db = MagicMock()
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        order.attach_mock(oidc.get_oidc_configuration, "discovery")
        order.attach_mock(oidc.fetch_jwks, "jwks")
        with patch.object(backchannel_logout_service, "_end_sessions"):
            _Run(service, db)(_token(rsa_key, sid="sid-a"))

        assert [call[0] for call in order.mock_calls][:3] == ["commit", "discovery", "jwks"]


class TestMatching:
    def test_a_sid_ends_the_live_sessions_of_that_provider_session(self, service, db, rsa_key):
        run = _Run(service, db, live=("s1", "s3", "s4", "s6"))

        run(_token(rsa_key, sid="sid-a"))

        assert sorted(run.deleted) == [("s1", 7), ("s3", 8)]

    def test_a_sid_with_a_sub_ends_only_the_linked_users_sessions(self, service, db, rsa_key):
        run = _Run(service, db)

        run(_token(rsa_key, sid="sid-a", sub="subject-8"))

        assert run.deleted == [("s3", 8)]

    def test_a_sid_with_a_sub_of_another_user_ends_nothing(self, service, db, rsa_key):
        run = _Run(service, db)

        run(_token(rsa_key, sid="sid-b", sub="subject-8"))

        assert run.deleted == []

    def test_a_sub_alone_ends_every_live_session_the_user_signed_in_to_through_the_provider(self, service, db, rsa_key):
        run = _Run(service, db, live=("s1", "s2", "s4", "s5", "s6"))

        run(_token(rsa_key, sub="subject-7"))

        assert sorted(run.deleted) == [("s1", 7), ("s2", 7), ("s4", 7), ("s5", 7)]

    @pytest.mark.parametrize("claims", [{"sid": "sid-unknown"}, {"sub": "unlinked"}, {"sid": "sid-a", "sub": "x"}])
    def test_a_token_naming_no_live_session_succeeds_and_ends_nothing(self, service, db, rsa_key, claims):
        run = _Run(service, db)

        with jasil_testing.capture_audit() as audit:
            run(_token(rsa_key, **claims))

        assert run.deleted == []
        audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)

    def test_sessions_that_already_ended_are_not_ended_again(self, service, db, rsa_key):
        run = _Run(service, db, live=())

        with jasil_testing.capture_audit() as audit:
            run(_token(rsa_key, sid="sid-a"))

        assert run.deleted == []
        audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)


class TestSessionsThatVanish:
    def test_a_session_gone_by_the_time_it_is_ended_is_skipped_and_the_audit_counts_the_ended_ones(
        self, service, db, rsa_key
    ):
        run = _Run(service, db, live=("s1", "s3"))

        with jasil_testing.capture_audit() as audit:
            run(_token(rsa_key, sid="sid-a"))

        assert sorted(run.deleted) == [("s1", 7), ("s3", 8)]
        rows = {entry.target_id: entry.details for entry in audit.matching(sessions_audit_actions.SESSION_REVOKE.id)}
        assert rows == {"7": {"sessions_revoked": 1}, "8": {"sessions_revoked": 1}}


class TestFailureWhileEndingSessions:
    def _fail_ending(self, error):
        return patch.object(
            backchannel_logout_service.identity_provider_links_integration, "end_idp_sessions_by_sid", side_effect=error
        )

    def test_the_claim_is_released_and_the_same_token_succeeds_on_retry(self, service, db, rsa_key):
        token = _token(rsa_key, sid="sid-a")
        error = OperationalError("COMMIT", {}, Exception("db down"))

        with self._fail_ending(error), pytest.raises(OperationalError) as raised:
            _Run(service, db)(token)
        run = _Run(service, db)
        run(token)

        assert raised.value is error
        assert sorted(run.deleted) == [("s1", 7), ("s2", 7), ("s3", 8)]

    def test_a_release_that_fails_is_logged_and_the_original_error_is_raised(self, service, state, db, rsa_key):
        error = OperationalError("COMMIT", {}, Exception("db down"))
        broken = MagicMock(wraps=state)
        broken.delete.side_effect = StateBackendUnavailableError("down")
        service = backchannel_logout_service.BackchannelLogoutService(service._oidc, broken)

        with self._fail_ending(error), pytest.raises(OperationalError) as raised:
            _Run(service, db)(_token(rsa_key, sid="sid-a"))

        assert raised.value is error

    def test_a_replay_refusal_releases_nothing(self, service, db, rsa_key):
        token = _token(rsa_key, sid="sid-a")
        _Run(service, db)(token)

        for _ in range(2):
            with pytest.raises(core_exceptions.InvalidInputError):
                _Run(service, db)(token)


class TestAudit:
    def test_one_session_revoke_row_per_user_carries_the_count(self, service, db, rsa_key):
        with jasil_testing.capture_audit() as audit:
            _Run(service, db)(_token(rsa_key, sid="sid-a"))

        rows = {entry.target_id: entry.details for entry in audit.matching(sessions_audit_actions.SESSION_REVOKE.id)}
        assert rows == {"7": {"sessions_revoked": 2}, "8": {"sessions_revoked": 1}}
        entry = audit.assert_audited(sessions_audit_actions.SESSION_REVOKE.id, target_id="7")
        assert (entry.target_type, entry.target_owner_id) == ("user", "7")

    def test_the_sessions_end_in_a_committed_transaction(self, service, rsa_key):
        db = MagicMock()
        ended = {7: 1}
        with patch.object(
            backchannel_logout_service.identity_provider_links_integration,
            "end_idp_sessions_by_sid",
            return_value=ended,
        ) as end:
            _Run(service, db)(_token(rsa_key, sid="sid-a"))

        end.assert_called_once_with(IDP_ID, "sid-a", db, user_id=None)
        assert db.commit.call_count == 2


class TestRefusals:
    def _refused(self, service, db, token, reason):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidInputError):
            _Run(service, db)(token)
        entry = audit.assert_audited(
            idp_audit_actions.BACKCHANNEL_LOGOUT_REFUSE.id,
            outcome="failure",
            target_type="identity_provider",
            target_id=str(IDP_ID),
        )
        assert entry.details == {"idp_id": str(IDP_ID), "reason": reason}
        audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)

    def test_a_token_that_does_not_verify_is_refused_and_audited(self, service, db):
        other = RSAKey.generate_key(2048, parameters={"kid": "k1"})

        self._refused(service, db, _token(other, sid="sid-a"), "invalid_token")

    def test_an_id_token_posted_as_a_logout_token_is_refused(self, service, db, rsa_key):
        self._refused(service, db, _token(rsa_key, sub="subject-7", events=None, nonce="n"), "invalid_token")

    def test_a_replayed_token_is_refused_and_ends_nothing_more(self, service, db, rsa_key):
        token = _token(rsa_key, sid="sid-a")
        _Run(service, db)(token)

        self._refused(service, db, token, "replayed")

    def test_the_same_jti_from_another_provider_is_not_a_replay(self, service, db, rsa_key):
        _Run(service, db, idp=_idp(id=OTHER_IDP_ID))(_token(rsa_key, sid="sid-a"))
        run = _Run(service, db)

        run(_token(rsa_key, sid="sid-b"))

        assert run.deleted == [("s4", 7)]

    def test_the_replay_claim_lasts_until_the_token_can_no_longer_pass_the_expiry_check(self, service, db, rsa_key):
        state = MagicMock()
        state.set_if_absent.return_value = True
        service._state = state
        now = int(time.time())

        _Run(service, db)(_token(rsa_key, sid="sid-a", exp=now + 100))

        ttl = state.set_if_absent.call_args.args[2]
        assert 100 + 60 - 2 <= ttl <= 100 + 60 + 1

    def test_signing_keys_that_cannot_be_read_refuse_the_token(self, service, oidc, db, rsa_key):
        oidc.get_oidc_configuration.return_value = None

        self._refused(service, db, _token(rsa_key, sid="sid-a"), "signing_keys_unavailable")

    def test_a_jwks_endpoint_that_does_not_answer_refuses_the_token(self, service, oidc, db, rsa_key):
        oidc.fetch_jwks.side_effect = oidc_client_service.UpstreamTimeoutError("timeout")

        self._refused(service, db, _token(rsa_key, sid="sid-a"), "signing_keys_unavailable")

    def test_an_unreachable_state_store_fails_closed_without_ending_sessions(self, service, db, rsa_key):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        service._state = state
        run = _Run(service, db)

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.ServiceUnavailableError):
            run(_token(rsa_key, sid="sid-a"))

        assert run.deleted == []
        audit.assert_not_audited(idp_audit_actions.BACKCHANNEL_LOGOUT_REFUSE.id)
