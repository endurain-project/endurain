"""A synced email change is applied, audited and told to the previous address, against the real database."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
import pytest
from sqlalchemy import func, select

import modules.auth.identity_providers.contracts as contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.user_provisioning_service as provisioning
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.integration_service as users_integration
from tests._factories.identity_links import make_oidc_provider
from tests._factories.users import make_user


@pytest.fixture
def world(committed_sessions):
    """A user with an unused reset token, a provider that syncs email, and the events the change announces."""
    announced: list[object] = []
    platform_runtime.get_active_platform().events.subscribe("auth.email_changed", announced.append)
    with committed_sessions() as db:
        user = make_user(db, email="before@example.com")
        idp_id = make_oidc_provider(db, "pocket", "https://idp.example.com", sync_user_info=False, sync_email=True)
        db.add(
            password_reset_models.PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash="hash",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                used=False,
            )
        )
        db.commit()
    return user, idp_id, announced, committed_sessions


def _idp(sessions, idp_id):
    with sessions() as db:
        return idp_crud.get_identity_provider(idp_id, db)


def test_a_synced_email_is_applied_audited_and_told_to_the_previous_address(world):
    user, idp_id, announced, sessions = world

    with sessions() as db, jasil_testing.capture_audit() as audit:
        updated = provisioning.update_user_from_idp(
            users_integration.require_user(user.id, db),
            _idp(sessions, idp_id),
            contracts.SyncedClaims(name=None, email="New@Example.com", email_verified=True),
            db,
        )
        db.commit()

    assert updated.email == "new@example.com"
    assert updated.email_verified is True
    entry = audit.assert_audited(users_audit_actions.USER_EMAIL_CHANGE.id, target_type="user", target_id=str(user.id))
    assert entry.details is None
    with sessions() as db:
        notice = db.scalars(select(sign_up_models.SignUpToken).filter_by(user_id=user.id)).one()
        assert (notice.previous_email, notice.email, notice.used) == ("before@example.com", "new@example.com", True)
        assert db.scalars(select(password_reset_models.PasswordResetToken.used)).one() is True
    assert [event.payload for event in announced] == [{"user_id": str(user.id), "token_id": str(notice.id)}]


def test_sync_email_off_keeps_the_email_while_the_name_syncs(world):
    user, idp_id, announced, sessions = world
    idp = _idp(sessions, idp_id).model_copy(update={"sync_user_info": True, "sync_email": False})

    with sessions() as db, jasil_testing.capture_audit() as audit:
        updated = provisioning.update_user_from_idp(
            users_integration.require_user(user.id, db),
            idp,
            contracts.SyncedClaims(name="Brand New", email="new@example.com", email_verified=True),
            db,
        )
        db.commit()

    assert (updated.email, updated.name) == ("before@example.com", "Brand New")
    audit.assert_not_audited(users_audit_actions.USER_EMAIL_CHANGE.id)
    assert announced == []
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(sign_up_models.SignUpToken)) == 0
