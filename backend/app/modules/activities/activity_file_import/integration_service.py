"""Public parser-registry operations for activity files."""

import modules.activities.activity_file_import.registry as parser_registry

FileParser = parser_registry.FileParser


def get_parser(file_extension: str) -> FileParser | None:
    """Return the parser registered for a file extension."""
    return parser_registry.get_parser(file_extension)


def supported_extensions() -> tuple[str, ...]:
    """Return the file extensions accepted by the parser registry."""
    return parser_registry.supported_extensions()
