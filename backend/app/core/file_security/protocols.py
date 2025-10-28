"""
Framework-agnostic protocols for file upload handling.

This module defines protocols that allow safeuploads to work with any
web framework's file upload implementation without depending on specific
framework packages.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class UploadFileProtocol(Protocol):
    """
    Protocol for file upload objects from any web framework.

    This protocol defines the minimal interface required for file
    validation. Any object with these attributes and methods can be
    validated, regardless of the web framework being used.

    Attributes:
        filename: Original filename from the client.
        size: Size of the uploaded file in bytes.
    """

    filename: str | None
    size: int | None

    async def read(self, size: int = -1) -> bytes:
        """
        Read bytes from the uploaded file.

        Args:
            size: Number of bytes to read. -1 reads entire file.

        Returns:
            Bytes read from the file.
        """
        ...

    async def seek(self, offset: int) -> int:
        """
        Move file pointer to specified position.

        Args:
            offset: Position to move to in bytes.

        Returns:
            New position in the file.
        """
        ...
