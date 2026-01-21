"""Centralized file upload handling with security validation."""

import os
import glob

import aiofiles
import aiofiles.os
from fastapi import HTTPException, UploadFile, status
from safeuploads import FileValidator
from safeuploads.exceptions import FileValidationError

import core.logger as core_logger


async def save_file(file: UploadFile | bytes, upload_dir: str, filename: str) -> str:
    file_path = None
    try:

        # Ensure upload directory exists
        await aiofiles.os.makedirs(upload_dir, exist_ok=True)

        # Build full file path
        file_path = os.path.join(upload_dir, filename)

        # Save file asynchronously
        if isinstance(file, bytes):
            content = file
        else:
            content = await file.read()
        async with aiofiles.open(file_path, "wb") as save_file:
            await save_file.write(content)

        core_logger.print_to_log(f"File saved successfully: {file_path}", "debug")

        return file_path
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in save_file: {err}", "error", exc=err)

        # Remove the file if it was created
        if file_path and await aiofiles.os.path.exists(file_path):
            await aiofiles.os.remove(file_path)

        # Raise an HTTPException with a 500 Internal Server Error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        ) from err


async def save_image_file_and_validate_it(
    file: UploadFile, upload_dir: str, filename: str
) -> str:
    """
    Save an image file asynchronously with security validation.

    Validates file type via magic number, creates upload directory,
    saves file asynchronously, and cleans up on error.

    Security measures:
    - SafeUploads validates file type via magic number (not extension).
    - File size limit enforced (max configured image size).
    - Filename provided by caller (path traversal prevention).
    - Uploaded to isolated directory specified by caller.

    Args:
        file: Image file to upload (UploadFile).
        upload_dir: Directory to save file to.
        filename: Filename to save as (without directory path).

    Returns:
        Full file path where file was saved.

    Raises:
        HTTPException: 400 if file validation fails, 500 if
            write operation fails.
    """
    try:
        # Validate image file type and size
        file_validator = FileValidator()
        await file_validator.validate_image_file(file)

        # Save the validated image file
        return await save_file(file, upload_dir, filename)
    except FileValidationError as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in save_image_file_and_validate_it: {err}", "error", exc=err
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


async def delete_files_by_pattern(directory: str, pattern: str) -> None:
    """
    Delete files from filesystem matching a glob pattern asynchronously.

    Searches directory for files matching the pattern and removes
    them asynchronously. Silently skips files that no longer exist.

    Args:
        directory: Directory path to search in.
        pattern: Glob pattern to match (e.g., "user_123.*").

    Returns:
        None

    Raises:
        None - errors logged but not raised for resilience.
    """
    try:
        # Build full pattern path
        full_pattern = os.path.join(directory, pattern)

        # Find all files matching the pattern
        files_to_delete = glob.glob(full_pattern)

        # Remove each file found asynchronously
        for file_path in files_to_delete:
            try:
                if await aiofiles.os.path.exists(file_path):
                    await aiofiles.os.remove(file_path)

                core_logger.print_to_log(
                    f"File deleted successfully: {file_path}", "debug"
                )
            except OSError as err:
                core_logger.print_to_log(
                    f"Failed to delete file {file_path}: {err}",
                    "warning",
                    exc=err,
                )
    except Exception as err:
        core_logger.print_to_log(
            f"Error deleting files matching pattern {pattern}: {err}",
            "error",
            exc=err,
        )
