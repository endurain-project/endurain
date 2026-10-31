"""Reading a bulk-import archive member by member: listing, capped copy, text uploads."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import UploadFile

import core.exceptions as core_exceptions
import core.file_uploads as file_uploads


def _zip(tmp_path: Path, members: dict[str, bytes], *, symlink: str | None = None) -> Path:
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16) | 0x10
            archive.writestr(info, "target")
    return path


class TestListZipMembers:
    def test_lists_regular_files_with_their_sizes_and_skips_directories(self, tmp_path):
        archive = _zip(tmp_path, {"a.fit": b"123", "dir/": b"", "dir/b.gpx": b"45"})

        members = file_uploads.list_zip_members(archive)

        assert [(m.name, m.size) for m in members] == [("a.fit", 3), ("dir/b.gpx", 2)]

    @pytest.mark.parametrize("name", ["../evil.fit", "/abs.fit", "a/../../b.fit", "C:/win.fit"])
    def test_an_entry_that_could_escape_is_refused(self, tmp_path, name):
        archive = _zip(tmp_path, {name: b"x"})

        with pytest.raises(core_exceptions.InvalidInputError):
            file_uploads.list_zip_members(archive)

    def test_a_symlink_entry_is_refused(self, tmp_path):
        archive = _zip(tmp_path, {"a.fit": b"x"}, symlink="link.fit")

        with pytest.raises(core_exceptions.InvalidInputError):
            file_uploads.list_zip_members(archive)

    def test_too_many_entries_are_refused_before_any_is_read(self, tmp_path):
        archive = _zip(tmp_path, {f"{n}.fit": b"x" for n in range(5)})

        with pytest.raises(core_exceptions.InvalidInputError):
            file_uploads.list_zip_members(archive, max_entries=4)

    def test_an_entry_beyond_the_size_cap_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(file_uploads, "_MAX_EXTRACTED_ENTRY_BYTES", 2)
        archive = _zip(tmp_path, {"a.fit": b"123"})

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            file_uploads.list_zip_members(archive)

    def test_a_total_beyond_the_cap_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(file_uploads, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 4)
        archive = _zip(tmp_path, {"a.fit": b"123", "b.fit": b"456"})

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            file_uploads.list_zip_members(archive)

    def test_something_that_is_not_a_zip_is_refused(self, tmp_path):
        path = tmp_path / "x.zip"
        path.write_bytes(b"not a zip")

        with pytest.raises(core_exceptions.InvalidInputError):
            file_uploads.list_zip_members(path)


class TestCopyZipMember:
    def test_writes_the_member_to_a_path_the_caller_chose(self, tmp_path):
        archive = _zip(tmp_path, {"deep/../name.fit": b"data"})
        destination = tmp_path / "out.bin"

        with zipfile.ZipFile(archive) as zf:
            written = file_uploads.copy_zip_member(zf, "deep/../name.fit", destination)

        assert (written, destination.read_bytes()) == (4, b"data")

    def test_a_member_that_inflates_beyond_the_cap_is_cut_and_removed(self, tmp_path):
        archive = _zip(tmp_path, {"a.fit": b"x" * 100})
        destination = tmp_path / "out.bin"

        with zipfile.ZipFile(archive) as zf, pytest.raises(core_exceptions.PayloadTooLargeError):
            file_uploads.copy_zip_member(zf, "a.fit", destination, max_bytes=10)

        assert not destination.exists()

    def test_a_missing_member_is_an_input_error(self, tmp_path):
        archive = _zip(tmp_path, {"a.fit": b"x"})

        with zipfile.ZipFile(archive) as zf, pytest.raises(core_exceptions.InvalidInputError):
            file_uploads.copy_zip_member(zf, "nope.fit", tmp_path / "out.bin")


class TestSaveTextUpload:
    def test_streams_to_a_server_named_file(self, tmp_path):
        upload = UploadFile(filename="../../etc/passwd", file=io.BytesIO(b"a,b\n1,2\n"))

        path = file_uploads.save_text_upload_sync(upload, upload_dir=str(tmp_path), filename="gear.csv", max_bytes=100)

        assert Path(path) == tmp_path / "gear.csv"
        assert Path(path).read_bytes() == b"a,b\n1,2\n"

    def test_an_upload_over_the_cap_is_refused_and_leaves_nothing(self, tmp_path):
        upload = UploadFile(filename="gear.csv", file=io.BytesIO(b"x" * 50))

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            file_uploads.save_text_upload_sync(upload, upload_dir=str(tmp_path), filename="gear.csv", max_bytes=10)

        assert list(tmp_path.iterdir()) == []
