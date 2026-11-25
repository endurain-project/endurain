"""Activity file-parser registry.

Maps a file extension to the parser that turns one on-disk activity file into a
:class:`~modules.activities.activity.contracts.ParsedFile` — the canonical,
format-agnostic result the ingestion core consumes. Supporting a new file
format is a **registration** here rather than an edit to the dispatch logic.

Each registered parser is exposed through the uniform :class:`FileParser`
signature ``(path, user_id, activity_name, default_timezone, lap_distance_km) -> ParsedFile``. A format's decoder
reads the file into a :class:`~modules.activities.activity_file_import.recording.Recording`, ``assembly`` turns every
session of the recording into an activity, and the adapter converts each into the canonical shape; only the decoder
differs per format. A FIT file also carries file-scoped exercise-title rows.

Returning a uniform ``ParsedFile`` is what keeps "how many activities are in this
file" a parser detail: the ingestion core iterates ``parsed_file.activities`` and
never branches on the extension.

The parsers stay pure of db/domain/provider coupling (enforced by the
``activity-file-import-purity`` import-linter contract); this module only imports
the sibling parser modules and the shared contracts.

Note:
    Decoders currently read from a filesystem path. Migrating them to a pure
    ``bytes``/``BinaryIO`` contract (so file I/O lives entirely in the ingestion
    adapter) is a follow-up. The registry is the seam that migration
    would slot into without touching the ingestion core's dispatch again.
"""

import uuid
from collections.abc import Callable
from typing import Protocol

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.adapter as activity_file_import_adapter
import modules.activities.activity_file_import.assembly as activity_file_import_assembly
import modules.activities.activity_file_import.fit_decoder as activity_file_import_fit_decoder
import modules.activities.activity_file_import.gpx_decoder as activity_file_import_gpx_decoder
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.tcx_decoder as activity_file_import_tcx_decoder


class FileParser(Protocol):
    """Callable that parses one activity file into a :class:`ParsedFile`."""

    def __call__(
        self,
        path: str,
        user_id: uuid.UUID,
        activity_name: str | None,
        default_timezone: str,
        lap_distance_km: float,
    ) -> activity_contracts.ParsedFile:
        """Parse the file at ``path`` for ``user_id``.

        ``default_timezone`` is the athlete's own IANA timezone, used only when the
        file yields no timezone of its own (no GPS track and no reported UTC
        offset). It is **passed in** rather than looked up so the parsers stay free
        of any ``modules.users`` coupling, as the purity contract requires.

        Args:
            path: Path of the file to parse.
            user_id: ID of the user the file belongs to.
            activity_name: Optional activity name override.
            default_timezone: Timezone to assume when the file carries none.
            lap_distance_km: Distance of an automatic lap; only used by formats without device laps.

        Returns:
            The parsed file.
        """
        ...


def _parser(decode: Callable[[str], activity_file_import_recording.Recording]) -> FileParser:
    """Build the parser of a format from its decoder.

    Args:
        decode: Reads a file of the format into a recording.

    Returns:
        A :class:`FileParser` that decodes the file and builds the activities of its sessions.
    """

    def parse(
        path: str,
        user_id: uuid.UUID,
        activity_name: str | None,
        default_timezone: str,
        lap_distance_km: float,
    ) -> activity_contracts.ParsedFile:
        """Parse the file at ``path`` for ``user_id``.

        Args:
            path: Path of the file to parse.
            user_id: ID of the user the file belongs to.
            activity_name: Optional activity name override.
            default_timezone: Timezone to assume when the file carries none.
            lap_distance_km: Distance of an automatic lap, for a session with no device laps.

        Returns:
            The parsed file, one entry per session and the multisport parent when the file has one.
        """
        recording = decode(path)
        assembled = activity_file_import_assembly.assemble(
            recording, user_id, activity_name, default_timezone, lap_distance_km
        )
        return activity_contracts.ParsedFile(
            activities=[
                activity_file_import_adapter.parsed_info_to_parsed_activity(payload) for payload in assembled.activities
            ],
            components={"exercise_titles": list(recording.exercise_titles)} if recording.format == "fit" else {},
            parent=None
            if assembled.parent is None
            else activity_file_import_adapter.parsed_info_to_parsed_activity(assembled.parent),
        )

    return parse


_PARSERS: dict[str, FileParser] = {
    ".gpx": _parser(activity_file_import_gpx_decoder.decode_gpx),
    ".tcx": _parser(activity_file_import_tcx_decoder.decode_tcx),
    ".fit": _parser(activity_file_import_fit_decoder.decode_fit),
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
