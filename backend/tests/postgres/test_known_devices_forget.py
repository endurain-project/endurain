"""Forgetting known devices across security generations, against real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import text

import core.hashing as core_hashing
import modules.auth.constants as auth_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.service as known_devices_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user

_PUBLISH_REVOKED = "modules.auth.sessions.event_publishers.platform_publisher.publish_on_commit"
_DESCRIPTION = known_devices_contracts.DeviceDescription(browser="Firefox", operating_system="Linux", device_type="PC")
_KEPT, _FORGOTTEN = "k" * 43, "f" * 43


def _register(db, device_id, generation):
    known_devices_crud.create_device(
        MOCK_USER_ID, core_hashing.sha256_hex(device_id), generation, datetime.now(UTC), _DESCRIPTION, db
    )


def _add_session(db, device_id):
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    db.add(
        sessions_models.UsersSessions(
            id=session_id,
            user_id=MOCK_USER_ID,
            ip_address="127.0.0.1",
            device_type="desktop",
            operating_system="linux",
            operating_system_version="1",
            browser="firefox",
            browser_version="1",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=1),
            token_family_id=session_id,
            client_type=auth_constants.ClientType.WEB,
            auth_time=now,
            amr=["pwd"],
            device_hash=core_hashing.sha256_hex(device_id),
        )
    )
    db.flush()
    return session_id


def _seed(pg_factory):
    """Register two devices with a session each, then advance the generation; return both session ids."""
    ensure_user(pg_factory, MOCK_USER_ID)
    with pg_factory() as db:
        _register(db, _KEPT, 0)
        _register(db, _FORGOTTEN, 0)
        kept, forgotten = _add_session(db, _KEPT), _add_session(db, _FORGOTTEN)
        security_generation_integration.stage_bump(MOCK_USER_ID, db)
        db.commit()
    return kept, forgotten


def _remaining(pg_factory):
    with pg_factory() as db:
        sessions = set(db.execute(text("SELECT id FROM users_sessions")).scalars())
        devices = set(db.execute(text("SELECT device_hash FROM auth_known_devices")).scalars())
    return sessions, devices


def test_forgetting_the_other_devices_after_a_generation_bump_ends_the_sessions_of_the_old_generation(pg_factory):
    kept, _ = _seed(pg_factory)
    with pg_factory() as db, patch(_PUBLISH_REVOKED):
        assert known_devices_service.forget_other_devices(MOCK_USER_ID, _KEPT, db) == 1
        db.commit()
    assert _remaining(pg_factory) == ({kept}, {core_hashing.sha256_hex(_KEPT)})


def test_forgetting_all_devices_after_a_generation_bump_ends_every_session(pg_factory):
    _seed(pg_factory)
    with pg_factory() as db, patch(_PUBLISH_REVOKED):
        assert known_devices_service.forget_other_devices(MOCK_USER_ID, None, db) == 2
        db.commit()
    assert _remaining(pg_factory) == (set(), set())
