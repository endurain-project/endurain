"""A synced email change is applied, audited and told to the previous address, against a real database."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy.orm import sessionmaker

import modules.auth.identity_providers.user_provisioning_service as provisioning
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.integration_service as users_integration
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import create_sqlite_session, ensure_user

_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"


@pytest.fixture
def db():
    session = create_sqlite_session()
    ensure_user(sessionmaker(bind=session.get_bind()), MOCK_USER_ID)
    yield session
    session.close()


def _idp(**overrides):
    values = {"id": uuid.uuid4(), "name": "Pocket", "user_mapping": None, "sync_user_info": False, "sync_email": True}
    values.update(overrides)
    return MagicMock(**values)


RESET_TOKEN_ID = uuid.uuid4()


def _add_reset_token(db):
    db.add(
        password_reset_models.PasswordResetToken(
            id=RESET_TOKEN_ID,
            user_id=MOCK_USER_ID,
            token_hash="hash",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            used=False,
        )
    )
    db.commit()


def test_a_synced_email_is_applied_audited_and_told_to_the_previous_address(db):
    user = users_integration.get_user(MOCK_USER_ID, db)
    previous = user.email
    _add_reset_token(db)

    with jasil_testing.capture_audit() as audit, patch(_PUBLISH) as publish:
        updated = provisioning.update_user_from_idp(
            user, _idp(), {"email": "New@Example.com", "email_verified": True}, db
        )
        db.commit()

    assert updated.email == "new@example.com"
    assert updated.email_verified is True
    entry = audit.assert_audited(
        users_audit_actions.USER_EMAIL_CHANGE.id, target_type="user", target_id=str(MOCK_USER_ID)
    )
    assert entry.details is None
    notice = db.query(sign_up_models.SignUpToken).filter_by(user_id=MOCK_USER_ID).one()
    assert (notice.previous_email, notice.email, notice.used) == (previous, "new@example.com", True)
    assert publish.call_args.args[0] == "auth.email_changed"
    assert publish.call_args.args[1] == {"user_id": str(MOCK_USER_ID), "token_id": str(notice.id)}
    assert db.get(password_reset_models.PasswordResetToken, RESET_TOKEN_ID).used is True


def test_sync_email_off_keeps_the_email_while_the_name_syncs(db):
    user = users_integration.get_user(MOCK_USER_ID, db)

    with jasil_testing.capture_audit() as audit, patch(_PUBLISH) as publish:
        updated = provisioning.update_user_from_idp(
            user,
            _idp(sync_user_info=True, sync_email=False),
            {"email": "new@example.com", "email_verified": True, "name": "Brand New"},
            db,
        )

    assert (updated.email, updated.name) == (user.email, "Brand New")
    audit.assert_not_audited(users_audit_actions.USER_EMAIL_CHANGE.id)
    publish.assert_not_called()
    assert db.query(sign_up_models.SignUpToken).count() == 0
