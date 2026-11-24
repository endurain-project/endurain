"""The scheduled prune of devices no sign-in has used for the retention period."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import module_registry as runtime_module_registry
import modules.auth.known_devices.constants as known_devices_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.models as known_devices_models
import modules.auth.known_devices.scheduled_jobs as known_devices_scheduled_jobs
from tests._factories.users import make_user

_DESCRIPTION = known_devices_contracts.DeviceDescription(browser="Firefox", operating_system="Linux", device_type="PC")


def _arrange(committed_sessions) -> None:
    """Store a device seen just inside and one just beyond the retention."""
    now = datetime.now(UTC)
    retention = timedelta(days=known_devices_constants.DEVICE_RETENTION_DAYS)
    with committed_sessions() as db:
        user = make_user(db)
        known_devices_crud.create_device(user.id, "a" * 64, 0, now - retention + timedelta(hours=1), _DESCRIPTION, db)
        known_devices_crud.create_device(user.id, "b" * 64, 0, now - retention - timedelta(hours=1), _DESCRIPTION, db)
        db.commit()


def test_the_job_deletes_the_devices_beyond_the_retention_in_a_session_of_its_own(committed_sessions):
    _arrange(committed_sessions)

    known_devices_scheduled_jobs.delete_unseen_devices()

    with committed_sessions() as db:
        remaining = set(db.scalars(sa.select(known_devices_models.KnownDevice.device_hash)))
    assert remaining == {"a" * 64}


def test_the_prune_runs_daily_under_its_lock_and_is_registered_with_the_runtime():
    (job,) = known_devices_scheduled_jobs.recurring_jobs()
    module = next(module for module in runtime_module_registry.MODULES if module.name == "known_devices")

    assert job.func is known_devices_scheduled_jobs.delete_unseen_devices
    assert job.minutes == 1440
    assert job.lock_name == known_devices_scheduled_jobs.PRUNE_LOCK_NAME
    assert module.recurring_jobs is known_devices_scheduled_jobs.recurring_jobs
