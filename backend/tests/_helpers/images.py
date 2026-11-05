"""In-memory images carrying metadata, for tests of the metadata strip."""

import io

from PIL import Image, PngImagePlugin

_ORIENTATION = 0x0112
_GPS_IFD = 0x8825


def exif_with_gps(orientation: int = 1) -> Image.Exif:
    """Return EXIF data carrying GPS coordinates and the given orientation.

    Args:
        orientation: The EXIF orientation value.

    Returns:
        The EXIF block.
    """
    exif = Image.Exif()
    exif[_ORIENTATION] = orientation
    exif[0x010F] = "TestCamera"
    gps = exif.get_ifd(_GPS_IFD)
    gps[1] = "N"
    gps[2] = (38.0, 42.0, 0.0)
    gps[3] = "W"
    gps[4] = (9.0, 8.0, 0.0)
    return exif


def jpeg_with_exif(size: tuple[int, int] = (40, 20), *, orientation: int = 1) -> bytes:
    """Return a JPEG carrying GPS EXIF and the given orientation tag.

    Args:
        size: Width and height of the stored pixels.
        orientation: The EXIF orientation value.

    Returns:
        The JPEG bytes.
    """
    exif = exif_with_gps(orientation)
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def png_with_text(size: tuple[int, int] = (8, 8), *, mode: str = "RGBA") -> bytes:
    """Return a PNG carrying a text chunk and, for ``RGBA``, a transparent pixel.

    Args:
        size: Width and height.
        mode: The Pillow mode to store.

    Returns:
        The PNG bytes.
    """
    info = PngImagePlugin.PngInfo()
    info.add_text("Location", "38.7,-9.1")
    image = Image.new(mode, size, (10, 20, 30, 0) if mode == "RGBA" else (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", pnginfo=info)
    return buffer.getvalue()


def has_metadata(data: bytes) -> bool:
    """Return whether an image still carries EXIF, XMP or PNG text.

    Args:
        data: The image bytes.

    Returns:
        True when any metadata is present.
    """
    with Image.open(io.BytesIO(data)) as image:
        return (
            bool(image.getexif())
            or bool(image.info.get("exif"))
            or bool(image.info.get("xmp"))
            or bool(getattr(image, "text", None))
        )


def webp_with_exif(size: tuple[int, int] = (40, 20), *, orientation: int = 1) -> bytes:
    """Return a WebP carrying GPS EXIF and the given orientation tag.

    Args:
        size: Width and height of the stored pixels.
        orientation: The EXIF orientation value.

    Returns:
        The WebP bytes.
    """
    exif = exif_with_gps(orientation)
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 30, 200)).save(buffer, "WEBP", exif=exif)
    return buffer.getvalue()


def gif(size: tuple[int, int] = (8, 8)) -> bytes:
    """Return a GIF image.

    Args:
        size: Width and height in pixels.

    Returns:
        The GIF bytes.
    """
    buffer = io.BytesIO()
    Image.new("P", size).save(buffer, "GIF")
    return buffer.getvalue()


def heic_like() -> bytes:
    """Return bytes with an ISO base media ``ftyp`` header naming the ``heic`` brand.

    Returns:
        A minimal HEIC-signature payload.
    """
    return b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
