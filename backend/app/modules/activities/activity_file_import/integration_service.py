"""Public parser-registry operations for activity files."""

import modules.activities.activity_file_import.parser_registry as activity_file_import_parser_registry

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
