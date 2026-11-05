"""Tests for the unified file-upload pipeline in ``core.file_uploads``."""

from __future__ import annotations

import asyncio
import gzip
import io
import logging
import struct
import zipfile
import zlib
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image, ImageCms
from safeuploads import ErrorCode
from safeuploads.exceptions import (
    CompressionSecurityError,
    ExtensionSecurityError,
    FilenameSecurityError,
    FileProcessingError,
    FileSecurityError,
    FileSignatureError,
    FileSizeError,
    FileValidationError,
    MimeTypeError,
    UnicodeSecurityError,
    WindowsReservedNameError,
    ZipBombError,
)

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
from core.file_uploads import (
    UploadKind,
    _resolve_upload_path,
    _stream_to_path_sync,
    _to_domain_error,
    extract_validated_zip_sync,
    move_within,
    read_validated_upload_sync,
    safe_remove_within,
    save_validated_bytes_sync,
    save_validated_upload_sync,
    validate_bytes_sync,
    validate_local_file_sync,
)
from tests._helpers import images

# ---------------------------------------------------------------------------
# Fixtures: minimal valid payloads per UploadKind
# ---------------------------------------------------------------------------


def _make_png_bytes() -> bytes:
    """Return a minimal valid 1x1 PNG image."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = (
        struct.pack(">I", len(ihdr_data))
        + b"IHDR"
        + ihdr_data
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    )
    raw = b"\x00\xff\xff\xff"  # filter byte + 1 RGB pixel
    compressed = zlib.compress(raw)
    idat = (
        struct.pack(">I", len(compressed))
        + b"IDAT"
        + compressed
        + struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    )
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    return sig + ihdr + idat + iend


def _make_zip_bytes() -> bytes:
    """Return a minimal valid ZIP archive with one entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hello.txt", b"hello world")
    return buf.getvalue()


def _make_gpx_bytes() -> bytes:
    """Return a minimal valid GPX 1.1 document."""
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<gpx version="1.1" creator="endurain-tests"'
        b' xmlns="http://www.topografix.com/GPX/1/1">\n'
        b"  <trk><name>t</name><trkseg>"
        b'<trkpt lat="0" lon="0"></trkpt>'
        b"</trkseg></trk>\n"
        b"</gpx>\n"
    )


def _make_gzip_bytes() -> bytes:
    """Return a minimal valid gzip-wrapped GPX payload."""
    return gzip.compress(_make_gpx_bytes())


def _upload(filename: str, content: bytes) -> UploadFile:
    """Build an UploadFile around in-memory content."""
    return UploadFile(file=io.BytesIO(content), filename=filename)


_KIND_CASES = [
    (UploadKind.IMAGE, "ok.png", _make_png_bytes),
    (UploadKind.ZIP, "ok.zip", _make_zip_bytes),
    (UploadKind.ACTIVITY, "ok.gpx", _make_gpx_bytes),
    (UploadKind.GZIP, "ok.gpx.gz", _make_gzip_bytes),
]


# ---------------------------------------------------------------------------
# _to_domain_error: one branch per mapped exception class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "err,expected_status",
    [
        (FileSizeError("too big"), 413),
        (MimeTypeError("bad mime"), 400),
        (FileSignatureError("bad sig"), 400),
        (ExtensionSecurityError("bad ext"), 400),
        (FilenameSecurityError("bad name"), 400),
        (WindowsReservedNameError("CON"), 400),
        (UnicodeSecurityError("rtl"), 400),
        (ZipBombError("bomb"), 400),
        (CompressionSecurityError("bad zip"), 400),
        (FileValidationError("generic"), 400),
        (FileProcessingError("oops"), 500),
    ],
)
def test_to_domain_error_mapping(err, expected_status):
    """Each safeuploads exception maps to the documented status."""
    domain_err = _to_domain_error(err)
    assert isinstance(domain_err, core_exceptions.DomainError)
    assert domain_err.status_code == expected_status
    assert domain_err.detail


def test_to_domain_error_maps_an_empty_file_to_invalid_input():
    """An empty file is bad content, not an oversized payload."""
    err = FileSizeError("Empty file not allowed", size=0, error_code=ErrorCode.FILE_EMPTY)

    domain_err = _to_domain_error(err)

    assert isinstance(domain_err, core_exceptions.InvalidInputError)
    assert domain_err.status_code == 400


@pytest.mark.parametrize("kind,filename,_b", _KIND_CASES)
def test_read_validated_upload_sync_rejects_an_empty_file_as_invalid_input(kind: UploadKind, filename: str, _b):
    """A 0-byte upload is refused with 400 for every kind."""
    upload = _upload(filename, b"")
    with pytest.raises(core_exceptions.InvalidInputError):
        try:
            read_validated_upload_sync(upload, kind=kind)
        finally:
            upload.file.close()


