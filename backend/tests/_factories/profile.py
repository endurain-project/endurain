"""Profile archives, built the way the export writes them, for tests on the real database."""

import io
import json
import struct
import uuid
import zipfile
import zlib
from collections.abc import Mapping

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import modules.users.users.schema as users_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.service as profile_service


def png(shade: int = 200, size: int = 2) -> bytes:
    """Build a valid PNG, different for each shade.

    Args:
        shade: The grey the image is filled with.
        size: Width and height in pixels.

    Returns:
        The image bytes.
    """

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes([shade, shade, shade]) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def archive_of(entries: Mapping[str, object]) -> bytes:
    """Build a ZIP archive: a name ending in ``.json`` is written as JSON, anything else as the bytes given.

    Args:
        entries: Entry name to its content.

    Returns:
        The archive bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for name, content in entries.items():
            if isinstance(content, bytes):
                zipf.writestr(name, content)
            else:
                zipf.writestr(name, json.dumps(content))
    return buffer.getvalue()


def profile_archive(user: users_schema.UserRead, **sections: object) -> bytes:
    """Build an archive exported from a user's account, holding the sections given.

    Args:
        user: The account the archive claims to come from; its username and email go into ``data/user.json``.
        **sections: Section name (``user_goals``, ``gears``, ...) to its records, written as ``data/<name>.json``.
            ``user`` replaces the account row.

    Returns:
        The archive bytes.
    """
    entries: dict[str, object] = {"data/user.json": [{"username": user.username, "email": user.email}]}
    for name, records in sections.items():
        entries[f"data/{name}.json"] = records
    return archive_of(entries)


def export_archive(user_id: uuid.UUID, storage: platform_providers.StorageProvider, db: Session) -> bytes:
    """Export an account the way the export job does and read the staged archive back.

    Args:
        user_id: The exporting user.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The archive bytes; the staged copy is removed.
    """
    profile_service.stage_export(user_id, storage, db)
    key = profile_constants.export_staged_key(user_id)
    data = storage.get(profile_constants.EXPORT_STAGING_AREA, key)
    assert data is not None
    storage.delete(profile_constants.EXPORT_STAGING_AREA, key)
    return data


class FaultyStorage:
    """A storage provider that fails the way an unreachable backend does, and delegates everything else.

    Attributes:
        inner: The real provider the calls fall through to.
    """

    def __init__(
        self,
        inner: platform_providers.StorageProvider,
        *,
        faults: Mapping[str, BaseException] | None = None,
        key_faults: Mapping[tuple[str, str], BaseException] | None = None,
    ) -> None:
        """Wrap a provider.

        Args:
            inner: The real provider.
            faults: Method name to the error every call of it raises.
            key_faults: ``(method name, key)`` to the error the call on that key raises.
        """
        self.inner = inner
        self._faults = dict(faults or {})
        self._key_faults = dict(key_faults or {})

    def __getattr__(self, name: str):
        """Return the provider's attribute, or a method that raises when a fault is set for it."""
        attribute = getattr(self.inner, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            if name in self._faults:
                raise self._faults[name]
            fault = self._key_faults.get((name, args[1] if len(args) > 1 else ""))
            if fault is not None:
                raise fault
            return attribute(*args, **kwargs)

        return call
