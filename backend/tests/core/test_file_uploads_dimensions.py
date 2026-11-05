"""Image uploads are bounded by their pixel count, which their byte size does not limit."""

import io

import pytest
from fastapi import UploadFile
from PIL import Image

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads


def _png(width: int, height: int) -> bytes:
    """Return a PNG of the given size; a blank 1-bit image stays tiny on disk whatever its dimensions."""
    buffer = io.BytesIO()
    Image.new("1", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def _validate(data: bytes) -> None:
    upload = UploadFile(file=io.BytesIO(data), filename="photo.png")
    try:
        core_file_uploads.read_validated_upload_sync(upload, kind=core_file_uploads.UploadKind.IMAGE)
    finally:
        upload.file.close()


def test_a_photo_of_ordinary_size_is_accepted():
    _validate(_png(4000, 3000))


def test_the_pixel_limit_itself_is_accepted():
    _validate(_png(10000, 10000))


@pytest.mark.parametrize("size", [(10001, 10000), (20000, 20000)])
def test_an_image_with_too_many_pixels_is_refused_as_too_large(size):
    with pytest.raises(core_exceptions.PayloadTooLargeError) as refused:
        _validate(_png(*size))

    assert refused.value.status_code == 413


def test_an_image_whose_header_cannot_be_read_is_refused_as_invalid():
    data = _png(10, 10)
    corrupt = data[:8] + b"\x00" * (len(data) - 8)

    with pytest.raises(core_exceptions.InvalidInputError):
        _validate(corrupt)


def test_the_upload_can_be_read_after_the_check():
    data = _png(10, 10)
    upload = UploadFile(file=io.BytesIO(data), filename="photo.png")

    core_file_uploads._validate_upload(upload, kind=core_file_uploads.UploadKind.IMAGE)

    assert upload.file.read() == data


def test_a_png_signature_without_a_readable_header_is_invalid():
    file = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    with pytest.raises(core_exceptions.InvalidInputError):
        core_file_uploads._check_image_pixels(file)
