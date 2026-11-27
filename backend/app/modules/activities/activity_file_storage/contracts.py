"""The data shapes the retained-file surface accepts and returns."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityFileRef:
    """Where a retained file is stored and what it holds.

    Attributes:
        file_id: The file row's id.
        storage_key: The blob's key in the activity-files storage area.
        extension: The file's extension with its dot, such as ``.fit``.
        sha256: Hex SHA-256 of the file's bytes.
        size_bytes: The file's size.
    """

    file_id: uuid.UUID
    storage_key: str
    extension: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class StagedFile:
    """A retained file whose row exists and whose blob is stored.

    Attributes:
        ref: The file.
        created: Whether this call created the row, as opposed to taking the live row of the same bytes.
    """

    ref: ActivityFileRef
    created: bool
