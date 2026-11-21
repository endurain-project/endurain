"""The profile photo in the export: read through the storage provider, skipped when it cannot be read."""

import io
import uuid
import zipfile

import pytest
from jasil.providers import StorageBackendUnavailableError

import modules.users.users.constants as users_constants
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_media_service as export_media_service
import modules.users.users_profile.utils as profile_utils
from tests._factories.profile import FaultyStorage

_AREA = users_constants.USER_IMAGE_STORAGE_AREA
_USER_ID = uuid.UUID(int=1)


@pytest.fixture
def storage(_publish_local_platform):
    return _publish_local_platform.storage


def _export(storage, *, memory_limit_mb: int = 1_000_000):
    """Write the user's photos into an archive and return its entries and the counts."""
    counts = profile_utils.initialize_operation_counts(include_user_count=True)
    config = profile_utils.BasePerformanceConfig(max_memory_mb=memory_limit_mb)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipf:
        export_media_service.add_user_images_to_zip(zipf, _USER_ID, storage, counts, config)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as zipf:
        return {name: zipf.read(name) for name in zipf.namelist()}, counts


def test_a_user_without_a_stored_photo_exports_none(storage):
    entries, counts = _export(storage)

    assert entries == {}
    assert counts["user_images"] == 0


def test_the_photo_is_written_under_its_key_and_counted(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"image-bytes")

    entries, counts = _export(storage)

    assert entries == {f"user_images/{_USER_ID}.png": b"image-bytes"}
    assert counts["user_images"] == 1


def test_only_the_owners_photo_is_listed(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"mine")
    storage.save(_AREA, f"{uuid.UUID(int=2)}.png", b"theirs")
    storage.save(_AREA, f"{uuid.UUID(int=10)}.png", b"another")

    entries, _ = _export(storage)

    assert list(entries) == [f"user_images/{_USER_ID}.png"]


def test_a_large_photo_is_still_exported_and_the_memory_limit_is_checked_for_it(storage):
    big = b"x" * (11 * 1024 * 1024)
    storage.save(_AREA, f"{_USER_ID}.png", big)

    entries, counts = _export(storage)

    assert len(entries[f"user_images/{_USER_ID}.png"]) == len(big)
    assert counts["user_images"] == 1


def test_a_large_photo_over_the_memory_limit_stops_the_export(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"x" * (6 * 1024 * 1024))

    with pytest.raises(profile_exceptions.MemoryAllocationError):
        _export(storage, memory_limit_mb=0)


def test_a_listing_failure_skips_the_photo_and_is_not_raised(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"image-bytes")
    unreachable = FaultyStorage(storage, faults={"list_keys": StorageBackendUnavailableError("down")})

    entries, counts = _export(unreachable)

    assert entries == {}
    assert counts["user_images"] == 0


def test_a_read_failure_skips_only_that_photo(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"png")
    storage.save(_AREA, f"{_USER_ID}.webp", b"webp")
    flaky = FaultyStorage(storage, key_faults={("get", f"{_USER_ID}.png"): StorageBackendUnavailableError("down")})

    entries, counts = _export(flaky)

    assert entries == {f"user_images/{_USER_ID}.webp": b"webp"}
    assert counts["user_images"] == 1


def test_a_photo_listed_but_gone_is_skipped(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"png")

    class Vanishing(FaultyStorage):
        def __getattr__(self, name):
            if name == "get":
                return lambda area, key: None
            return super().__getattr__(name)

    entries, counts = _export(Vanishing(storage))

    assert entries == {}
    assert counts["user_images"] == 0


def test_an_unexpected_listing_error_is_not_swallowed(storage):
    broken = FaultyStorage(storage, faults={"list_keys": RuntimeError("bug")})

    with pytest.raises(RuntimeError, match="bug"):
        _export(broken)


def test_an_unexpected_read_error_is_not_swallowed(storage):
    storage.save(_AREA, f"{_USER_ID}.png", b"png")
    broken = FaultyStorage(storage, key_faults={("get", f"{_USER_ID}.png"): RuntimeError("bug")})

    with pytest.raises(RuntimeError, match="bug"):
        _export(broken)