# ---------------------------------------------------------------------------
# _resolve_upload_path: filename hardening
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "../escape.txt",
        "subdir/inside.txt",
        "/abs/path.txt",
    ],
)
def test_resolve_upload_path_rejects_unsafe(tmp_path: Path, bad_name: str):
    """Traversal, absolute, and nested names are rejected with 400."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        _resolve_upload_path(str(tmp_path), bad_name)
    assert exc.value.status_code == 400


def test_resolve_upload_path_accepts_safe(tmp_path: Path):
    """A bare filename resolves under the upload directory."""
    resolved = _resolve_upload_path(str(tmp_path), "ok.png")
    assert resolved.parent == tmp_path.resolve()


# ---------------------------------------------------------------------------
# read_validated_upload_sync: happy + sad paths per kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind,filename,builder", _KIND_CASES)
def test_read_validated_upload_sync_accepts_valid_payload(kind: UploadKind, filename: str, builder):
    """Each kind validates without raising on a well-formed payload."""
    upload = _upload(filename, builder())
    try:
        read_validated_upload_sync(upload, kind=kind)
    finally:
        upload.file.close()


def test_read_validated_upload_sync_accepts_zip_with_gzip_entries():
    """A ZIP holding ``.gz`` activities (Strava bulk export layout) validates."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("activities.csv", b"Activity ID\n1\n")
        zf.writestr("activities/1.gpx.gz", _make_gzip_bytes())
    upload = _upload("export.zip", buf.getvalue())
    try:
        read_validated_upload_sync(upload, kind=UploadKind.ZIP)
    finally:
        upload.file.close()


@pytest.mark.parametrize("kind,filename,_b", _KIND_CASES)
def test_read_validated_upload_sync_rejects_garbage_per_kind(kind: UploadKind, filename: str, _b):
    """Garbage bytes with a valid extension are rejected."""
    upload = _upload(filename, b"not a real payload")
    with pytest.raises(core_exceptions.DomainError) as exc:
        try:
            read_validated_upload_sync(upload, kind=kind)
        finally:
            upload.file.close()
    # 400 for signature/MIME mismatch, 413 if size cap would
    # somehow trigger first; both are acceptable rejections.
    assert exc.value.status_code in {400, 413}


# ---------------------------------------------------------------------------
# _stream_to_path_sync: success / oversize / cleanup
# ---------------------------------------------------------------------------


def test_stream_to_path_sync_writes_and_cleans_part_file(
    tmp_path: Path,
):
    """Successful streaming leaves the destination, no .part."""
    payload = b"x" * (3 * 1024 * 1024)  # 3 MiB across multiple chunks
    upload = _upload("blob.bin", payload)
    destination = tmp_path / "blob.bin"
    try:
        _stream_to_path_sync(upload, destination, max_bytes=10 * 1024 * 1024)
    finally:
        upload.file.close()
    assert destination.read_bytes() == payload
    assert not (tmp_path / "blob.bin.part").exists()


def test_stream_to_path_sync_aborts_on_oversize(tmp_path: Path):
    """Exceeding max_bytes raises 413 and removes the .part file."""
    payload = b"y" * (2 * 1024 * 1024)
    upload = _upload("over.bin", payload)
    destination = tmp_path / "over.bin"
    with pytest.raises(core_exceptions.DomainError) as exc:
        try:
            _stream_to_path_sync(upload, destination, max_bytes=1024)
        finally:
            upload.file.close()
    assert exc.value.status_code == 413
    assert not destination.exists()
    assert not (tmp_path / "over.bin.part").exists()


# ---------------------------------------------------------------------------
# save_validated_upload_sync: end-to-end per kind + traversal
# ---------------------------------------------------------------------------


def test_save_validated_upload_sync_image_happy_path(tmp_path: Path):
    """A valid image is validated then persisted to disk."""
    upload = _upload("avatar.png", _make_png_bytes())
    try:
        path = save_validated_upload_sync(
            upload,
            kind=UploadKind.IMAGE,
            upload_dir=str(tmp_path),
            filename="avatar.png",
        )
    finally:
        upload.file.close()
    assert Path(path).exists()
    assert Path(path).read_bytes() == _make_png_bytes()
    assert not (tmp_path / "avatar.png.part").exists()


def test_save_validated_upload_sync_signature_mismatch_no_partial(
    tmp_path: Path,
):
    """Failed validation must not leave any file behind."""
    upload = _upload("evil.png", b"this is not a png")
    with pytest.raises(core_exceptions.DomainError):
        try:
            save_validated_upload_sync(
                upload,
                kind=UploadKind.IMAGE,
                upload_dir=str(tmp_path),
                filename="evil.png",
            )
        finally:
            upload.file.close()
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Module-level wiring
# ---------------------------------------------------------------------------


def test_module_exposes_singleton_validator():
    """The application uses one shared FileValidator instance."""
    assert core_file_uploads.file_validator is not None
    # Limits configured on the shared validator.
    limits = core_file_uploads.file_validator.config.limits
    assert limits.max_activity_file_size == 200 * 1024 * 1024
    assert limits.max_gzip_size == 200 * 1024 * 1024
    assert limits.max_uncompressed_size == 2 * 1024 * 1024 * 1024
    assert limits.enable_audit_logging is True


