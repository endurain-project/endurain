"""Concurrent uploads of one user at the open-upload cap, against real PostgreSQL.

Each request counts the user's open uploads and then inserts its job. Without the per-user lock, two requests
at the boundary both count one slot free and both insert, so the cap is only met under one connection.
"""

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.service as ingestion_service
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user

_CAP = ingestion_constants.MAX_OPEN_UPLOADS_PER_USER
_UPLOAD = ingestion_constants.IngestionJobKind.UPLOAD


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    return pg_factory


def _open_count(factory) -> int:
    with factory() as db:
        return ingestion_crud.count_open_uploads(MOCK_USER_ID, db)


def _fill(factory, count: int) -> None:
    with factory() as db:
        for _ in range(count):
            ingestion_crud.create_ingestion_job(
                uuid.uuid4(), MOCK_USER_ID, _UPLOAD, db, filename="ride.gpx", staged_key="abc.gpx"
            )
        db.commit()


def _race_uploads(factory, count: int) -> list:
    barrier = threading.Barrier(count)
    outcomes: list = []

    def run() -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(ingestion_service.accept_upload(MOCK_USER_ID, "ride.gpx", MagicMock(), MagicMock(), db))
            except core_exceptions.ConflictError as err:
                outcomes.append(err)

    with (
        patch.object(ingestion_service.core_config.settings, "JOBS_ENABLED", False),
        patch.object(ingestion_service.activity_ingestion_dispatch_service, "require_capacity"),
        patch.object(
            ingestion_service.activity_ingestion_upload_entry_service,
            "receive_upload",
            return_value=upload_entry_service.ReceivedUpload(
                incoming_path="/incoming/x.gpx", storage_key="abc.gpx", fingerprint="h"
            ),
        ),
        patch.object(
            ingestion_service.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
        ),
        patch.object(ingestion_service.activity_ingestion_upload_entry_service, "discard_staged_upload"),
        patch.object(ingestion_service, "run_in_background_or_fail"),
    ):
        threads = [threading.Thread(target=run) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
    return outcomes


def test_two_uploads_racing_for_the_last_slot_admit_only_one(factory):
    _fill(factory, _CAP - 1)

    outcomes = _race_uploads(factory, 2)

    conflicts = [outcome for outcome in outcomes if isinstance(outcome, core_exceptions.ConflictError)]
    assert len(outcomes) == 2
    assert len(conflicts) == 1
    assert _open_count(factory) == _CAP


def test_a_burst_from_one_user_never_exceeds_the_cap(factory):
    outcomes = _race_uploads(factory, _CAP + 5)

    assert len(outcomes) == _CAP + 5
    assert _open_count(factory) == _CAP
