"""Every real fixture and synthetic case the decoders accept, decoded once into a recording.

The encoder round-trip tests run over these, so every device file and edge case that decodes is also written back out
and read again.
"""

import functools
import tempfile
from collections.abc import Callable
from pathlib import Path

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.fit_decoder as fit_decoder
import modules.activities.activity_file_import.gpx_decoder as gpx_decoder
import modules.activities.activity_file_import.recording as recording
import modules.activities.activity_file_import.tcx_decoder as tcx_decoder
from tests.activities.activity_file_import import synthetic_files

_FIXTURES = Path(__file__).parent / "fixtures"
_DECODERS: dict[str, Callable[[str], recording.Recording]] = {
    ".gpx": gpx_decoder.decode_gpx,
    ".tcx": tcx_decoder.decode_tcx,
    ".fit": fit_decoder.decode_fit,
}


@functools.cache
def recordings() -> dict[str, recording.Recording]:
    """Decode every real fixture and synthetic case, leaving out those the decoders refuse.

    Returns:
        Each recording by its path relative to ``fixtures/``; a synthetic case is ``synthetic/<format>/<name>``.
    """
    decoded: dict[str, recording.Recording] = {}
    for path in sorted(_FIXTURES.rglob("*")):
        if path.suffix in _DECODERS:
            _keep(decoded, path.relative_to(_FIXTURES).as_posix(), path)
    with tempfile.TemporaryDirectory() as folder:
        for name, build in synthetic_files.CASES.items():
            path = Path(folder) / Path(name).name
            path.write_bytes(build())
            _keep(decoded, f"synthetic/{name}", path)
    return decoded


def _keep(decoded: dict[str, recording.Recording], name: str, path: Path) -> None:
    """Decode a file into ``decoded`` unless its decoder refuses it.

    Args:
        decoded: The recordings so far; updated in place.
        name: The file's name in ``decoded``.
        path: The file.
    """
    try:
        decoded[name] = _DECODERS[path.suffix](str(path))
    except core_exceptions.DomainError:
        return
