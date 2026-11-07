"""An unverified self sign-up is removed once its verification link has expired, and nothing else is."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.credentials.models as credentials_models
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session

_OLD = datetime.now(UTC) - sign_up_service.SIGN_UP_TOKEN_TTL - timedelta(hours=1)
_RECENT = datetime.now(UTC) - sign_up_service.SIGN_UP_TOKEN_TTL + timedelta(hours=1)


@pytest.fixture
def erasers():
    erasers = MagicMock()
    with patch("modules.users.users.deletion_job_service.users_contributor_registry.erasers", return_value=erasers):
        yield erasers


@pytest.fixture
def db(erasers):
    session = create_sqlite_session()
    yield session
    session.close()


def _user(db: Session, user_id: int, **overrides) -> int:
    fields = {
        "id": user_id,
        "name": f"User {user_id}",
        "username": f"user{user_id}",
        "email": f"user{user_id}@example.com",
        "preferred_language": "en",
        "access_type": "regular",
        "active": False,
        "email_verified": False,
        "created_at": _OLD,
    } | overrides
    db.add(users_models.Users(**fields))
    db.commit()
    return user_id


def _credential(db: Session, user_id: int) -> None:
    db.add(credentials_models.LocalCredential(user_id=user_id, password_hash="hash"))
    db.commit()


def _link(db: Session, user_id: int) -> None:
    db.add(identity_link_models.IdentityLink(user_id=user_id, idp_id=1, idp_subject=f"sub{user_id}"))
    db.commit()


def _token(db: Session, user_id: int, *, used: bool = False, expires_in: timedelta = timedelta(hours=1)) -> None:
    now = datetime.now(UTC)
    db.add(
        sign_up_models.SignUpToken(
            id=f"token-{user_id}-{used}-{expires_in}",
            user_id=user_id,
            token_hash=f"hash-{user_id}-{used}-{expires_in}",
            created_at=now,
            expires_at=now + expires_in,
            used=used,
            email=f"user{user_id}@example.com",
        )
    )
    db.commit()


def _remaining(db: Session) -> set[int]:
    db.expire_all()
    return {user.id for user in db.query(users_models.Users).all()}


def test_an_old_unverified_sign_up_without_a_password_or_a_provider_is_deleted(db, erasers):
    _user(db, 1)

    with jasil_testing.capture_audit() as audit:
        assert sign_up_service.purge_unverified_sign_ups(db) == 1

    assert _remaining(db) == set()
    entry = audit.assert_audited(
        users_audit_actions.USER_PURGE.id, target_type="user", target_id="1", target_owner_id="1"
    )
    assert entry.details is None or entry.details == {}
    erasers.delete_notifications.assert_called_once_with(1, db)


def test_an_expired_or_used_token_does_not_keep_the_account(db):
    _user(db, 1)
    _user(db, 2)
    _token(db, 1, expires_in=-timedelta(hours=1))
    _token(db, 2, used=True)

    assert sign_up_service.purge_unverified_sign_ups(db) == 2
    assert _remaining(db) == set()


@pytest.mark.parametrize(
    ("overrides", "setup"),
    [
        pytest.param({"created_at": _RECENT}, None, id="younger-than-the-link-lifetime"),
        pytest.param({"email_verified": True}, None, id="verified"),
        pytest.param({"active": True}, None, id="active"),
        pytest.param({"pending_admin_approval": True}, _credential, id="approval-only-with-password"),
        pytest.param({}, _credential, id="admin-created-inactive-with-password"),
        pytest.param({"deactivated_at": _OLD}, None, id="deactivated"),
        pytest.param({"deletion_requested_at": _OLD}, None, id="deletion-requested"),
        pytest.param({}, _link, id="sso-linked"),
        pytest.param({}, _token, id="live-resend-token"),
    ],
)
def test_an_account_that_is_not_an_expired_unverified_sign_up_is_kept(db, erasers, overrides, setup):
    _user(db, 1, **overrides)
    if setup is not None:
        setup(db, 1)

    assert sign_up_service.purge_unverified_sign_ups(db) == 0
    assert _remaining(db) == {1}
    erasers.delete_notifications.assert_not_called()


def test_only_the_purgeable_accounts_go_when_they_are_mixed_with_kept_ones(db):
    _user(db, 1)
    _user(db, 2)
    _credential(db, 2)
    _user(db, 3)
    _user(db, 4, created_at=_RECENT)

    assert sign_up_service.purge_unverified_sign_ups(db) == 2
    assert _remaining(db) == {2, 4}


def test_a_purge_audits_each_account_and_never_a_kept_one(db):
    for user_id in (1, 2, 3):
        _user(db, user_id)
    _credential(db, 3)

    with jasil_testing.capture_audit() as audit:
        sign_up_service.purge_unverified_sign_ups(db)

    purged = audit.matching(users_audit_actions.USER_PURGE.id)
    assert sorted(entry.target_id for entry in purged) == ["1", "2"]


def test_it_deletes_in_bounded_batches(db):
    for user_id in range(1, 6):
        _user(db, user_id)

    with patch.object(core_database, "PURGE_BATCH_SIZE", 2):
        assert sign_up_service.purge_unverified_sign_ups(db) == 5
    assert _remaining(db) == set()


def test_a_verification_that_commits_after_the_candidates_are_read_keeps_its_account(db):
    """The lock query is followed by a re-read of the exclusions, so a credential added in between wins."""
    _user(db, 1)
    real_execute = db.execute
    calls = {"count": 0}

    def execute(stmt, *args, **kwargs):
        result = real_execute(stmt, *args, **kwargs)
        calls["count"] += 1
        if calls["count"] == 1:
            _credential(db, 1)
        return result

    with patch.object(db, "execute", side_effect=execute):
        assert sign_up_service.purge_unverified_sign_ups(db) == 0
    assert _remaining(db) == {1}


def test_a_resend_keeps_the_account_before_any_subscriber_issues_the_mailed_token(db):
    """The resend stages a live token in its own transaction, so a queued mail cannot cost the account."""
    from jasil.backends.state_memory import MemoryState

    _user(db, 1)
    server_settings = MagicMock(signup_require_email_verification=True)
    with (
        patch.object(sign_up_service.server_settings_integration, "get_server_settings", return_value=server_settings),
        patch.object(sign_up_service.server_settings_integration, "is_mail_configured", return_value=True),
        patch.object(sign_up_service.sign_up_event_publishers, "publish_sign_up_verification_requested"),
    ):
        sign_up_service.resend_sign_up_verification_email("user1@example.com", MemoryState(), db)

    assert sign_up_service.purge_unverified_sign_ups(db) == 0
    assert _remaining(db) == {1}
    # The delivery subscriber's token replaces the staged one; the account still has exactly one live link.
    sign_up_service.create_sign_up_token(1, "user1@example.com", "event-1", db)
    live = db.query(sign_up_models.SignUpToken).filter_by(user_id=1, used=False).count()
    assert live == 1