def test_failed_validation_emits_audit_record(caplog):
    """Rejected uploads emit a structured audit failure record."""
    upload = _upload("evil.png", b"this is not a png")
    caplog.set_level(logging.WARNING, logger="safeuploads.audit")

    with pytest.raises(core_exceptions.DomainError):
        try:
            core_file_uploads._validate_upload(upload, kind=UploadKind.IMAGE)
        finally:
            upload.file.close()

    failure_records = [
        record for record in caplog.records if getattr(record, "audit_event_type", "") == "validation_failure"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].audit_correlation_id


# ---------------------------------------------------------------------------
# Phase 19: validate_bytes_sync / save_validated_bytes_sync
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind,filename,builder", _KIND_CASES)
def test_validate_bytes_sync_accepts_valid_payload(kind: UploadKind, filename: str, builder):
    """Valid in-memory bytes pass per-kind validation."""
    validate_bytes_sync(builder(), kind=kind, filename=filename)


def test_validate_bytes_sync_rejects_garbage():
    """Garbage bytes with a valid extension are rejected."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        validate_bytes_sync(b"not a real zip", kind=UploadKind.ZIP, filename="x.zip")
    assert exc.value.status_code in {400, 413}


def test_save_validated_bytes_sync_writes_validated_payload(
    tmp_path: Path,
):
    """Bytes are validated then atomically written to disk."""
    saved = save_validated_bytes_sync(
        _make_zip_bytes(),
        kind=UploadKind.ZIP,
        upload_dir=str(tmp_path),
        filename="ok.zip",
    )
    assert Path(saved).exists()
    assert Path(saved).parent == tmp_path.resolve()
    assert not (tmp_path / "ok.zip.part").exists()


def test_save_validated_bytes_sync_preserves_existing_on_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed atomic replace keeps the old file intact."""
    destination = tmp_path / "ok.zip"
    destination.write_bytes(b"original")

    def fail_replace(_src, _dst):
        """Simulate an atomic-replace filesystem failure."""
        raise OSError("replace failed")

    monkeypatch.setattr(core_file_uploads.os, "replace", fail_replace)

    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_bytes_sync(
            _make_zip_bytes(),
            kind=UploadKind.ZIP,
            upload_dir=str(tmp_path),
            filename="ok.zip",
        )

    assert exc.value.status_code == 500
    assert destination.read_bytes() == b"original"
    assert not (tmp_path / "ok.zip.part").exists()


def test_save_validated_bytes_sync_rejects_bad_filename(tmp_path: Path):
    """Server-generated filename guard still applies for byte writes."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_bytes_sync(
            _make_zip_bytes(),
            kind=UploadKind.ZIP,
            upload_dir=str(tmp_path),
            filename="../escape.zip",
        )
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Phase 19: extract_validated_zip_sync
# ---------------------------------------------------------------------------


def _build_zip_with_entries(
    entries: list[tuple[str, bytes]],
) -> bytes:
    """Build a ZIP containing the given (name, bytes) entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_validated_zip_sync_happy_path(tmp_path: Path):
    """All safe entries are extracted under dest_dir."""
    payload = _build_zip_with_entries(
        [
            ("a.gpx", _make_gpx_bytes()),
            ("b.gpx", _make_gpx_bytes()),
        ]
    )
    zip_path = tmp_path / "archive.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    extracted = extract_validated_zip_sync(zip_path, dest_dir=dest)

    assert len(extracted) == 2
    for entry in extracted:
        assert entry.parent == dest.resolve()
        assert entry.exists()


def test_extract_validated_zip_sync_rejects_zip_slip(tmp_path: Path):
    """A traversal entry name aborts extraction with 400."""
    payload = _build_zip_with_entries([("../escape.gpx", _make_gpx_bytes())])
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400
    # No file should have leaked outside dest.
    assert not (tmp_path / "escape.gpx").exists()


def test_extract_validated_zip_sync_rejects_absolute_entry(
    tmp_path: Path,
):
    """An absolute entry name is treated as a zip-slip attempt."""
    payload = _build_zip_with_entries([("/abs/path.gpx", _make_gpx_bytes())])
    zip_path = tmp_path / "abs.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400


def test_extract_validated_zip_sync_rejects_windows_drive_entry(
    tmp_path: Path,
):
    """A Windows-drive entry name is treated as unsafe."""
    payload = _build_zip_with_entries([("C:/abs/path.gpx", _make_gpx_bytes())])
    zip_path = tmp_path / "drive.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400


def test_extract_validated_zip_sync_cleans_previous_entries_on_error(
    tmp_path: Path,
):
    """A later unsafe entry removes earlier extracted files."""
    payload = _build_zip_with_entries(
        [
            ("good.gpx", _make_gpx_bytes()),
            ("../escape.gpx", _make_gpx_bytes()),
        ]
    )
    zip_path = tmp_path / "partial.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400
    assert not (dest / "good.gpx").exists()
    assert not (tmp_path / "escape.gpx").exists()


