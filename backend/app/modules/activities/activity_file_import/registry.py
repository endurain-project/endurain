"""Activity file-parser registry.

Maps a file extension to the parser that turns one on-disk activity file into a
:class:`~modules.activities.activity.contracts.ParsedFile` — the canonical,
format-agnostic result the ingestion core consumes. Supporting a new file
format is a **registration** here rather than an edit to the dispatch logic.

Each registered parser is exposed through the uniform :class:`FileParser`
signature ``(path, user_id, activity_name, default_timezone) -> ParsedFile``, and
the thin adapters below absorb every per-parser difference:

* GPX returns a ``TypedDict`` and TCX a plain dict, each describing exactly one
  activity.
* FIT parses in two stages and can describe **several** activities in one file,
  so its activity_file_import_adapter runs the split/build pipeline here rather than making the caller
  do it. It also carries file-scoped exercise-title rows.

Returning a uniform ``ParsedFile`` is what keeps "how many activities are in this
file" a parser detail: the ingestion core iterates ``parsed_file.activities`` and
never branches on the extension.

The parsers stay pure of db/domain/provider coupling (enforced by the
``activity-file-import-purity`` import-linter contract); this module only imports
the sibling parser modules and the shared contracts.

Note:
    Parsers currently read from a filesystem path. Migrating them to a pure
    ``bytes``/``BinaryIO`` contract (so file I/O lives entirely in the ingestion
    activity_file_import_adapter) is a follow-up: FIT's two-stage parse and TCX's path-only reader
    make it a larger, separate change. The registry is the seam that migration
    would slot into without touching the ingestion core's dispatch again.
"""

from typing import Protocol

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.adapter as activity_file_import_adapter
import modules.activities.activity_file_import.fit_utils as activity_file_import_fit_utils
import modules.activities.activity_file_import.gpx_utils as activity_file_import_gpx_utils
import modules.activities.activity_file_import.tcx_utils as activity_file_import_tcx_utils


class FileParser(Protocol):
    """Callable that parses one activity file into a :class:`ParsedFile`."""

    def __call__(
        self,
        path: str,
        user_id: int,
        activity_name: str | None,
        default_timezone: str,
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

        Returns:
            The parsed file.
        """
        ...


def _parse_gpx(
    path: str,
    user_id: int,
    activity_name: str | None,
    default_timezone: str,
) -> activity_contracts.ParsedFile:
    """Adapter: parse a GPX file into the single activity it describes.

    Args:
        path: Path of the GPX file.
        user_id: ID of the user the file belongs to.
        activity_name: Optional activity name override.
        default_timezone: Timezone to assume when the file carries none.

    Returns:
        The parsed file.
    """
    parsed_info = dict(
        activity_file_import_gpx_utils.parse_gpx_file(
            path, user_id, activity_name_input=activity_name, default_timezone=default_timezone
        )
    )
    return activity_contracts.ParsedFile(
        activities=[activity_file_import_adapter.parsed_info_to_parsed_activity(parsed_info)]
    )


def _parse_tcx(
    path: str,
    user_id: int,
    activity_name: str | None,
    default_timezone: str,
) -> activity_contracts.ParsedFile:
    """Adapter: parse a TCX file into the single activity it describes.

    Args:
        path: Path of the TCX file.
        user_id: ID of the user the file belongs to.
        activity_name: Optional activity name override.
        default_timezone: Timezone to assume when the file carries none.

    Returns:
        The parsed file.
    """
    parsed_info = activity_file_import_tcx_utils.parse_tcx_file(
        path, user_id, activity_name_input=activity_name, default_timezone=default_timezone
    )
    return activity_contracts.ParsedFile(
        activities=[activity_file_import_adapter.parsed_info_to_parsed_activity(parsed_info)]
    )


def _parse_fit(
    path: str,
    user_id: int,
    activity_name: str | None,
    default_timezone: str,
) -> activity_contracts.ParsedFile:
    """Adapter: parse a FIT file into the one *or more* activities it describes.

    FIT's first stage is owner- and timezone-agnostic; splitting the records into
    sessions and building each ``ActivityCore`` is the second stage, which is
    where the owner and the fallback timezone apply. Both stages run here so that
    a multi-session ``.fit`` looks exactly like a single-activity ``.gpx`` to the
    caller.

    Args:
        path: Path of the FIT file.
        user_id: ID of the user the file belongs to.
        activity_name: Optional activity name override.
        default_timezone: Timezone to assume when the file carries none.

    Returns:
        The parsed file, one entry per activity.
    """
    payload = activity_file_import_fit_utils.parse_fit_file(path, activity_name)
    sessions = activity_file_import_fit_utils.split_records_by_activity(payload)
    parsed_infos = activity_file_import_fit_utils.create_activity_objects(sessions, user_id, default_timezone)
    return activity_contracts.ParsedFile(
        activities=[
            activity_file_import_adapter.parsed_info_to_parsed_activity(parsed_info) for parsed_info in parsed_infos
        ],
        components={"exercise_titles": payload.get("exercise_titles")},
    )


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
