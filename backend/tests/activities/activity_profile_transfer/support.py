"""Run the activities' profile section against a real archive, the database and the platform's storage."""

import io
import json
import uuid
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import modules.activities.activity_profile_transfer.export_service as export_service
import modules.activities.activity_profile_transfer.import_service as import_service
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.utils as profile_utils

#: Every key the section reports a count for, whatever the archive holds.
COUNT_KEYS = frozenset(
    {
        "activities",
        "activity_files",
        "media",
        "activity_laps",
        "activity_sets",
        "activity_samples",
        "activity_workout_steps",
        "activity_media",
        "activity_exercise_titles",
        "activity_sources",
    }
)


def _no_check(*_args: object) -> None:
    """Accept every memory and time check."""


@dataclass
class Exported:
    """What an export wrote.

    Attributes:
        entries: Archive entry name to its bytes.
        counts: The counts the section reported.
        after_commit: The work that writes the files and media, or ``None`` when there is none.
    """

    entries: dict[str, bytes]
    counts: dict[str, int]
    after_commit: Callable[[], None] | None
    names: list[str] = field(default_factory=list)

    def json(self, name: str) -> list[dict[str, Any]]:
        """Parse a JSON entry.

        Args:
            name: Entry name.

        Returns:
            The records it lists.
        """
        return json.loads(self.entries[name])


@contextmanager
def _open_archive() -> Iterator[tuple[io.BytesIO, zipfile.ZipFile]]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        yield buffer, archive


def export_activities(
    db: Session,
    user_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
    *,
    batch_size: int = 10,
    run_after_commit: bool = True,
    writer_type: type[profile_utils.ZipArchiveWriter] = profile_utils.ZipArchiveWriter,
    check_memory: Callable[[str], None] = _no_check,
    check_timeout: Callable[[], None] = _no_check,
) -> Exported:
    """Export a user's activities the way the profile export runs the section.

    Args:
        db: Database session the section reads in.
        user_id: The user to export.
        storage: The platform storage the files and media are read from.
        batch_size: How many activities the section holds at a time.
        run_after_commit: Whether to run the deferred file and media work.
        writer_type: The archive writer to use.
        check_memory: The context's memory check.
        check_timeout: The context's time check.

    Returns:
        What the archive holds and the counts reported.
    """
    counts: dict[str, int] = {}
    with _open_archive() as (buffer, zipf):
        ctx = users_profile_contracts.ProfileExportContext(
            user_id=user_id,
            db=db,
            storage=storage,
            archive=writer_type(zipf, counts),
            counts=counts,
            batch_size=batch_size,
            check_memory=check_memory,
            check_timeout=check_timeout,
        )
        after_commit = export_service.export_profile(ctx)
        if run_after_commit and after_commit is not None:
            after_commit()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as written:
        entries = {name: written.read(name) for name in written.namelist()}
    return Exported(entries=entries, counts=counts, after_commit=after_commit, names=list(entries))


@dataclass
class Restored:
    """What an import staged.

    Attributes:
        counts: The counts the section reported.
        after_commit: The work that writes the files and media, or ``None`` when there is none.
    """

    counts: dict[str, int]
    after_commit: Callable[[], None] | None


def import_activities(
    db: Session,
    user_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
    entries: dict[str, Any],
    *,
    ids: users_profile_contracts.ProfileIdMaps | None = None,
    max_activities: int = 10_000,
    batch_size: int = 125,
    max_json_bytes: int = 128 * 1024 * 1024,
    run_after_commit: bool = True,
    check_memory: Callable[[str], None] = _no_check,
    check_timeout: Callable[[], None] = _no_check,
) -> Restored:
    """Restore the activities of an archive the way the profile import runs the section.

    Args:
        db: Database session the rows are staged in.
        user_id: The user to import into.
        storage: The platform storage the files and media are written to.
        entries: Archive entry name to its content (bytes, or JSON-serializable records).
        ids: Ids restored by the sections that ran before.
        max_activities: The most activities the archive may list.
        batch_size: How many activities the section holds at a time.
        max_json_bytes: The most one JSON entry may decompress to.
        run_after_commit: Whether to run the deferred file and media work.
        check_memory: The context's memory check.
        check_timeout: The context's time check.

    Returns:
        The counts reported and the deferred work.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for name, content in entries.items():
            zipf.writestr(name, content if isinstance(content, bytes) else json.dumps(content))
    archive = profile_utils.ZipArchiveReader(
        zipfile.ZipFile(io.BytesIO(buffer.getvalue())),
        max_json_bytes=max_json_bytes,
        max_uncompressed_bytes=1024 * 1024 * 1024,
        max_memory_mb=1024,
        enable_memory_monitoring=False,
    )

    def check_activity_count(count: int) -> None:
        if count > max_activities:
            raise profile_exceptions.ActivityLimitError(f"Too many activities ({count})")

    counts: dict[str, int] = {}
    ctx = users_profile_contracts.ProfileImportContext(
        user_id=user_id,
        db=db,
        storage=storage,
        archive=archive,
        counts=counts,
        ids=ids or {},
        batch_size=batch_size,
        check_memory=check_memory,
        check_timeout=check_timeout,
        check_activity_count=check_activity_count,
    )
    after_commit = import_service.restore_profile(ctx)
    if run_after_commit and after_commit is not None:
        after_commit()
    return Restored(counts=counts, after_commit=after_commit)


class UnavailableStorage:
    """The platform storage, except that reading or listing chosen keys fails as an unreachable backend does."""

    def __init__(
        self,
        inner: platform_providers.StorageProvider,
        *,
        unreadable: tuple[str, ...] = (),
        unlistable: bool = False,
        broken: Exception | None = None,
    ) -> None:
        """Wrap a storage.

        Args:
            inner: The storage that serves everything else.
            unreadable: Fragments of keys whose read raises ``StorageBackendUnavailableError``.
            unlistable: Whether listing raises ``StorageBackendUnavailableError``.
            broken: An error raised by every read and listing instead, as a defect would.
        """
        self._inner = inner
        self._unreadable = unreadable
        self._unlistable = unlistable
        self._broken = broken
        self.reads: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def get(self, area: str, key: str) -> bytes | None:
        """Read a blob, failing for the keys chosen at construction."""
        self.reads[key] += 1
        if self._broken is not None:
            raise self._broken
        if any(fragment in key for fragment in self._unreadable):
            raise platform_providers.StorageBackendUnavailableError("backend down")
        return self._inner.get(area, key)

    def list_keys(self, area: str, prefix: str = "") -> list[str]:
        """List keys, failing when chosen at construction."""
        if self._broken is not None:
            raise self._broken
        if self._unlistable:
            raise platform_providers.StorageBackendUnavailableError("permission denied")
        return self._inner.list_keys(area, prefix)


def png(shade: int = 200) -> bytes:
    """Return a valid 2x2 PNG, different for each shade."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes([shade, shade, shade]) * 2 for _ in range(2))
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


#: A minimal GPX file the activity validator accepts.
GPX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<gpx version="1.1" creator="endurain-test" xmlns="http://www.topografix.com/GPX/1/1">'
    b"<trk><name>Seed</name><trkseg>"
    b'<trkpt lat="38.7" lon="-9.1"><ele>10</ele><time>2026-07-28T09:00:00Z</time></trkpt>'
    b'<trkpt lat="38.8" lon="-9.2"><ele>12</ele><time>2026-07-28T09:00:10Z</time></trkpt>'
    b"</trkseg></trk></gpx>"
)

#: The counts only an import reports.
IMPORT_ONLY_COUNT_KEYS = frozenset({"activities_skipped"})