def test_extract_validated_zip_sync_refuses_existing_target(
    tmp_path: Path,
):
    """Existing files under dest_dir are never overwritten."""
    dest = tmp_path / "out"
    dest.mkdir()
    existing = dest / "keep.gpx"
    existing.write_bytes(b"original")
    payload = _build_zip_with_entries([("keep.gpx", _make_gpx_bytes())])
    zip_path = tmp_path / "overwrite.zip"
    zip_path.write_bytes(payload)

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)

    assert exc.value.status_code == 400
    assert existing.read_bytes() == b"original"
    assert not any(path.name.startswith(".extract-") for path in dest.iterdir())


def test_extract_validated_zip_sync_rejects_duplicate_target(
    tmp_path: Path,
):
    """Duplicate archive entries that resolve together are rejected."""
    payload = _build_zip_with_entries(
        [
            ("dup.gpx", _make_gpx_bytes()),
            ("./dup.gpx", _make_gpx_bytes()),
        ]
    )
    zip_path = tmp_path / "dupes.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)

    assert exc.value.status_code == 400
    assert not (dest / "dup.gpx").exists()


def test_extract_validated_zip_sync_per_entry_validation_drops_bad(
    tmp_path: Path,
):
    """Invalid entries are dropped when per_entry_kind is given."""
    payload = _build_zip_with_entries(
        [
            ("good.gpx", _make_gpx_bytes()),
            ("bad.gpx", b"not a real gpx"),
        ]
    )
    zip_path = tmp_path / "mixed.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    extracted = extract_validated_zip_sync(
        zip_path,
        dest_dir=dest,
        per_entry_kind=UploadKind.ACTIVITY,
    )

    names = sorted(p.name for p in extracted)
    assert names == ["good.gpx"]
    # Bad entry was unlinked after validation failure.
    assert not (dest / "bad.gpx").exists()


def test_extract_validated_zip_sync_max_entries_enforced(tmp_path: Path):
    """max_entries cap aborts before any file is written."""
    payload = _build_zip_with_entries([(f"f{i}.gpx", _make_gpx_bytes()) for i in range(5)])
    zip_path = tmp_path / "many.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest, max_entries=2)
    assert exc.value.status_code == 400
    # Nothing should have been extracted on entry-count rejection.
    assert not any(dest.iterdir()) if dest.exists() else True


# ---------------------------------------------------------------------------
# Phase 21: move_within / safe_remove_within
# ---------------------------------------------------------------------------


def test_move_within_moves_into_dest(tmp_path: Path):
    """Source file lands at dest_dir/filename and original is gone."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest_dir = tmp_path / "out"

    moved = move_within(src, dest_dir, filename="moved.bin")

    assert moved.exists()
    assert moved.parent == dest_dir.resolve()
    assert not src.exists()


def test_move_within_rejects_unsafe_filename(tmp_path: Path):
    """Traversal in filename is refused before any I/O."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest_dir = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        move_within(src, dest_dir, filename="../evil.bin")
    assert exc.value.status_code == 400
    assert src.exists()


def test_move_within_rejects_source_outside_base(tmp_path: Path):
    """Source path is checked when src_base_dir is provided."""
    src_base = tmp_path / "src-base"
    src_base.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"payload")
    dest_dir = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        move_within(
            outside,
            dest_dir,
            filename="moved.bin",
            src_base_dir=src_base,
        )
    assert exc.value.status_code == 400
    assert outside.exists()


def test_safe_remove_within_removes_inside(tmp_path: Path):
    """File under base_dir is removed and True is returned."""
    target = tmp_path / "doomed.bin"
    target.write_bytes(b"x")

    assert safe_remove_within(target, base_dir=tmp_path) is True
    assert not target.exists()


def test_safe_remove_within_refuses_outside(tmp_path: Path):
    """File outside base_dir raises 400 and is not touched."""
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")

    with pytest.raises(core_exceptions.DomainError) as exc:
        safe_remove_within(outside, base_dir=base)
    assert exc.value.status_code == 400
    assert outside.exists()


def test_safe_remove_within_missing_file_returns_false(tmp_path: Path):
    """A missing-but-contained path returns False without raising."""
    missing = tmp_path / "ghost.bin"
    assert safe_remove_within(missing, base_dir=tmp_path) is False


# ---------------------------------------------------------------------------
# _validator_for / max_bytes_for: dispatch edge cases
# ---------------------------------------------------------------------------


def test_validator_for_unknown_kind():
    """An unrecognized UploadKind raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported UploadKind"):
        core_file_uploads._validator_for("unknown")


def testmax_bytes_for_image():
    """IMAGE kind returns the expected byte cap."""
    assert core_file_uploads.max_bytes_for(UploadKind.IMAGE) == 20 * 1024 * 1024


def testmax_bytes_for_gzip():
    """GZIP kind returns the expected byte cap."""
    assert core_file_uploads.max_bytes_for(UploadKind.GZIP) == 200 * 1024 * 1024


def testmax_bytes_for_unknown_kind():
    """Unrecognized UploadKind raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported UploadKind"):
        core_file_uploads.max_bytes_for("unknown")


