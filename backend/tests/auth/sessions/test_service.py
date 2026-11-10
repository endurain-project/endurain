"""Tests for session transaction and lifecycle orchestration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.schema as auth_schema
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.service as sessions_service
from modules.auth.constants import ClientType

_STEP_UP = auth_schema.StepUpVerification(current_password="admin-password")
_FIREFOX_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"


def _session(**updates):
    data = {
        "id": "session-id",
        "user_id": 7,
        "refresh_token": "hashed-refresh",
        "ip_address": "127.0.0.1",
        "device_type": "PC",
        "operating_system": "Linux",
        "operating_system_version": "1",
        "browser": "Firefox",
        "browser_version": "1",
        "created_at": datetime.now(UTC),
        "last_activity_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "oauth_state_id": None,
        "tokens_exchanged": False,
        "token_family_id": "family-id",
        "rotation_count": 0,
        "last_rotation_at": None,
        "csrf_token_hash": None,
        "client_type": "web",
        "auth_time": datetime.now(UTC),
        "amr": ["pwd"],
    }
    data.update(updates)
    return sessions_contracts.SessionRead(**data)


def test_create_session_hashes_secrets_and_stages(mock_db):
    user = SimpleNamespace(id=7)
    hasher = MagicMock()
    hasher.hash_password.return_value = "hashed-refresh"
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.create_session", return_value=_session()) as create,
    ):
        result = sessions_service.create_session(
            "session-id",
            user,
            ClientType.MOBILE,
            "127.0.0.1",
            _FIREFOX_UA,
            "plain-refresh",
            hasher,
            datetime.now(UTC) + timedelta(days=1),
            mock_db,
            amr=["pwd", "otp", "mfa"],
        )
    assert result.id == "session-id"
    assert create.call_args.args[0].amr == ["pwd", "otp", "mfa"]
    assert create.call_args.args[0].auth_time == create.call_args.args[0].created_at
    hasher.hash_password.assert_called_once_with("plain-refresh")
    assert create.call_args.args[0].refresh_token == "hashed-refresh"
    assert create.call_args.args[0].ip_address == "127.0.0.1"
    assert create.call_args.args[0].browser == "Firefox"
    assert create.call_args.args[0].device_type == "PC"
    assert create.call_args.args[0].client_type == ClientType.MOBILE
    mock_db.commit.assert_not_called()


def test_create_session_records_the_app_redirect_uri(mock_db):
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.create_session", return_value=_session()) as create,
    ):
        sessions_service.create_session(
            "session-id",
            SimpleNamespace(id=7),
            ClientType.MOBILE,
            "127.0.0.1",
            _FIREFOX_UA,
            None,
            MagicMock(),
            datetime.now(UTC) + timedelta(days=1),
            mock_db,
            amr=["fed"],
            app_redirect_uri="gadgetbridge://auth/sso/callback",
        )
    assert create.call_args.args[0].app_redirect_uri == "gadgetbridge://auth/sso/callback"


def test_a_rotation_keeps_the_app_redirect_uri(mock_db):
    session = _session(app_redirect_uri="gadgetbridge://auth/sso/callback")
    hasher = MagicMock()
    hasher.hash_password.return_value = "replacement-hash"
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.edit_session", return_value=session) as edit,
    ):
        sessions_service.edit_session(
            session, "127.0.0.2", _FIREFOX_UA, "replacement", hasher, datetime.now(UTC) + timedelta(days=1), mock_db
        )
    assert edit.call_args.args[0].app_redirect_uri == "gadgetbridge://auth/sso/callback"


def test_the_session_read_schema_shows_the_app_redirect_uri():
    import modules.auth.sessions.schema as sessions_schema

    read = sessions_schema.UserSessionsRead.model_validate(_session(app_redirect_uri="app:/cb"))

    assert read.app_redirect_uri == "app:/cb"
    assert sessions_schema.UserSessionsRead.model_validate(_session()).app_redirect_uri is None


def test_edit_session_stages_rotation(mock_db):
    session = _session()
    hasher = MagicMock()
    hasher.hash_password.return_value = "replacement-hash"
    with (
        _policy_patch(),
        patch(
            "modules.auth.sessions.service.sessions_crud.edit_session", return_value=_session(rotation_count=1)
        ) as edit,
    ):
        result = sessions_service.edit_session(
            session, "127.0.0.2", _FIREFOX_UA, "replacement", hasher, datetime.now(UTC) + timedelta(days=1), mock_db
        )
    assert result.rotation_count == 1
    assert edit.call_args.args[0].refresh_token == "replacement-hash"
    assert edit.call_args.args[0].rotation_count == 1
    assert edit.call_args.args[0].ip_address == "127.0.0.2"
    mock_db.commit.assert_not_called()


def test_session_with_oauth_state_uses_integration_surface(mock_db):
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.get_session_by_id_not_expired",
            return_value=_session(oauth_state_id="state-id"),
        ),
        patch(
            "modules.auth.sessions.service.oauth_state_integration.get_oauth_state_by_id_not_expired",
            return_value="state",
        ) as get_state,
    ):
        result = sessions_service.get_session_with_oauth_state("session-id", mock_db)
    assert result is not None
    assert result[0].id == "session-id"
    assert result[1] == "state"
    get_state.assert_called_once_with("state-id", mock_db)


def test_claim_token_exchange_cleans_up_oauth_and_stages(mock_db):
    wanted = datetime.now(UTC) + timedelta(days=1)
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.get_session_by_id",
            return_value=_session(oauth_state_id="state-id"),
        ),
        patch(
            "modules.auth.sessions.service.server_settings_integration.get_session_policy",
            return_value=SimpleNamespace(absolute_timeout=timedelta(days=30)),
        ),
        patch("modules.auth.sessions.service.sessions_crud.claim_session_for_token_exchange", return_value=True),
        patch("modules.auth.sessions.service.sessions_crud.clear_oauth_state_reference") as clear_reference,
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
    ):
        assert (
            sessions_service.claim_session_for_token_exchange("session-id", "hashed", wanted, ["fed"], mock_db)
            == wanted
        )
    clear_reference.assert_called_once_with("session-id", mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    mock_db.commit.assert_not_called()


def test_claim_caps_the_new_expiry_at_the_absolute_timeout(mock_db):
    session = _session()
    with (
        patch("modules.auth.sessions.service.sessions_crud.get_session_by_id", return_value=session),
        patch(
            "modules.auth.sessions.service.server_settings_integration.get_session_policy",
            return_value=SimpleNamespace(absolute_timeout=timedelta(hours=2)),
        ),
        patch(
            "modules.auth.sessions.service.sessions_crud.claim_session_for_token_exchange", return_value=True
        ) as claim,
    ):
        expires_at = sessions_service.claim_session_for_token_exchange(
            "session-id", "hashed", session.created_at + timedelta(days=7), ["fed"], mock_db
        )
    assert expires_at == session.created_at + timedelta(hours=2)
    claim.assert_called_once_with("session-id", "hashed", expires_at, ["fed"], mock_db)


def test_claim_lost_race_does_not_commit(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.get_session_by_id", return_value=_session()),
        patch(
            "modules.auth.sessions.service.server_settings_integration.get_session_policy",
            return_value=SimpleNamespace(absolute_timeout=timedelta(days=30)),
        ),
        patch("modules.auth.sessions.service.sessions_crud.claim_session_for_token_exchange", return_value=False),
    ):
        assert (
            sessions_service.claim_session_for_token_exchange("session-id", "hash", datetime.now(UTC), ["fed"], mock_db)
            is None
        )
    mock_db.commit.assert_not_called()


def test_claim_of_a_missing_session_is_refused(mock_db):
    with patch("modules.auth.sessions.service.sessions_crud.get_session_by_id", return_value=None):
        assert (
            sessions_service.claim_session_for_token_exchange("session-id", "hash", datetime.now(UTC), ["fed"], mock_db)
            is None
        )


@pytest.mark.parametrize(("refresh_token", "exchanged"), [("refresh", True), (None, False)])
def test_a_session_created_with_a_refresh_token_needs_no_exchange(refresh_token, exchanged, mock_db):
    hasher = MagicMock()
    hasher.hash_password.return_value = "hashed"
    with (
        patch(
            "modules.auth.sessions.service.server_settings_integration.get_session_policy",
            return_value=SimpleNamespace(absolute_timeout=timedelta(days=30)),
        ),
        patch("modules.auth.sessions.service.sessions_crud.create_session") as create,
    ):
        sessions_service.create_session(
            "session-id",
            SimpleNamespace(id=7),
            ClientType.WEB,
            "127.0.0.1",
            "agent",
            refresh_token,
            hasher,
            datetime.now(UTC) + timedelta(minutes=10),
            mock_db,
            amr=["pwd"],
        )
    assert create.call_args.args[0].tokens_exchanged is exchanged


def test_delete_session_cleans_linked_records_and_commits(mock_db):
    session = _session(oauth_state_id="state-id")
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=session),
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family") as delete_family,
    ):
        sessions_service.delete_session("session-id", 7, _STEP_UP, MagicMock(), mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    delete_family.assert_called_once_with("family-id", mock_db)
    mock_db.commit.assert_called_once()


def test_family_invalidation_stages_session_and_token_deletion(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_family", return_value=2),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family", return_value=4),
    ):
        assert sessions_service.invalidate_token_family("family-id", mock_db) == 2
    mock_db.commit.assert_not_called()


def test_stage_delete_session_cleans_linked_records_without_committing(mock_db):
    session = _session(oauth_state_id="state-id")
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=session),
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family") as delete_family,
    ):
        sessions_service.stage_delete_session("session-id", 7, mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    delete_family.assert_called_once_with("family-id", mock_db)
    mock_db.commit.assert_not_called()


def test_delete_user_sessions_stages_without_committing(mock_db):
    with patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=3):
        assert sessions_service.delete_sessions_by_user(7, mock_db, "current") == 3
    mock_db.commit.assert_not_called()


def test_delete_user_sessions_standalone_commits(mock_db):
    with patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=3):
        assert sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, MagicMock(), mock_db) == 3
    mock_db.commit.assert_called_once()


def test_missing_session_deletion_propagates_domain_not_found(mock_db):
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.delete_session",
            side_effect=core_exceptions.NotFoundError("Session not found"),
        ),
        pytest.raises(core_exceptions.NotFoundError),
    ):
        sessions_service.delete_session("missing", 7, _STEP_UP, MagicMock(), mock_db)
    mock_db.commit.assert_not_called()


def test_list_user_sessions_builds_a_page_from_the_window_and_count(mock_db):
    page = core_pagination.PageParams(2, 1)
    with (
        patch("modules.auth.sessions.service.core_config.settings") as settings,
        patch("modules.auth.sessions.service.sessions_crud.get_user_sessions_page", return_value=[_session()]) as rows,
        patch("modules.auth.sessions.service.sessions_crud.count_user_sessions", return_value=3) as count,
    ):
        settings.ENVIRONMENT = "production"
        result = sessions_service.list_user_sessions(7, page, mock_db)
    rows.assert_called_once_with(7, mock_db, limit=1, offset=1)
    count.assert_called_once_with(7, mock_db)
    assert [item.id for item in result.items] == ["session-id"]
    assert (result.total, result.page, result.next) == (3, 2, 3)
    assert not hasattr(result.items[0], "refresh_token")


def test_list_user_sessions_is_empty_in_demo(mock_db):
    with (
        patch("modules.auth.sessions.service.core_config.settings") as settings,
        patch("modules.auth.sessions.service.sessions_crud.get_user_sessions_page") as rows,
    ):
        settings.ENVIRONMENT = "demo"
        result = sessions_service.list_user_sessions(7, core_pagination.PageParams(1, 25), mock_db)
    rows.assert_not_called()
    assert result.items == [] and result.total == 0


def test_session_logs_carry_a_fingerprint_not_the_session_id(mock_db, caplog):
    with (
        caplog.at_level("INFO"),
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=_session()),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family"),
    ):
        sessions_service.delete_session("secret-session-id", 7, _STEP_UP, MagicMock(), mock_db)
    assert "secret-session-id" not in caplog.text
    assert "secret-session-id" not in str([record.__dict__ for record in caplog.records])


_ABSOLUTE = timedelta(hours=720)


def _hasher():
    hasher = MagicMock()
    hasher.hash_password.return_value = "hashed"
    return hasher


def _policy_patch():
    policy = SimpleNamespace(idle_timeout=None, absolute_timeout=_ABSOLUTE)
    return patch("modules.auth.sessions.service.server_settings_integration.get_session_policy", return_value=policy)


def test_create_session_caps_expiry_at_the_absolute_timeout(mock_db):
    hasher = _hasher()
    before = datetime.now(UTC)
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.create_session", return_value=_session()) as create,
    ):
        sessions_service.create_session(
            "session-id",
            SimpleNamespace(id=7),
            ClientType.WEB,
            "127.0.0.1",
            _FIREFOX_UA,
            "r",
            hasher,
            before + timedelta(days=3650),
            mock_db,
            amr=["pwd"],
        )
    staged = create.call_args.args[0]
    assert staged.expires_at == staged.created_at + _ABSOLUTE


def test_create_session_keeps_an_earlier_expiry(mock_db):
    requested = datetime.now(UTC) + timedelta(days=1)
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.create_session", return_value=_session()) as create,
    ):
        sessions_service.create_session(
            "session-id",
            SimpleNamespace(id=7),
            ClientType.WEB,
            "127.0.0.1",
            _FIREFOX_UA,
            "r",
            _hasher(),
            requested,
            mock_db,
            amr=["pwd"],
        )
    assert create.call_args.args[0].expires_at == requested


def test_edit_session_caps_expiry_at_creation_plus_absolute_timeout(mock_db):
    created = datetime.now(UTC) - timedelta(hours=700)
    session = _session(created_at=created)
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.edit_session", return_value=session) as edit,
    ):
        sessions_service.edit_session(
            session, "127.0.0.2", _FIREFOX_UA, "r", _hasher(), datetime.now(UTC) + timedelta(days=7), mock_db
        )
    assert edit.call_args.args[0].expires_at == created + _ABSOLUTE


def test_edit_session_keeps_an_earlier_expiry(mock_db):
    session = _session(created_at=datetime.now(UTC))
    requested = datetime.now(UTC) + timedelta(days=7)
    with (
        _policy_patch(),
        patch("modules.auth.sessions.service.sessions_crud.edit_session", return_value=session) as edit,
    ):
        sessions_service.edit_session(session, "127.0.0.2", _FIREFOX_UA, "r", _hasher(), requested, mock_db)
    assert edit.call_args.args[0].expires_at == requested


def test_stage_delete_session_announces_the_revoked_session(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=_session()),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family"),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked") as publish,
    ):
        sessions_service.stage_delete_session("sid", 7, mock_db)

    publish.assert_called_once_with(7, mock_db, session_id="sid")


def test_deleting_all_sessions_announces_a_user_wide_revocation(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=2),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked") as publish,
    ):
        sessions_service.delete_sessions_by_user(7, mock_db)

    publish.assert_called_once_with(7, mock_db, except_session_id=None)


def test_deleting_the_other_sessions_names_the_one_kept(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=1),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked") as publish,
    ):
        sessions_service.delete_sessions_by_user_and_commit(
            7, _STEP_UP, MagicMock(), mock_db, exclude_session_id="keep"
        )

    publish.assert_called_once_with(7, mock_db, except_session_id="keep")


def test_family_invalidation_announces_each_revoked_session(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.list_session_owners_by_family", return_value=[(7, "fam")]),
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_family", return_value=1),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family", return_value=0),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked") as publish,
    ):
        sessions_service.invalidate_token_family("fam", mock_db)

    publish.assert_called_once_with(7, mock_db, session_id="fam")


def test_deleting_no_sessions_announces_nothing(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=0),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked") as publish,
    ):
        sessions_service.delete_sessions_by_user(7, mock_db)

    publish.assert_not_called()


class TestCsrfKeyRotation:
    """A CSRF hash stored under the old ``SECRET_KEY`` still verifies once the key list is ``new,old``."""

    @pytest.fixture(autouse=True)
    def _fresh_keys(self):
        import core.key_derivation as core_key_derivation

        core_key_derivation.derive_keys.cache_clear()
        yield
        core_key_derivation.derive_keys.cache_clear()

    @staticmethod
    def _with_secret(secret: str):
        import core.key_derivation as core_key_derivation

        core_key_derivation.derive_keys.cache_clear()
        return patch("core.key_derivation.core_config.read_secret", return_value=secret)

    def test_a_hash_made_under_the_old_key_verifies(self):
        with self._with_secret("o" * 40):
            stored = sessions_service._hash_csrf_token("csrf")
        with self._with_secret(f"{'n' * 40},{'o' * 40}"):
            assert sessions_service.verify_csrf_token("csrf", stored) is True
            assert sessions_service.verify_csrf_token("other", stored) is False

    def test_a_hash_made_under_a_key_that_left_the_list_does_not_verify(self):
        with self._with_secret("o" * 40):
            stored = sessions_service._hash_csrf_token("csrf")
        with self._with_secret("n" * 40):
            assert sessions_service.verify_csrf_token("csrf", stored) is False

    def test_new_hashes_use_the_first_key(self):
        with self._with_secret(f"{'n' * 40},{'o' * 40}"):
            stored = sessions_service._hash_csrf_token("csrf")
        with self._with_secret("n" * 40):
            assert sessions_service.verify_csrf_token("csrf", stored) is True


def _refusing() -> MagicMock:
    return MagicMock(side_effect=core_exceptions.StepUpFailedError())


def test_deleting_one_session_verifies_the_revoke_step_up_before_deleting(mock_db):
    verifier = MagicMock()
    order = MagicMock()
    order.attach_mock(verifier, "step_up")
    with patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=_session()) as delete:
        order.attach_mock(delete, "delete")
        with patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family"):
            sessions_service.delete_session("session-id", 7, _STEP_UP, verifier, mock_db)

    assert [call[0] for call in order.mock_calls][:2] == ["step_up", "delete"]
    verifier.assert_called_once_with(_STEP_UP)


def test_a_refused_step_up_deletes_no_session(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session") as delete,
        pytest.raises(core_exceptions.StepUpFailedError),
    ):
        sessions_service.delete_session("session-id", 7, _STEP_UP, _refusing(), mock_db)

    delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_deleting_all_sessions_verifies_the_revoke_step_up_before_deleting(mock_db):
    verifier = MagicMock()
    with patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=0):
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, verifier, mock_db)

    verifier.assert_called_once_with(_STEP_UP)


def test_a_refused_step_up_deletes_no_sessions(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user") as delete,
        pytest.raises(core_exceptions.StepUpFailedError),
    ):
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, _refusing(), mock_db)

    delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_an_administrator_revoking_all_sessions_bumps_before_the_commit(mock_db):
    order = MagicMock()
    order.attach_mock(mock_db.commit, "commit")
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=2) as delete,
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"),
        patch("modules.auth.sessions.service.security_generation_integration.stage_bump") as bump,
    ):
        order.attach_mock(bump, "bump")
        order.attach_mock(delete, "delete_sessions")
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, MagicMock(), mock_db)

    bump.assert_called_once_with(7, mock_db)
    assert [call[0] for call in order.mock_calls] == ["bump", "delete_sessions", "commit"]


def test_an_administrator_revoking_all_sessions_bumps_when_none_were_open(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=0),
        patch("modules.auth.sessions.service.security_generation_integration.stage_bump") as bump,
    ):
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, MagicMock(), mock_db)

    bump.assert_called_once_with(7, mock_db)


def test_revoking_all_but_one_session_does_not_bump(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=1),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"),
        patch("modules.auth.sessions.service.security_generation_integration.stage_bump") as bump,
    ):
        sessions_service.delete_sessions_by_user_and_commit(
            7, _STEP_UP, MagicMock(), mock_db, exclude_session_id="keep"
        )

    bump.assert_not_called()


def test_a_refused_step_up_does_not_bump(mock_db):
    with (
        patch("modules.auth.sessions.service.security_generation_integration.stage_bump") as bump,
        pytest.raises(core_exceptions.StepUpFailedError),
    ):
        sessions_service.delete_sessions_by_user_and_commit(7, _STEP_UP, _refusing(), mock_db)

    bump.assert_not_called()


def test_revoking_one_session_does_not_bump(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=_session()),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family"),
        patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"),
        patch("modules.auth.sessions.service.security_generation_integration.stage_bump") as bump,
    ):
        sessions_service.stage_delete_session("sid", 7, mock_db)

    bump.assert_not_called()


class TestBulkDeleteRemovesOAuthStates:
    """A bulk session delete also removes the OAuth state rows of the deleted sessions, and only those."""

    @staticmethod
    def _seed(db):
        import modules.auth.oauth_state.constants as oauth_state_constants
        import modules.auth.oauth_state.models as oauth_state_models
        import modules.auth.sessions.models as sessions_models

        now = datetime.now(UTC)
        for user_id, session_id, state_id in (
            (7, "s-kept", "st-kept"),
            (7, "s-gone", "st-gone"),
            (8, "s-other", "st-other"),
        ):
            db.add(
                oauth_state_models.OAuthState(
                    id=state_id,
                    nonce="n" * 32,
                    client_type="web",
                    purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
                    expires_at=now + timedelta(minutes=5),
                )
            )
            db.add(
                sessions_models.UsersSessions(
                    id=session_id,
                    user_id=user_id,
                    refresh_token="hash",
                    ip_address="127.0.0.1",
                    device_type="PC",
                    operating_system="Linux",
                    operating_system_version="1",
                    browser="Firefox",
                    browser_version="1",
                    created_at=now,
                    last_activity_at=now,
                    expires_at=now + timedelta(days=1),
                    tokens_exchanged=True,
                    token_family_id=session_id,
                    rotation_count=0,
                    client_type="web",
                    auth_time=now,
                    amr=["pwd"],
                    oauth_state_id=state_id,
                )
            )
        db.commit()

    @staticmethod
    def _state_ids(db):
        import modules.auth.oauth_state.models as oauth_state_models

        return set(db.execute(sa.select(oauth_state_models.OAuthState.id)).scalars())

    def test_it_removes_the_states_of_the_deleted_sessions_only(self):
        from tests._helpers.db import create_sqlite_session

        db = create_sqlite_session()
        self._seed(db)
        with patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"):
            assert sessions_service.delete_sessions_by_user(7, db) == 2
        db.commit()

        assert self._state_ids(db) == {"st-other"}
        db.close()

    def test_it_keeps_the_state_of_the_excluded_session(self):
        from tests._helpers.db import create_sqlite_session

        db = create_sqlite_session()
        self._seed(db)
        with patch("modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"):
            assert sessions_service.delete_sessions_by_user(7, db, "s-kept") == 1
        db.commit()

        assert self._state_ids(db) == {"st-kept", "st-other"}
        db.close()


class TestStaleSessionPurge:
    """A session ended by the cleanup jobs is announced like any other revoked session."""

    _PUBLISH = "modules.auth.sessions.service.sessions_event_publishers.publish_sessions_revoked"

    def test_the_expired_purge_announces_each_ended_session_and_commits_each_batch(self):
        db = MagicMock()
        batches = [[(7, f"s{i}") for i in range(sessions_service.core_database.PURGE_BATCH_SIZE)], [(8, "last")]]
        with (
            patch("modules.auth.sessions.service.sessions_crud.delete_expired_sessions", side_effect=batches) as crud,
            patch(self._PUBLISH) as publish,
        ):
            total = sessions_service.delete_expired_sessions(db)

        assert total == sessions_service.core_database.PURGE_BATCH_SIZE + 1
        assert crud.call_count == 2
        assert db.commit.call_count == 2
        assert publish.call_count == total
        assert publish.call_args_list[-1].args == (8, db)
        assert publish.call_args_list[-1].kwargs == {"session_id": "last"}

    def test_the_idle_purge_announces_each_ended_session(self):
        db = MagicMock()
        policy = MagicMock(idle_timeout=timedelta(hours=1))
        with (
            patch("modules.auth.sessions.service.server_settings_integration.get_session_policy", return_value=policy),
            patch(
                "modules.auth.sessions.service.sessions_crud.delete_idle_sessions", return_value=[(7, "a"), (9, "b")]
            ),
            patch(self._PUBLISH) as publish,
        ):
            assert sessions_service.delete_idle_sessions(db) == 2

        assert [(c.args[0], c.kwargs["session_id"]) for c in publish.call_args_list] == [(7, "a"), (9, "b")]

    def test_no_idle_timeout_ends_nothing_and_announces_nothing(self):
        policy = MagicMock(idle_timeout=None)
        with (
            patch("modules.auth.sessions.service.server_settings_integration.get_session_policy", return_value=policy),
            patch("modules.auth.sessions.service.sessions_crud.delete_idle_sessions") as crud,
            patch(self._PUBLISH) as publish,
        ):
            assert sessions_service.delete_idle_sessions(MagicMock()) == 0

        crud.assert_not_called()
        publish.assert_not_called()
