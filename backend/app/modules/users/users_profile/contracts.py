"""Typed seams of the profile export and import.

A module that owns part of a user's profile describes it as a :data:`ProfileSection`; app composition
registers the sections and the export and import orchestrators run them in order. A section sees the
archive only through the writer and reader protocols and the contexts below, so it needs nothing from
the profile package itself.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import jasil.providers as platform_providers
from pydantic import BaseModel
from sqlalchemy.orm import Session

#: Archived id to stored id, per section, keyed by the key of the section that published the ids.
type ProfileIdMaps = dict[str, dict[int, int]]

#: What an archive carries of a row's identity: the exporting account's id, owner and version, none of which an import writes.
ARCHIVE_ROW_IDENTITY = frozenset({"id", "user_id", "version", "updated_at"})


def without_row_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the row identity an archive carries, leaving the fields an import writes.

    Args:
        row: One exported row.

    Returns:
        The row without its id, owner, version and ``updated_at``, which the import renews.
    """
    return {key: value for key, value in row.items() if key not in ARCHIVE_ROW_IDENTITY}


class ProfileArchiveWriter(Protocol):
    """The export archive as a section sees it.

    Every JSON write also sets ``counts[stem]`` to the number of records written, where ``stem`` is the
    file name without its folder and ``.json``.
    """

    def write_json(self, path: str, records: Sequence[BaseModel]) -> None:
        """Write records as one JSON array entry.

        Args:
            path: Entry path inside the archive.
            records: The records to serialize.
        """
        ...

    def write_json_stream(self, path: str, batches: Iterable[Sequence[BaseModel]]) -> None:
        """Write records as one JSON array entry, holding one batch at a time.

        Nothing else may be written to the archive while ``batches`` is consumed.

        Args:
            path: Entry path inside the archive.
            batches: The records to serialize, read lazily.
        """
        ...

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write one entry as it is.

        Args:
            path: Entry path inside the archive.
            data: The entry content.
        """
        ...


class ProfileArchiveReader(Protocol):
    """The import archive as a section sees it; every read counts against the archive-wide limits."""

    @property
    def names(self) -> frozenset[str]:
        """The entry names in the archive."""
        ...

    def load_json(self, path: str, *, check_memory: bool = True) -> list[dict[str, Any]]:
        """Load a JSON array entry strictly.

        Args:
            path: Entry path inside the archive.
            check_memory: Whether to check memory usage after parsing.

        Returns:
            The objects the entry lists; an absent entry or one that is not a list gives an empty list.

        Raises:
            FileSizeError: If the entry exceeds the allowed size.
            JSONParseError: If the entry is not valid JSON.
            MemoryAllocationError: If the memory limit is exceeded.
        """
        ...

    def load_json_part(self, path: str) -> list[dict[str, Any]]:
        """Load one part of a split JSON array entry, tolerating a bad part.

        Args:
            path: Entry path inside the archive.

        Returns:
            The objects the part lists; a part that is too large or not a JSON list is logged and gives an empty list.
        """
        ...

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        """Read one entry.

        Args:
            path: Entry path inside the archive.
            max_bytes: The most this entry may decompress to.

        Returns:
            The entry content.

        Raises:
            FileSizeError: If the entry or the archive exceeds the allowed size.
        """
        ...


@dataclass(frozen=True, kw_only=True)
class ProfileExportContext:
    """What a section needs to export its entries.

    Attributes:
        user_id: The user being exported.
        db: Database session, in the export's read transaction.
        storage: The platform storage provider.
        archive: Where to write entries.
        counts: Exported item counts, by key.
        batch_size: How many records to hold at a time.
        check_memory: Raises when the memory limit is exceeded; takes a description of the operation.
        check_timeout: Raises when the export is out of time.
    """

    user_id: int
    db: Session
    storage: platform_providers.StorageProvider
    archive: ProfileArchiveWriter
    counts: dict[str, int]
    batch_size: int
    check_memory: Callable[[str], None]
    check_timeout: Callable[[], None]


@dataclass(frozen=True, kw_only=True)
class ProfileImportContext:
    """What a section needs to restore its entries.

    Attributes:
        user_id: The user being imported into.
        db: Database session; a restore stages rows and never commits.
        storage: The platform storage provider.
        archive: Where to read entries.
        counts: Imported item counts, by key.
        ids: Ids restored by the sections that ran before this one.
        batch_size: How many records to hold at a time.
        check_memory: Raises when the memory limit is exceeded; takes a description of the operation.
        check_timeout: Raises when the import is out of time.
        check_activity_count: Raises when an archive lists more activities than an import allows.
    """

    user_id: int
    db: Session
    storage: platform_providers.StorageProvider
    archive: ProfileArchiveReader
    counts: dict[str, int]
    ids: ProfileIdMaps
    batch_size: int
    check_memory: Callable[[str], None]
    check_timeout: Callable[[], None]
    check_activity_count: Callable[[int], None]


#: Runs after the export has committed its read transaction, so it may take long on object storage.
type ExportFiles = Callable[[], None]

#: Runs after the import has committed its rows, so it may name the stored ids.
type RestoreFiles = Callable[[], None]


@dataclass(frozen=True, kw_only=True)
class ProfileRecordsSection:
    """A section that is one JSON entry, ``data/{key}.json``, counted under ``key``.

    The callables take and return builtin and pydantic types, so a module that knows nothing of users
    can provide them.

    Attributes:
        key: Entry name and count key; also the key of the ids ``restore`` publishes.
        export: Lists a user's records, as ``(user_id, db)``.
        restore: Stages archived records, as ``(records, user_id, ids, db)``, and returns how many it staged.
            It may publish ``ids[key]``.
    """

    key: str
    export: Callable[[int, Session], Sequence[BaseModel]]
    restore: Callable[[list[dict[str, Any]], int, ProfileIdMaps, Session], int]


@dataclass(frozen=True, kw_only=True)
class ProfileArchiveSection:
    """A section that writes and reads its own entries.

    Attributes:
        key: Name of the section, also the key of the ids it publishes.
        export: Writes the entries; may return the work that runs after the read transaction is committed.
        restore: Stages the rows; returns the work that runs after the commit, or ``None`` when
            the archive has nothing to write then.
    """

    key: str
    export: Callable[[ProfileExportContext], ExportFiles | None]
    restore: Callable[[ProfileImportContext], RestoreFiles | None]


type ProfileSection = ProfileRecordsSection | ProfileArchiveSection
