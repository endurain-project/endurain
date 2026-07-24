"""Activity file-parser registry.

Maps a file extension to the parser that turns one on-disk activity file into
the shared ``parsed_info`` dict the ingestion core consumes. This replaces the
hard-coded ``if/elif`` extension chain that used to live in the ingestion
orchestrator, so supporting a new file format is a **registration** here rather
than an edit to the dispatch logic — the extension point the "future sources"
architecture needs.

Each registered parser is exposed through the uniform :class:`FileParser`
signature ``(path, user_id, activity_name) -> dict``; the thin adapters below
absorb the per-parser differences (GPX returns a ``TypedDict`` normalized to a
plain ``dict``; FIT's parse stage is owner-agnostic and ignores ``user_id``, the
owner being attached later when ``create_activity_objects`` builds the
``ActivityCore``). The parsers stay pure of db/domain/provider coupling
(enforced by the ``activity-file-import-purity`` import-linter contract); this
module only imports the sibling parser modules.

Note:
    Parsers currently read from a filesystem path. Migrating them to a pure
    ``bytes``/``BinaryIO`` contract (so file I/O lives entirely in the ingestion
    adapter) is a follow-up: FIT's two-stage parse and TCX's path-only reader
    make it a larger, separate change. The registry is the seam that migration
    would slot into without touching the orchestrator's dispatch again.
"""

from typing import Any, Protocol

import modules.activities.activity_file_import.utils_fit as fit_utils
import modules.activities.activity_file_import.utils_gpx as gpx_utils
import modules.activities.activity_file_import.utils_tcx as tcx_utils


class FileParser(Protocol):
    """Callable that parses one activity file into the shared ``parsed_info`` dict."""

    def __call__(self, path: str, user_id: int, activity_name: str | None = None) -> dict[str, Any]:
        """Parse the file at ``path`` for ``user_id`` into a ``parsed_info`` dict."""
        ...


def _parse_gpx(path: str, user_id: int, activity_name: str | None = None) -> dict[str, Any]:
    """Adapter: parse a GPX file, normalizing the ``TypedDict`` to a plain dict."""
    return dict(gpx_utils.parse_gpx_file(path, user_id, activity_name))


def _parse_tcx(path: str, user_id: int, activity_name: str | None = None) -> dict[str, Any]:
    """Adapter: parse a TCX file into a ``parsed_info`` dict."""
    return tcx_utils.parse_tcx_file(path, user_id, activity_name)


def _parse_fit(path: str, user_id: int, activity_name: str | None = None) -> dict[str, Any]:
    """Adapter: parse a FIT file.

    FIT's parse stage is owner-agnostic — the owner is attached later when
    ``create_activity_objects`` builds the ``ActivityCore`` — so ``user_id`` is
    accepted (for the uniform :class:`FileParser` signature) but not used here.
    """
    return fit_utils.parse_fit_file(path, activity_name)


_PARSERS: dict[str, FileParser] = {
    ".gpx": _parse_gpx,
    ".tcx": _parse_tcx,
    ".fit": _parse_fit,
}


def get_parser(file_extension: str) -> FileParser | None:
    """Return the parser registered for a file extension, or None if unsupported.

    Args:
        file_extension: The file extension, including the leading dot
            (case-insensitive), e.g. ``".gpx"``.

    Returns:
        The registered :class:`FileParser`, or ``None`` when the extension has
        no registered parser.
    """
    return _PARSERS.get(file_extension.lower())


def supported_extensions() -> tuple[str, ...]:
    """Return the file extensions with a registered parser.

    Returns:
        The registered/parseable extensions, e.g. ``(".gpx", ".tcx", ".fit")``.
    """
    return tuple(_PARSERS)
