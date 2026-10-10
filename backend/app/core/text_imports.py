"""Bounded readers for trusted-but-large text-import files.

CSV imports (Strava gear) read files that an operator placed in a
known directory. They are not "uploads" in the multipart sense, but
an oversized or malformed file could still exhaust memory. The
helpers here apply byte- and row-level caps before parsing so the
binary :mod:`core.file_uploads` pipeline does not need to grow text
parsing concerns.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException, status

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# Hard ceiling on a single CSV file size and row count. Strava
# exports of bikes/shoes are tiny in practice (kilobytes / dozens of
# rows). The defaults below are deliberately generous so legitimate
# operator imports never hit them, while still preventing a runaway
# file from reading hundreds of MiB into memory.
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_MAX_ROWS = 100_000


def _enforce_size(path: Path, max_bytes: int) -> None:
    """Raise HTTP 413 if ``path`` exceeds ``max_bytes``.

    Args:
        path: File to inspect.
        max_bytes: Maximum allowed file size in bytes.

    Raises:
        HTTPException: 413 when the file is too large.
    """
    try:
        size = path.stat().st_size
    except OSError as err:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={
                "message": f"Cannot stat import file {path.name}",
                "code": "TEXT_IMPORT_STAT_FAILED",
            },
        ) from err
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "message": (f"Import file {path.name} is {size} bytes, exceeds {max_bytes} byte cap"),
                "code": "TEXT_IMPORT_TOO_LARGE",
            },
        )


def read_bounded_csv(
    path: str | os.PathLike,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_rows: int = _DEFAULT_MAX_ROWS,
    encoding: str = "utf-8-sig",
) -> Iterator[dict[str, str]]:
    """Stream a CSV file as dicts with size and row caps enforced.

    Args:
        path: Path to the CSV file.
        max_bytes: Hard cap on file size before parsing begins.
        max_rows: Hard cap on number of data rows yielded.
        encoding: Text encoding used to open the file.

    Yields:
        One dictionary per data row (header → value).

    Raises:
        HTTPException: 413 when the file or row count exceeds caps,
            424 when the file cannot be stat'd or opened.
    """
    file_path = Path(os.fspath(path))
    _enforce_size(file_path, max_bytes)

    try:
        with open(file_path, encoding=encoding, newline="") as fh:
            reader = csv.DictReader(fh)
            for rows_yielded, row in enumerate(reader, start=1):
                if rows_yielded > max_rows:
                    raise HTTPException(
                        status_code=(status.HTTP_413_CONTENT_TOO_LARGE),
                        detail={
                            "message": (f"Import file {file_path.name} exceeds {max_rows} row cap"),
                            "code": "TEXT_IMPORT_TOO_MANY_ROWS",
                        },
                    )
                yield row
    except OSError as err:
        logger.error(f"read_bounded_csv failed to open {file_path.name}: {type(err).__name__}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={
                "message": (f"Failed to open import file {file_path.name}"),
                "code": "TEXT_IMPORT_OPEN_FAILED",
            },
        ) from err
