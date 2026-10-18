"""Act as an API replica: one user requests to follow another and the target accepts.

Run from the ``app`` directory with the replica's environment. It builds the same
platform the API does, then calls the real follow service, so the events are
queued through the transactional outbox exactly as a request would queue them.
"""

# ruff: noqa: E402 - a process entry point: it extends sys.path before importing.

import sys

sys.path.insert(0, ".")

import jasil.container as container
import jasil.jobs.registry as jobs_registry
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry
import module_registry

model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(core_config.settings)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)
# Without a registered durable subscriber the publisher falls back to the in-process bus.
module_registry.register_durable_handlers(jobs_registry.registry)

import modules.followers.service as followers_service
import modules.users.users.models as users_models
from core.database import SessionLocal

with SessionLocal() as db:
    users = []
    for username in ("follower-user", "followee-user"):
        user = users_models.Users(
            name=username,
            username=username,
            email=f"{username}@example.com",
            preferred_language="en",
            access_type="regular",
            timezone="UTC",
        )
        db.add(user)
        users.append(user)
    db.commit()
    follower_id, followee_id = users[0].id, users[1].id

with SessionLocal() as db:
    followers_service.follow_user(follower_id, followee_id, db)
with SessionLocal() as db:
    followers_service.accept_follow_request(followee_id, follower_id, db)

lifecycle.shutdown()
