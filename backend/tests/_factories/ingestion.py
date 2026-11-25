"""Activity files, job rows and the in-process pool for tests on the real ingestion stack.

The files are real: a GPX (``tests/_factories/garmin.py``), a TCX and a FIT built here byte by byte, small enough to
parse in milliseconds and valid enough to take the production parsers' whole path.
"""

import io
import os
import struct
import tempfile
import time
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jasil.jobs.models as jobs_models
import jasil.providers as platform_providers
from jasil.events import Event
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

import core.database as core_database
import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.schema as ingestion_schema
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service
import modules.users.users_default_gear.crud as users_default_gear_crud
import modules.users.users_default_gear.schema as users_default_gear_schema
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
from tests._factories.garmin import DEFAULT_ACTIVITY_START

#: Seconds between the Unix epoch and the FIT epoch (1989-12-31 UTC).
_FIT_EPOCH_OFFSET = 631065600

_ENUM, _UINT8, _UINT16, _SINT32, _UINT32, _STRING = 0x00, 0x02, 0x84, 0x85, 0x86, 0x07


def _crc16(data: bytes) -> int:
    """Compute the FIT CRC-16 of a byte string."""
    table = (
        0x0000,
        0xCC01,
        0xD801,
        0x1400,
        0xF001,
        0x3C00,
        0x2800,
        0xE401,
        0xA001,
        0x6C00,
        0x7800,
        0xB401,
        0x5000,
        0x9C01,
        0x8801,
        0x4400,
    )
    crc = 0
    for byte in data:
        for nibble in (byte & 0xF, (byte >> 4) & 0xF):
            crc = (crc >> 4) ^ table[crc & 0xF] ^ table[nibble]
    return crc


def _message(local: int, global_number: int, fields: list[tuple[int, int, int | bytes]]) -> bytes:
    """Build a definition message followed by one data message.

    Args:
        local: The local message type.
        global_number: The FIT global message number.
        fields: ``(field number, base type, value)`` triples; the value is packed to the base type's size, and a
            string value is its bytes.

    Returns:
        The definition and data bytes.
    """
    formats = {_ENUM: ("B", 1), _UINT8: ("B", 1), _UINT16: ("H", 2), _SINT32: ("i", 4), _UINT32: ("I", 4)}
    definition = struct.pack("<BBBHB", 0x40 | local, 0, 0, global_number, len(fields))
    data = bytes([local])
    for number, base_type, value in fields:
        if isinstance(value, bytes):
            terminated = value + b"\x00"
            definition += struct.pack("<BBB", number, len(terminated), base_type)
            data += terminated
            continue
        code, size = formats[base_type]
        definition += struct.pack("<BBB", number, size, base_type)
        data += struct.pack("<" + code, value)
    return definition + data


def _fit_time(moment: datetime) -> int:
    """Convert an instant to FIT seconds."""
    return int(moment.timestamp()) - _FIT_EPOCH_OFFSET


def _semicircles(degrees: float) -> int:
    """Convert degrees to FIT semicircles."""
    return round(degrees * (2**31) / 180)


