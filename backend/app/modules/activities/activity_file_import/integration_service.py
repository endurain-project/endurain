"""Public parser-registry operations for activity files."""

import modules.activities.activity_file_import.parser_registry as activity_file_import_parser_registry
import modules.activities.activity_file_import.parser_utils as activity_file_import_parser_utils

FileParser = activity_file_import_parser_registry.FileParser


def get_parser(file_extension: str) -> FileParser | None:
    """Return the parser registered for a file extension.

    Args:
        file_extension: The file extension, including the dot.

    Returns:
        The parser, or None when the extension is unsupported.
    """
    return activity_file_import_parser_registry.get_parser(file_extension)


def supported_extensions() -> tuple[str, ...]:
    """Return the file extensions accepted by the parser registry.

    Returns:
        The accepted extensions.
    """
    return activity_file_import_parser_registry.supported_extensions()


def auto_lap_distance_km(imperial: bool) -> float:
    """Return the distance of an automatic lap in the athlete's units.

    Args:
        imperial: Whether the athlete uses imperial units.

    Returns:
        One mile in km for imperial athletes, 1 km otherwise.
    """
    return (
        activity_file_import_parser_utils.KM_PER_MILE
        if imperial
        else activity_file_import_parser_utils.DEFAULT_LAP_DISTANCE_KM
    )