# ---------------------------------------------------------------------------
# _to_domain_error: fallback branch
# ---------------------------------------------------------------------------


def test_to_domain_error_fallback():
    """A plain FileSecurityError maps to 500."""
    err = FileSecurityError("generic security error")
    domain_err = _to_domain_error(err)
    assert domain_err.status_code == 500


# ---------------------------------------------------------------------------
# _resolve_upload_path / resolve_storage_path: extra edge cases
# ---------------------------------------------------------------------------


def test_resolve_upload_path_rejects_dotdot(tmp_path: Path):
    """A bare '..' filename escapes via relative_to failure."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        _resolve_upload_path(str(tmp_path), "..")
    assert exc.value.status_code == 400


def test_resolve_upload_path_rejects_nul_byte(tmp_path: Path):
    """Filename containing NUL byte is rejected."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        _resolve_upload_path(str(tmp_path), "bad\x00file")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# save_validated_bytes_sync: error handler
# ---------------------------------------------------------------------------


def test_save_validated_bytes_sync_generic_error(tmp_path: Path, monkeypatch):
    """Non-domain error in save_validated_bytes_sync raises 500."""

    def fail_makedirs(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(core_file_uploads.os, "makedirs", fail_makedirs)

    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_bytes_sync(_make_zip_bytes(), kind=UploadKind.ZIP, upload_dir=str(tmp_path), filename="fail.zip")
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _bytes_to_path_sync: oversize + cleanup OSError
# ---------------------------------------------------------------------------


def test_bytes_to_path_sync_oversize(tmp_path: Path):
    """Data exceeding max_bytes raises 413."""
    destination = tmp_path / "test.bin"
    with pytest.raises(core_exceptions.DomainError) as exc:
        core_file_uploads._bytes_to_path_sync(b"x" * 100, destination, max_bytes=10)
    assert exc.value.status_code == 413


def test_bytes_to_path_sync_cleans_part_on_oserror(tmp_path: Path, monkeypatch):
    """Part file cleanup handles OSError silently."""
    gpx_bytes = _make_gpx_bytes()

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(core_file_uploads.os, "replace", fail_replace)

    original_unlink = Path.unlink

    def fail_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.name.endswith(".part"):
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_bytes_sync(
            gpx_bytes,
            kind=UploadKind.ACTIVITY,
            upload_dir=str(tmp_path),
            filename="activity.gpx",
        )
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _stream_to_path_sync: cleanup OSError
# ---------------------------------------------------------------------------


def test_stream_to_path_sync_handles_cleanup_oserror(tmp_path: Path, monkeypatch):
    """OSError from part.unlink during stream cleanup is caught."""
    payload = b"x" * 1024
    upload = _upload("blob.bin", payload)
    destination = tmp_path / "blob.bin"

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(core_file_uploads.os, "replace", fail_replace)

    original_unlink = Path.unlink

    def fail_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.name.endswith(".part"):
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(OSError):
        try:
            _stream_to_path_sync(upload, destination, max_bytes=10 * 1024 * 1024)
        finally:
            upload.file.close()


# ---------------------------------------------------------------------------
# save_validated_upload_sync: generic error handler
# ---------------------------------------------------------------------------


def test_save_validated_upload_sync_generic_error(tmp_path: Path, monkeypatch):
    """Non-domain error in save_validated_upload_sync is wrapped in 500."""

    def fail_makedirs(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(core_file_uploads.os, "makedirs", fail_makedirs)

    upload = _upload("ride.gpx", _make_gpx_bytes())
    with pytest.raises(core_exceptions.DomainError) as exc:
        try:
            save_validated_upload_sync(
                upload,
                kind=UploadKind.ACTIVITY,
                upload_dir=str(tmp_path),
                filename="ride.gpx",
            )
        finally:
            upload.file.close()
    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to save file"


# ---------------------------------------------------------------------------
# delete_files_by_pattern: per-file and generic errors
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _is_safe_extraction_target: NUL / self-target
# ---------------------------------------------------------------------------


def test_is_safe_extraction_target_nul_byte(tmp_path: Path):
    """Entry name containing NUL byte is rejected."""
    result = core_file_uploads._is_safe_extraction_target("bad\x00file", tmp_path)
    assert result is None


def test_is_safe_extraction_target_equals_dest(tmp_path: Path):
    """Entry resolving to dest_dir itself is rejected."""
    dest = tmp_path / "out"
    dest.mkdir()
    result = core_file_uploads._is_safe_extraction_target(".", dest)
    assert result is None


# ---------------------------------------------------------------------------
# extract_validated_zip_sync: directory entries / symlink / size caps / bad file
# ---------------------------------------------------------------------------


def _make_zip_with_dir_entry() -> bytes:
    """ZIP containing a directory and a file entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mydir/", b"")
        zf.writestr("mydir/file.txt", b"content")
    return buf.getvalue()


def test_extract_validated_zip_sync_skips_dir_entries(tmp_path: Path):
    """Directory entries in ZIP are skipped."""
    zip_path = tmp_path / "withdir.zip"
    zip_path.write_bytes(_make_zip_with_dir_entry())
    dest = tmp_path / "out"

    extracted = extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert len(extracted) == 1
    assert extracted[0].name == "file.txt"


def test_extract_validated_zip_sync_rejects_symlink(tmp_path: Path):
    """Symlink entries in ZIP are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("link.txt")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, b"target")
    zip_path = tmp_path / "symlink.zip"
    zip_path.write_bytes(buf.getvalue())
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400


def test_extract_validated_zip_sync_entry_size_exceeded(tmp_path: Path, monkeypatch):
    """Entry exceeding max size is rejected with 413."""
    monkeypatch.setattr(core_file_uploads, "_MAX_EXTRACTED_ENTRY_BYTES", 10)
    payload = _build_zip_with_entries([("large.bin", b"x" * 100)])
    zip_path = tmp_path / "large.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 413


def test_extract_validated_zip_sync_total_size_exceeded(tmp_path: Path, monkeypatch):
    """Total uncompressed size exceeding max is rejected with 413."""
    monkeypatch.setattr(core_file_uploads, "_MAX_EXTRACTED_ENTRY_BYTES", 20)
    monkeypatch.setattr(core_file_uploads, "_MAX_TOTAL_EXTRACTED_BYTES", 15)
    payload = _build_zip_with_entries(
        [
            ("a.bin", b"x" * 10),
            ("b.bin", b"x" * 10),
        ]
    )
    zip_path = tmp_path / "total.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 413


def test_extract_validated_zip_sync_bad_file(tmp_path: Path):
    """Invalid ZIP file raises 400."""
    zip_path = tmp_path / "bad.zip"
    zip_path.write_bytes(b"not a zip file")
    dest = tmp_path / "out"

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 400


def test_extract_validated_zip_sync_promotion_failure(tmp_path: Path, monkeypatch):
    """OSError during promotion raises 500."""
    payload = _build_zip_with_entries([("a.gpx", _make_gpx_bytes())])
    zip_path = tmp_path / "ok.zip"
    zip_path.write_bytes(payload)
    dest = tmp_path / "out"

    def fail_promote(
        extracted: object,
        dest_path: object,
    ) -> object:
        raise OSError("promotion failed")

    monkeypatch.setattr(
        core_file_uploads,
        "_promote_extracted_files_sync",
        fail_promote,
    )

    with pytest.raises(core_exceptions.DomainError) as exc:
        extract_validated_zip_sync(zip_path, dest_dir=dest)
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# move_within: existing destination + OS error
# ---------------------------------------------------------------------------


def test_move_within_existing_destination(tmp_path: Path):
    """move_within rejects overwriting an existing destination."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    existing = dest_dir / "moved.bin"
    existing.write_bytes(b"existing")

    with pytest.raises(core_exceptions.DomainError) as exc:
        move_within(src, dest_dir, filename="moved.bin")
    assert exc.value.status_code == 400
    assert src.exists()
    assert existing.read_bytes() == b"existing"


def test_move_within_oserror(tmp_path: Path, monkeypatch):
    """OSError from shutil.move raises 500."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest_dir = tmp_path / "out"

    def fail_move(_src: object, _dst: object) -> None:
        raise OSError("move failed")

    monkeypatch.setattr(core_file_uploads.shutil, "move", fail_move)

    with pytest.raises(core_exceptions.DomainError) as exc:
        move_within(src, dest_dir, filename="moved.bin")
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# safe_remove_within: FileNotFoundError + OSError
# ---------------------------------------------------------------------------


def test_safe_remove_within_file_disappears(tmp_path: Path, monkeypatch):
    """FileNotFoundError from unlink is caught and returns False."""
    target = tmp_path / "ghost.bin"

    original_is_file = Path.is_file

    def mock_is_file(self: Path) -> bool:
        return True if self.name == "ghost.bin" else original_is_file(self)

    monkeypatch.setattr(Path, "is_file", mock_is_file)

    original_unlink = Path.unlink

    def mock_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "ghost.bin":
            raise FileNotFoundError("file disappeared")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    result = safe_remove_within(target, base_dir=tmp_path)
    assert result is False


def test_safe_remove_within_oserror_handling(tmp_path: Path, monkeypatch):
    """OSError from unlink is caught and returns False."""
    target = tmp_path / "locked.bin"
    target.write_bytes(b"x")

    original_unlink = Path.unlink

    def mock_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "locked.bin":
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    result = safe_remove_within(target, base_dir=tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# Synchronous entry points: save_validated_upload_sync / validate_local_file_sync
# ---------------------------------------------------------------------------


def test_save_validated_upload_sync_happy_path(tmp_path: Path):
    """A valid activity is validated then streamed to disk synchronously."""
    upload = _upload("ride.gpx", _make_gpx_bytes())
    path = save_validated_upload_sync(
        upload,
        kind=UploadKind.ACTIVITY,
        upload_dir=str(tmp_path),
        filename="server.gpx",
    )
    assert path == str(tmp_path / "server.gpx")
    assert Path(path).read_bytes() == _make_gpx_bytes()
    assert not (tmp_path / "server.gpx.part").exists()


def test_save_validated_upload_sync_rejects_garbage(tmp_path: Path):
    """Garbage bytes with a valid extension are rejected before any write."""
    upload = _upload("ride.gpx", b"not a real activity file")
    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_upload_sync(
            upload,
            kind=UploadKind.ACTIVITY,
            upload_dir=str(tmp_path),
            filename="server.gpx",
        )
    assert exc.value.status_code in {400, 413}
    assert list(tmp_path.iterdir()) == []


def test_save_validated_upload_sync_traversal_rejected(tmp_path: Path):
    """A traversal filename never produces a file on disk (validation passes first)."""
    upload = _upload("ride.gpx", _make_gpx_bytes())
    with pytest.raises(core_exceptions.DomainError) as exc:
        save_validated_upload_sync(
            upload,
            kind=UploadKind.ACTIVITY,
            upload_dir=str(tmp_path),
            filename="../escape.gpx",
        )
    assert exc.value.status_code == 400
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path.parent / "escape.gpx").exists()


def test_validate_local_file_sync_accepts_valid(tmp_path: Path):
    """A valid on-disk activity validates without raising."""
    path = tmp_path / "ride.gpx"
    path.write_bytes(_make_gpx_bytes())
    validate_local_file_sync(str(path), kind=UploadKind.ACTIVITY)


def test_read_validated_upload_sync_returns_bytes(tmp_path: Path):
    """A valid image is validated and returned without touching the filesystem."""
    png = _make_png_bytes()
    data = read_validated_upload_sync(_upload("photo.png", png), kind=UploadKind.IMAGE)
    assert data == png
    assert list(tmp_path.iterdir()) == []


def test_read_validated_upload_sync_rejects_garbage():
    """Garbage bytes with a valid extension are rejected rather than returned."""
    with pytest.raises(core_exceptions.DomainError) as exc:
        read_validated_upload_sync(_upload("photo.png", b"not a real image"), kind=UploadKind.IMAGE)
    assert exc.value.status_code in {400, 413}


def test_validate_local_file_sync_rejects_garbage(tmp_path: Path):
    """Garbage on-disk content is rejected with a 4xx/413."""
    path = tmp_path / "ride.gpx"
    path.write_bytes(b"not a real activity file")
    with pytest.raises(core_exceptions.DomainError) as exc:
        validate_local_file_sync(str(path), kind=UploadKind.ACTIVITY)
    assert exc.value.status_code in {400, 413}


def test_the_synchronous_forms_start_no_event_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Every synchronous entry point validates on the calling thread, without an event loop."""

    def refuse_loop(*args, **kwargs):
        raise AssertionError("an event loop was started")

    monkeypatch.setattr(asyncio.events, "new_event_loop", refuse_loop)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ride.gpx", _make_gpx_bytes())
    activity = tmp_path / "ride.gpx"
    activity.write_bytes(_make_gpx_bytes())

    validate_bytes_sync(_make_png_bytes(), kind=UploadKind.IMAGE, filename="photo.png")
    validate_local_file_sync(str(activity), kind=UploadKind.ACTIVITY)
    read_validated_upload_sync(_upload("photo.png", _make_png_bytes()), kind=UploadKind.IMAGE)
    save_validated_upload_sync(
        _upload("ride.gpx", _make_gpx_bytes()), kind=UploadKind.ACTIVITY, upload_dir=str(tmp_path), filename="up.gpx"
    )
    saved = save_validated_bytes_sync(
        archive.getvalue(), kind=UploadKind.ZIP, upload_dir=str(tmp_path / "zip"), filename="a.zip"
    )
    extracted = extract_validated_zip_sync(saved, dest_dir=str(tmp_path / "out"), per_entry_kind=UploadKind.ACTIVITY)

    assert [path.name for path in extracted] == ["ride.gpx"]


# ---------------------------------------------------------------------------
# Generic on-disk file helpers (moved here from the activity ingestion
# orchestrator, which had reimplemented them for its own use)
# ---------------------------------------------------------------------------


def test_sha256_file_matches_hashlib(tmp_path: Path):
    """The streamed digest matches a one-shot hash of the same bytes."""
    import hashlib

    from core.file_uploads import sha256_file

    path = tmp_path / "activity.gpx"
    payload = b"<gpx>some deterministic content</gpx>"
    path.write_bytes(payload)

    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_is_stable_across_reads(tmp_path: Path):
    """The same bytes hash identically every time (what makes re-import a no-op)."""
    from core.file_uploads import sha256_file

    path = tmp_path / "activity.fit"
    path.write_bytes(b"\x00\x01\x02repeatable\xff")

    assert sha256_file(path) == sha256_file(path)


def test_remove_files_removes_only_existing(tmp_path: Path):
    """Existing files are removed; missing ones are silently skipped."""
    from core.file_uploads import remove_files

    present = tmp_path / "a"
    present.write_bytes(b"x")
    missing = tmp_path / "b"

    remove_files([present, missing])

    assert not present.exists()


def test_remove_files_swallows_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A removal failure is logged, never raised — cleanup must not mask the real error."""
    import core.file_uploads as file_uploads

    present = tmp_path / "a"
    present.write_bytes(b"x")

    def _boom(_path):
        raise OSError("Permission denied")

    monkeypatch.setattr(file_uploads.os, "remove", _boom)

    file_uploads.remove_files([present])


def test_decompress_gzip_returns_inner_payload(tmp_path: Path):
    """A ``.gz`` is expanded to a temp file; the caller owns removing both files."""
    from core.file_uploads import decompress_gzip

    payload = _make_gpx_bytes()
    archive = tmp_path / "activity_123.gpx.gz"
    archive.write_bytes(gzip.compress(payload))

    temp_path, extension = decompress_gzip(archive)

    try:
        assert extension == ".gpx"
        assert Path(temp_path).read_bytes() == payload
        # Left in place: a failed import still needs the user's original.
        assert archive.exists()
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_decompress_gzip_rejects_invalid_archive(tmp_path: Path):
    """Non-gzip content is a 400, not a traceback."""
    from core.file_uploads import decompress_gzip

    archive = tmp_path / "bad.gpx.gz"
    archive.write_bytes(b"definitely not gzip")

    with pytest.raises(core_exceptions.DomainError) as exc:
        decompress_gzip(archive)
    assert exc.value.status_code == 400


def test_decompress_gzip_rejects_decompression_bomb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Output beyond the activity cap is a 413 and leaves no temp file behind."""
    import core.file_uploads as file_uploads

    archive = tmp_path / "big.gpx.gz"
    archive.write_bytes(gzip.compress(b"x" * 4096))
    monkeypatch.setattr(file_uploads, "_MAX_ACTIVITY_BYTES", 16)

    with pytest.raises(core_exceptions.DomainError) as exc:
        file_uploads.decompress_gzip(archive)
    assert exc.value.status_code == 413


# ---------------------------------------------------------------------------
# Metadata strip
# ---------------------------------------------------------------------------


class TestStripImageMetadata:
    def test_jpeg_loses_exif_gps_and_keeps_format(self):
        original = images.jpeg_with_exif()
        assert images.has_metadata(original)

        stripped = core_file_uploads.strip_image_metadata(original)

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.format == "JPEG"
            assert not image.getexif()
        assert not images.has_metadata(stripped)

    def test_exif_orientation_is_applied_so_the_picture_stays_upright(self):
        original = images.jpeg_with_exif((40, 20), orientation=6)

        stripped = core_file_uploads.strip_image_metadata(original)

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.size == (20, 40)

    def test_png_loses_text_chunks_and_keeps_alpha(self):
        original = images.png_with_text()
        assert images.has_metadata(original)

        stripped = core_file_uploads.strip_image_metadata(original)

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0))[3] == 0
        assert not images.has_metadata(stripped)

    def test_palette_png_keeps_its_transparency(self):
        buffer = io.BytesIO()
        Image.new("P", (4, 4), 0).save(buffer, "PNG", transparency=0)

        stripped = core_file_uploads.strip_image_metadata(buffer.getvalue())

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.mode == "P"
            assert "transparency" in image.info

    def test_webp_loses_exif_and_keeps_format(self):
        exif = Image.Exif()
        exif[0x010F] = "TestCamera"
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buffer, "WEBP", exif=exif)

        stripped = core_file_uploads.strip_image_metadata(buffer.getvalue())

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.format == "WEBP"
        assert not images.has_metadata(stripped)

    def test_the_icc_profile_is_kept(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buffer, "JPEG", icc_profile=profile)

        stripped = core_file_uploads.strip_image_metadata(buffer.getvalue())

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.info["icc_profile"] == profile

    def test_max_dimension_downsizes_the_long_edge_keeping_the_ratio(self):
        buffer = io.BytesIO()
        Image.new("RGB", (400, 200)).save(buffer, "PNG")

        stripped = core_file_uploads.strip_image_metadata(buffer.getvalue(), max_dimension=100)

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.size == (100, 50)

    def test_max_dimension_never_upscales(self):
        buffer = io.BytesIO()
        Image.new("RGB", (40, 20)).save(buffer, "PNG")

        stripped = core_file_uploads.strip_image_metadata(buffer.getvalue(), max_dimension=512)

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.size == (40, 20)

    def test_undecodable_bytes_are_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            core_file_uploads.strip_image_metadata(b"not an image")

    def test_a_truncated_image_is_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            core_file_uploads.strip_image_metadata(images.jpeg_with_exif()[:200])

    def test_a_format_that_cannot_be_rewritten_is_refused(self):
        buffer = io.BytesIO()
        Image.new("P", (4, 4)).save(buffer, "GIF")

        with pytest.raises(core_exceptions.InvalidInputError):
            core_file_uploads.strip_image_metadata(buffer.getvalue())

    @pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
    def test_an_image_over_the_pixel_cap_is_refused(self):
        buffer = io.BytesIO()
        Image.new("1", (20_000, 6_000)).save(buffer, "PNG")

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            core_file_uploads.strip_image_metadata(buffer.getvalue())