def fit_file(
    *,
    start: datetime = DEFAULT_ACTIVITY_START,
    points: int = 20,
    manufacturer: int = 1,
    with_session: bool = True,
    with_gps: bool = True,
    activities: int = 1,
    multisport: bool = False,
    exercise_titles: tuple[tuple[str, int, int], ...] = (),
    workout_steps: tuple[int | None, ...] = (),
) -> bytes:
    """Build a small, valid FIT activity file: a running session with a record every 30 seconds.

    Args:
        start: When the first session starts.
        points: How many records each session holds.
        manufacturer: The FIT manufacturer number (1 is Garmin).
        with_session: Whether the file holds the session summaries; a file without them holds no activity.
        with_gps: Whether the records carry a position.
        activities: How many sessions the file holds, an hour apart.
        multisport: Whether the file's activity message names it one multisport activity, whose sessions are legs.
        exercise_titles: ``(step name, exercise category, exercise name)`` of each exercise title the file holds.
        workout_steps: The FIT ``duration_type`` of each planned workout step the file holds, ``None`` for a step
            that does not name one.

    Returns:
        The FIT file's bytes.
    """
    body = _message(
        0,
        0,
        [(0, _ENUM, 4), (1, _UINT16, manufacturer), (2, _UINT16, 3000), (4, _UINT32, _fit_time(start))],
    )
    for step_name, category, name in exercise_titles:
        body += _message(3, 264, [(0, _UINT16, category), (1, _UINT16, name), (2, _STRING, step_name.encode())])
    for index, duration_type in enumerate(workout_steps):
        step_fields: list[tuple[int, int, int | bytes]] = [(254, _UINT16, index)]
        if duration_type is not None:
            step_fields.append((1, _ENUM, duration_type))
        body += _message(3, 27, step_fields)
    for index in range(activities):
        first = start + timedelta(hours=index)
        last = first + timedelta(seconds=30 * (points - 1))
        for step in range(points):
            moment = first + timedelta(seconds=30 * step)
            fields: list[tuple[int, int, int | bytes]] = [(253, _UINT32, _fit_time(moment))]
            if with_gps:
                fields += [
                    (0, _SINT32, _semicircles(38.70 + step * 0.0005)),
                    (1, _SINT32, _semicircles(-9.14 + step * 0.0005)),
                ]
            fields += [(5, _UINT32, step * 4000), (3, _UINT8, 120 + step)]
            body += _message(1, 20, fields)
        elapsed_ms = int((last - first).total_seconds() * 1000)
        if with_session:
            body += _message(
                2,
                18,
                [
                    (253, _UINT32, _fit_time(last)),
                    (2, _UINT32, _fit_time(first)),
                    (7, _UINT32, elapsed_ms),
                    (8, _UINT32, elapsed_ms),
                    (9, _UINT32, (points - 1) * 4000),
                    (5, _ENUM, 1),
                ],
            )
    if multisport:
        body += _message(4, 34, [(253, _UINT32, _fit_time(last)), (1, _UINT16, activities), (2, _ENUM, 1)])
    header = struct.pack("<BBHI4s", 14, 0x20, 2100, len(body), b".FIT")
    header += struct.pack("<H", _crc16(header))
    payload = header + body
    return payload + struct.pack("<H", _crc16(payload))


def long_gpx(*, kilometres: float, start: datetime = DEFAULT_ACTIVITY_START, name: str = "Long Run") -> bytes:
    """Build a GPX track that runs straight north for a distance, a point every 50 metres.

    Args:
        kilometres: How far the track goes.
        start: When the track starts.
        name: The track's name.

    Returns:
        The GPX file's bytes.
    """
    steps = int(kilometres * 20)
    points = "".join(
        f'<trkpt lat="{38.70 + step * 50 / 111_320:.6f}" lon="-9.140000"><ele>20</ele>'
        f"<time>{(start + timedelta(seconds=15 * step)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time></trkpt>"
        for step in range(steps + 1)
    )
    gpx = (
        '<?xml version="1.0"?><gpx version="1.1" creator="long" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>{name}</name><trkseg>{points}</trkseg></trk></gpx>"
    )
    return gpx.encode()


