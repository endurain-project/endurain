"""Tests for profile exception classes and handler."""

import pytest
from fastapi import HTTPException, status

import modules.users.users_profile.exceptions as profile_exceptions


class TestProfileOperationError:
    """Test suite for ProfileOperationError base exception."""

    def test_can_be_raised(self):
        with pytest.raises(profile_exceptions.ProfileOperationError):
            raise profile_exceptions.ProfileOperationError()

    def test_is_exception_subclass(self):
        assert issubclass(profile_exceptions.ProfileOperationError, Exception)

    def test_with_message(self):
        error = profile_exceptions.ProfileOperationError("test message")
        assert str(error) == "test message"


class TestExportError:
    """Test suite for ExportError exception."""

    def test_is_profile_operation_error_subclass(self):
        assert issubclass(profile_exceptions.ExportError, profile_exceptions.ProfileOperationError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileOperationError):
            raise profile_exceptions.ExportError()


class TestProfileImportError:
    """Test suite for ProfileImportError exception."""

    def test_is_profile_operation_error_subclass(self):
        assert issubclass(profile_exceptions.ProfileImportError, profile_exceptions.ProfileOperationError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileOperationError):
            raise profile_exceptions.ProfileImportError()


class TestDatabaseConnectionError:
    """Test suite for DatabaseConnectionError exception."""

    def test_is_export_error_subclass(self):
        assert issubclass(profile_exceptions.DatabaseConnectionError, profile_exceptions.ExportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileOperationError):
            raise profile_exceptions.DatabaseConnectionError()


class TestFileSystemError:
    """Test suite for FileSystemError exception."""

    def test_is_profile_operation_error_subclass(self):
        assert issubclass(profile_exceptions.FileSystemError, profile_exceptions.ProfileOperationError)

    def test_can_be_raised(self):
        with pytest.raises(profile_exceptions.FileSystemError):
            raise profile_exceptions.FileSystemError()


class TestZipCreationError:
    """Test suite for ZipCreationError exception."""

    def test_is_export_error_subclass(self):
        assert issubclass(profile_exceptions.ZipCreationError, profile_exceptions.ExportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ExportError):
            raise profile_exceptions.ZipCreationError()


class TestMemoryAllocationError:
    """Test suite for MemoryAllocationError exception."""

    def test_is_profile_operation_error_subclass(self):
        assert issubclass(profile_exceptions.MemoryAllocationError, profile_exceptions.ProfileOperationError)

    def test_can_be_raised(self):
        with pytest.raises(profile_exceptions.MemoryAllocationError):
            raise profile_exceptions.MemoryAllocationError("memory exceeded")


class TestDataCollectionError:
    """Test suite for DataCollectionError exception."""

    def test_is_export_error_subclass(self):
        assert issubclass(profile_exceptions.DataCollectionError, profile_exceptions.ExportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ExportError):
            raise profile_exceptions.DataCollectionError()


class TestExportTimeoutError:
    """Test suite for ExportTimeoutError exception."""

    def test_is_export_error_subclass(self):
        assert issubclass(profile_exceptions.ExportTimeoutError, profile_exceptions.ExportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ExportError):
            raise profile_exceptions.ExportTimeoutError()


class TestImportValidationError:
    """Test suite for ImportValidationError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.ImportValidationError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.ImportValidationError()


class TestFileFormatError:
    """Test suite for FileFormatError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.FileFormatError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.FileFormatError()


class TestDataIntegrityError:
    """Test suite for DataIntegrityError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.DataIntegrityError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.DataIntegrityError()


class TestImportTimeoutError:
    """Test suite for ImportTimeoutError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.ImportTimeoutError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.ImportTimeoutError()


class TestDiskSpaceError:
    """Test suite for DiskSpaceError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.DiskSpaceError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.DiskSpaceError()


class TestFileSizeError:
    """Test suite for FileSizeError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.FileSizeError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.FileSizeError()


class TestActivityLimitError:
    """Test suite for ActivityLimitError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.ActivityLimitError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.ActivityLimitError()


class TestZipStructureError:
    """Test suite for ZipStructureError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.ZipStructureError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.ZipStructureError()


class TestJSONParseError:
    """Test suite for JSONParseError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.JSONParseError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.JSONParseError()


class TestSchemaValidationError:
    """Test suite for SchemaValidationError exception."""

    def test_is_profile_import_error_subclass(self):
        assert issubclass(profile_exceptions.SchemaValidationError, profile_exceptions.ProfileImportError)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(profile_exceptions.ProfileImportError):
            raise profile_exceptions.SchemaValidationError()


class TestHandleImportExportException:
    """Test suite for handle_import_export_exception function."""

    def test_database_connection_error(self):
        error = profile_exceptions.DatabaseConnectionError()
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert isinstance(result, HTTPException)
        assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Database connection failed" in str(result.detail)

    def test_zip_creation_error(self):
        error = profile_exceptions.ZipCreationError()
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert result.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "Failed to create export archive" in str(result.detail)

    def test_data_collection_error(self):
        error = profile_exceptions.DataCollectionError()
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert result.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "Data collection failed" in str(result.detail)

    def test_export_timeout_error(self):
        error = profile_exceptions.ExportTimeoutError()
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert result.status_code == status.HTTP_408_REQUEST_TIMEOUT
        assert "timed out" in str(result.detail)

    def test_import_validation_error(self):
        error = profile_exceptions.ImportValidationError("invalid data")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid data" in str(result.detail)

    def test_file_format_error(self):
        error = profile_exceptions.FileFormatError("not a zip")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "not a zip" in str(result.detail)

    def test_data_integrity_error(self):
        error = profile_exceptions.DataIntegrityError("mismatch")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "mismatch" in str(result.detail)

    def test_import_timeout_error(self):
        error = profile_exceptions.ImportTimeoutError()
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_408_REQUEST_TIMEOUT
        assert "timed out" in str(result.detail)

    def test_disk_space_error(self):
        error = profile_exceptions.DiskSpaceError()
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_507_INSUFFICIENT_STORAGE
        assert "Insufficient disk space" in str(result.detail)

    def test_file_size_error(self):
        error = profile_exceptions.FileSizeError("too big")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert "too big" in str(result.detail)

    def test_activity_limit_error(self):
        error = profile_exceptions.ActivityLimitError("too many")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert "too many" in str(result.detail)

    def test_zip_structure_error(self):
        error = profile_exceptions.ZipStructureError("bad zip")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "bad zip" in str(result.detail)

    def test_json_parse_error(self):
        error = profile_exceptions.JSONParseError("parse fail")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "parse fail" in str(result.detail)

    def test_schema_validation_error(self):
        error = profile_exceptions.SchemaValidationError("bad schema")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "bad schema" in str(result.detail)

    def test_file_system_error(self):
        error = profile_exceptions.FileSystemError()
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert result.status_code == status.HTTP_507_INSUFFICIENT_STORAGE
        assert "File system error" in str(result.detail)

    def test_memory_allocation_error(self):
        error = profile_exceptions.MemoryAllocationError("OOM")
        result = profile_exceptions.handle_import_export_exception(error, "import")
        assert result.status_code == status.HTTP_507_INSUFFICIENT_STORAGE
        assert "Insufficient memory" in str(result.detail)

    def test_unexpected_error_fallback(self):
        error = ValueError("something unexpected")
        result = profile_exceptions.handle_import_export_exception(error, "export")
        assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unexpected error" in str(result.detail)

    def test_operation_string_included(self):
        error = profile_exceptions.DatabaseConnectionError()
        result = profile_exceptions.handle_import_export_exception(error, "profile data export")
        assert "profile data export" in str(result.detail)
