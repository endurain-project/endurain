"""Act as an API replica: accept N GPX uploads and print their job ids.

Run from the ``app`` directory with the replica's environment. It builds the same
platform the API does, then calls the real ``accept_upload`` for each file, so the
upload is staged in storage and queued through the transactional outbox exactly as
a request would queue it.
"""

# ruff: noqa: E402, T201 - a process entry point: it extends sys.path before importing, and prints for its parent.

import json
import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, ".")

import jasil.container as container
import jasil.jobs.registry as jobs_registry
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings
import sqlalchemy as sa

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry
import module_registry

model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(core_config.settings)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)
module_registry.configure_activity_contributors()
# Without a registered durable subscriber the publisher falls back to the in-process bus.
module_registry.register_durable_handlers(jobs_registry.registry)

import modules.activities.activity_ingestion.service as ingestion_service
import modules.users.users.models as users_models
import modules.users.users_default_gear.crud as default_gear_crud
import modules.users.users_integrations.crud as integrations_crud
import modules.users.users_privacy_settings.crud as privacy_crud
from core.database import SessionLocal

count, tag = int(sys.argv[1]), sys.argv[2]

with SessionLocal() as db:
    user = db.scalars(sa.select(users_models.Users).where(users_models.Users.username == "upload-user")).first()
    if user is None:
        user = users_models.Users(
            name="Upload User",
            username="upload-user",
            email="upload-user@example.com",
            preferred_language="en",
            access_type="regular",
            timezone="UTC",
        )
        db.add(user)
        db.commit()
        privacy_crud.create_user_privacy_settings(user.id, db)
        integrations_crud.create_user_integrations(user.id, db)
        default_gear_crud.create_user_default_gear(user.id, db)
    user_id = user.id


def gpx(index: int) -> str:
    """A small, valid track whose start time is unique to ``tag`` and ``index``."""
    offset = sum(ord(char) for char in tag) % 300
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC) + timedelta(days=offset + index)
    points = "".join(
        f'<trkpt lat="{38.70 + step * 0.0005:.6f}" lon="{-9.14 + step * 0.0005:.6f}"><ele>{20 + step}</ele>'
        f"<time>{(start + timedelta(seconds=30 * step)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time></trkpt>"
        for step in range(40)
    )
    return (
        '<?xml version="1.0"?><gpx version="1.1" creator="tests" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>{tag}-{index}</name><trkseg>{points}</trkseg></trk></gpx>"
    )


job_ids = []
for index in range(count):

    def save_upload(*, kind, upload_dir, filename, _index=index):
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, filename)
        with open(path, "w") as handle:
            handle.write(gpx(_index))
        return path

    with SessionLocal() as db:
        job = ingestion_service.accept_upload(
            user_id, f"{tag}_{index}.gpx", save_upload, platform.storage, db, idempotency_key=f"{tag}-{index}"
        )
        job_ids.append(job.id)

print("JOBS " + json.dumps(job_ids))
lifecycle.shutdown()