def archive_of(members: dict[str, bytes]) -> bytes:
    """Build a ZIP of named members that is byte-for-byte the same whenever it is built from the same members.

    ``zipfile`` stamps members with the current time, so two archives built a second apart differ, which a test of a
    repeated request with an ``Idempotency-Key`` (it fingerprints the bytes) cannot use.

    Args:
        members: The member names and their bytes.

    Returns:
        The ZIP's bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)
    return buffer.getvalue()


def activity_tcx(*, start: datetime = DEFAULT_ACTIVITY_START, name: str = "Morning Run") -> bytes:
    """Build a small, valid TCX running activity with one lap of track points.

    Args:
        start: When the activity starts.
        name: The activity's id label.

    Returns:
        The TCX file's bytes.
    """
    points = "".join(
        "<Trackpoint>"
        f"<Time>{(start + timedelta(seconds=30 * step)).strftime('%Y-%m-%dT%H:%M:%SZ')}</Time>"
        f"<Position><LatitudeDegrees>{38.70 + step * 0.0005:.6f}</LatitudeDegrees>"
        f"<LongitudeDegrees>{-9.14 + step * 0.0005:.6f}</LongitudeDegrees></Position>"
        f"<AltitudeMeters>{20 + step}</AltitudeMeters><DistanceMeters>{step * 40}</DistanceMeters>"
        f"<HeartRateBpm><Value>{120 + step}</Value></HeartRateBpm>"
        "</Trackpoint>"
        for step in range(20)
    )
    stamp = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    tcx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        f'<Activities><Activity Sport="Running"><Id>{name}</Id>'
        f'<Lap StartTime="{stamp}"><TotalTimeSeconds>570</TotalTimeSeconds><DistanceMeters>760</DistanceMeters>'
        f"<Calories>60</Calories><Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"
    )
    return tcx.encode()


def stage_job(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: ingestion_constants.IngestionJobKind = ingestion_constants.IngestionJobKind.UPLOAD,
    status: str = "pending",
    staged_key: str | None = None,
    updated_at: datetime | None = None,
    created_at: datetime | None = None,
    job_id: uuid.UUID | None = None,
    retry_after: datetime | None = None,
    completed_at: datetime | None = None,
    activity_ids: list[uuid.UUID] | None = None,
    **create_options: object,
) -> ingestion_schema.ActivityIngestionJobRead:
    """Stage an ingestion job in any state through the module's create path (flushed, not committed).

    The job is created pending and then moved to the state a test arranges, with the timestamps it names.

    Args:
        db: Database session.
        user_id: The user who started the job.
        kind: What the job does.
        status: The stored status to leave the job in.
        staged_key: The storage key of the job's staged blob, if it has one.
        updated_at: When the job last changed; now by default.
        created_at: When the request was accepted; now by default.
        job_id: The job's id; a new one by default.
        retry_after: When a deferred job may run again.
        completed_at: When the job finished; the moment of the call for a completed or failed job.
        activity_ids: The activities a completed job created.
        **create_options: Further options of ``create_ingestion_job`` (``provider``, ``import_source``, ...).

    Returns:
        The job as read back.
    """
    job_id = job_id or uuid.uuid4()
    ingestion_crud.create_ingestion_job(job_id, user_id, kind, db, staged_key=staged_key, **create_options)
    values: dict[str, object] = {"status": status, "retry_after": retry_after}
    if updated_at is not None:
        values["updated_at"] = updated_at
    if created_at is not None:
        values["created_at"] = created_at
        values.setdefault("updated_at", created_at)
    if status in ("completed", "failed"):
        values["completed_at"] = completed_at or datetime.now(UTC)
        values["staged_key"] = None
    if activity_ids is not None:
        values["activity_ids"] = [str(activity_id) for activity_id in activity_ids]
    db.execute(
        update(ingestion_models.ActivityIngestionJob)
        .where(ingestion_models.ActivityIngestionJob.id == job_id)
        .values(**values)
    )
    db.flush()
    read = ingestion_crud.get_ingestion_job(job_id, user_id, db)
    assert read is not None
    return read


def staged_keys(storage: platform_providers.StorageProvider) -> list[str]:
    """List the staged upload and archive blobs held in storage, as the keys jobs name them by.

    Args:
        storage: The platform storage.

    Returns:
        The staged keys, sorted.
    """
    prefix = upload_entry_service.UPLOAD_STAGING_KEY_PREFIX
    area = upload_entry_service.UPLOAD_STAGING_STORAGE_AREA
    return sorted(key.removeprefix(prefix) for key, _modified in storage.iter_objects(area, prefix))


def read_job(sessions: sessionmaker[Session], job_id: uuid.UUID) -> ingestion_models.ActivityIngestionJob:
    """Read a job row back through a new session, so only committed state is seen.

    Args:
        sessions: The application's session factory.
        job_id: The job.

    Returns:
        The row, detached.
    """
    with sessions() as db:
        row = db.get(ingestion_models.ActivityIngestionJob, job_id)
        assert row is not None, "the job does not exist"
        db.expunge(row)
        return row


def find_job(sessions: sessionmaker[Session], job_id: uuid.UUID) -> ingestion_models.ActivityIngestionJob | None:
    """Read a job row back through a new session, or ``None`` when it does not exist.

    Args:
        sessions: The application's session factory.
        job_id: The job.

    Returns:
        The row, detached, or ``None``.
    """
    with sessions() as db:
        row = db.get(ingestion_models.ActivityIngestionJob, job_id)
        if row is not None:
            db.expunge(row)
        return row


def all_jobs(sessions: sessionmaker[Session]) -> list[ingestion_models.ActivityIngestionJob]:
    """List every job row, oldest first, read through a new session.

    Args:
        sessions: The application's session factory.

    Returns:
        The rows, detached.
    """
    with sessions() as db:
        rows = list(
            db.scalars(
                select(ingestion_models.ActivityIngestionJob).order_by(ingestion_models.ActivityIngestionJob.created_at)
            )
        )
        db.expunge_all()
        return rows


def activities_of(sessions: sessionmaker[Session], user_id: uuid.UUID) -> list[activity_models.Activity]:
    """List a user's stored activities, oldest first, read through a new session.

    Args:
        sessions: The application's session factory.
        user_id: The owner.

    Returns:
        The rows, detached.
    """
    with sessions() as db:
        rows = list(
            db.scalars(
                select(activity_models.Activity)
                .where(activity_models.Activity.user_id == user_id)
                .order_by(activity_models.Activity.start_time)
            )
        )
        db.expunge_all()
        return rows


def queued_events(sessions: sessionmaker[Session]) -> list[Event]:
    """List the events staged in the outbox for a durable worker, oldest first.

    Args:
        sessions: The application's session factory.

    Returns:
        The events as a worker receives them on their first attempt.
    """
    with sessions() as db:
        rows = list(db.scalars(select(jobs_models.EventOutbox).order_by(jobs_models.EventOutbox.created_at)))
        return [
            Event(
                event_id=row.event_id,
                event_type=row.event_type,
                source=row.source,
                timestamp=row.timestamp,
                payload=row.payload,
                retry_count=1,
                max_attempts=3,
            )
            for row in rows
        ]


class StubProvider:
    """A third-party activity provider registered with ingestion, holding the files it will hand over.

    Its fetch stores each file of the user through the real pipeline (:func:`ingest_activity_file`), as a provider
    does, and can be made to fail or to be rate limited.

    Attributes:
        name: The provider's name.
        files: The activity files each linked user has, by user id.
        failure: When set, every fetch raises it.
        on_fetch: When set, called at the start of every fetch, to observe the process from inside the provider call.
        calls: ``(user id, window start, window end)`` of every fetch.
        linked: The ids of the users who linked the provider.
    """

    def __init__(self, name: str = "stub") -> None:
        """Build a provider nobody has linked.

        Args:
            name: The provider's name.
        """
        self.name = name
        self.files: dict[uuid.UUID, list[bytes]] = {}
        self.failure: Exception | None = None
        self.on_fetch: Callable[[], None] | None = None
        self.calls: list[tuple[uuid.UUID, datetime, datetime]] = []
        self.linked: list[uuid.UUID] = []

    def link(self, user_id: uuid.UUID, *files: bytes) -> None:
        """Link a user, with the activity files the provider will hand over for them.

        Args:
            user_id: The user.
            *files: GPX files, each stored as one activity on a fetch.
        """
        self.linked = sorted({*self.linked, user_id})
        self.files[user_id] = list(files)

    def fetch_window(self, user_id: uuid.UUID, start: datetime, end: datetime) -> list:
        """Store the user's files through the pipeline and return what was stored.

        Args:
            user_id: The user whose window it is.
            start: Start of the window.
            end: End of the window.

        Returns:
            The stored activities.

        Raises:
            Exception: ``failure``, when set.
        """
        self.calls.append((user_id, start, end))
        if self.on_fetch is not None:
            self.on_fetch()
        if self.failure is not None:
            raise self.failure
        stored: list = []
        for index, content in enumerate(self.files.get(user_id, [])):
            with tempfile.TemporaryDirectory(prefix="stub-provider-") as directory:
                path = os.path.join(directory, f"{index}.gpx")
                with open(path, "wb") as handle:
                    handle.write(content)
                with core_database.SessionLocal() as db:
                    stored.extend(
                        ingestion_integration.ingest_activity_file(
                            user_id, path, db, source=ingestion_integration.UploadSource()
                        )
                        or []
                    )
        return stored

    def linked_user_ids(self, after_id: uuid.UUID | None, limit: int) -> list[uuid.UUID]:
        """Page through the linked users in ascending order.

        Args:
            after_id: Only users greater than this id, or ``None`` from the start.
            limit: The most ids to return.

        Returns:
            The ids.
        """
        return [user_id for user_id in self.linked if after_id is None or user_id > after_id][:limit]

    def register(self) -> StubProvider:
        """Register the provider with ingestion, as a provider module does at startup.

        Returns:
            The provider.
        """
        ingestion_integration.register_activity_provider(self.name, self.fetch_window, self.linked_user_ids)
        return self


def set_privacy_defaults(db: Session, user_id: uuid.UUID, **fields: object) -> None:
    """Change a user's activity privacy defaults through the module's edit path (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user.
        **fields: Fields of the privacy settings update, such as ``hide_activity_location=True``.
    """
    users_privacy_settings_integration.edit_privacy_settings(
        user_id, users_privacy_settings_schema.UserPrivacySettingsUpdate.model_validate(fields), db, if_match="*"
    )


def set_default_gear(db: Session, user_id: uuid.UUID, **fields: uuid.UUID | None) -> None:
    """Change a user's default gear per activity type through the module's edit path (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user.
        **fields: Fields of the default gear update, such as ``run_gear_id=gear.id``.
    """
    users_default_gear_crud.edit_user_default_gear(
        users_default_gear_schema.UserDefaultGearUpdate.model_validate(fields), user_id, db, if_match="*"
    )


def stage_blob(storage: platform_providers.StorageProvider, key: str, content: bytes) -> None:
    """Store a staged upload or archive under the key a job names it by.

    Args:
        storage: The platform storage.
        key: The staged key, as a job row holds it.
        content: The blob's bytes.
    """
    storage.save(
        upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, upload_entry_service.upload_staging_storage_key(key), content
    )


def age_stored_objects(root: Path, seconds: float) -> None:
    """Make every object a local storage holds look as if it was written ``seconds`` ago.

    Args:
        root: The directory the platform's local storage is rooted at.
        seconds: How much older to make each object.
    """
    stamp = time.time() - seconds
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (stamp, stamp))


class ConnectionProbe:
    """A storage provider that records how many other database sessions sit inside a transaction at each call.

    A session held open across a storage round trip would pin a pooled connection while object storage answers, which
    no job may do. The probe reads ``pg_stat_activity`` on an autocommit connection, which snapshots per statement.

    Attributes:
        inner: The real provider the calls fall through to.
        open_during_calls: The count of other sessions in a transaction, one entry per probed call.
    """

    def __init__(self, inner: platform_providers.StorageProvider, methods: tuple[str, ...]) -> None:
        """Wrap a provider.

        Args:
            inner: The real provider.
            methods: The methods whose calls are probed.
        """
        self.inner = inner
        self._methods = methods
        self.open_during_calls: list[int] = []

    def open_sessions(self) -> int:
        """Count the other database sessions that sit inside a transaction right now.

        Returns:
            The count.
        """
        with core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            return connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    " AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"
                )
            ).scalar_one()

    def __getattr__(self, name: str):
        """Return the provider's attribute, probing the methods this wrapper watches."""
        attribute = getattr(self.inner, name)
        if name not in self._methods:
            return attribute

        def call(*args, **kwargs):
            self.open_during_calls.append(self.open_sessions())
            return attribute(*args, **kwargs)

        return call
