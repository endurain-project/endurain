"""Tests for ``core.text_imports.read_bounded_csv``."""

from __future__ import annotations

from pathlib import Path

import pytest

import core.exceptions as core_exceptions
import core.text_imports as core_text_imports


def _write_csv(path: Path, rows: int, header: str = "name,value") -> None:
    """Write a tiny CSV file with ``rows`` data rows."""
    lines = [header]
    for i in range(rows):
        lines.append(f"row{i},val{i}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_bounded_csv_yields_rows(tmp_path: Path):
    """Well-formed CSV yields a dict per data row."""
    csv_path = tmp_path / "ok.csv"
    _write_csv(csv_path, rows=3)

    rows = list(core_text_imports.read_bounded_csv(csv_path))

    assert [r["name"] for r in rows] == ["row0", "row1", "row2"]
    assert rows[0]["value"] == "val0"


def test_read_bounded_csv_handles_utf8_bom(tmp_path: Path):
    """UTF-8 BOM headers are normalized by default."""
    csv_path = tmp_path / "bom.csv"
    csv_path.write_text("\ufeffname,value\nrow0,val0\n", encoding="utf-8")

    rows = list(core_text_imports.read_bounded_csv(csv_path))

    assert rows == [{"name": "row0", "value": "val0"}]


def test_read_bounded_csv_rejects_oversized_file(tmp_path: Path):
    """File larger than max_bytes raises 413 before any rows yielded."""
    csv_path = tmp_path / "big.csv"
    _write_csv(csv_path, rows=10)

    with pytest.raises(core_exceptions.DomainError) as exc:
        list(core_text_imports.read_bounded_csv(csv_path, max_bytes=10))
    assert exc.value.status_code == 413


def test_read_bounded_csv_enforces_row_cap(tmp_path: Path):
    """File exceeding max_rows raises 413 mid-iteration."""
    csv_path = tmp_path / "many.csv"
    _write_csv(csv_path, rows=20)

    with pytest.raises(core_exceptions.DomainError) as exc:
        list(core_text_imports.read_bounded_csv(csv_path, max_rows=5))
    assert exc.value.status_code == 413


def test_read_bounded_csv_missing_file_raises_424(tmp_path: Path):
    """A missing file is reported as failed dependency."""
    missing = tmp_path / "nope.csv"
    with pytest.raises(core_exceptions.DomainError) as exc:
        list(core_text_imports.read_bounded_csv(missing))
    assert exc.value.status_code == 424
