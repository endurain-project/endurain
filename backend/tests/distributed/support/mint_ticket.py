"""Act as an API replica: issue a websocket ticket for a user and print it.

Run from the ``app`` directory with the replica's environment. The ticket is written to
the shared state (Redis), so any replica can accept it when the socket connects.
"""

# ruff: noqa: T201 - a process entry point: it extends sys.path before importing, and prints for its parent.

import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, ".")

import jasil.container as container
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry
import module_registry
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
import modules.websocket.ticket_store as websocket_ticket_store
from core.database import SessionLocal

user_id = uuid.UUID(sys.argv[1])
model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(
    core_config.settings, plain_areas=module_registry.storage_plain_areas()
)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)

# A socket needs a live session, so the user and a session for it are stored first.
session_id = f"session-{user_id}"
now = datetime.now(UTC)
with SessionLocal() as db:
    if db.get(users_models.Users, user_id) is None:
        db.add(
            users_models.Users(
                id=user_id,
                name="socket-user",
                username="socket-user",
                email="socket-user@example.com",
                preferred_language="en",
                access_type="regular",
                timezone="UTC",
            )
        )
        # The session's foreign key needs the user row first; the models share no relationship to order the inserts.
        db.flush()
    db.add(
        sessions_models.UsersSessions(
            id=session_id,
            user_id=user_id,
            ip_address="127.0.0.1",
            device_type="PC",
            operating_system="Linux",
            operating_system_version="1",
            browser="Firefox",
            browser_version="1",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
            tokens_exchanged=True,
            token_family_id=session_id,
            rotation_count=0,
            client_type="web",
            auth_time=now,
            amr=["pwd"],
        )
    )
    db.commit()

print(
    f"TICKET {websocket_ticket_store.WsTicketStore(platform.state, platform.clock).create_ticket(user_id, session_id)}"
)

lifecycle.shutdown()
