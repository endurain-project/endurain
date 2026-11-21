"""How a profile transfer failure becomes an answer, and which failures are worth running again."""

import pytest
from fastapi import status
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.users.users_profile.exceptions as profile_exceptions

_E = profile_exceptions


@pytest.mark.parametrize(
    ("error", "http_status", "message"),
    [
        (_E.DatabaseConnectionError(), status.HTTP_503_SERVICE_UNAVAILABLE, "Database connection failed"),
        (_E.ZipCreationError(), status.HTTP_422_UNPROCESSABLE_CONTENT, "Failed to create export archive"),
        (_E.DataCollectionError(), status.HTTP_422_UNPROCESSABLE_CONTENT, "Data collection failed"),
        (_E.ExportTimeoutError(), status.HTTP_408_REQUEST_TIMEOUT, "timed out"),
        (_E.ImportValidationError("invalid data"), status.HTTP_400_BAD_REQUEST, "invalid data"),
        (_E.FileFormatError("not a zip"), status.HTTP_400_BAD_REQUEST, "not a zip"),
        (_E.DataIntegrityError("mismatch"), status.HTTP_422_UNPROCESSABLE_CONTENT, "mismatch"),
        (_E.ImportTimeoutError(), status.HTTP_408_REQUEST_TIMEOUT, "timed out"),
        (_E.DiskSpaceError(), status.HTTP_507_INSUFFICIENT_STORAGE, "Insufficient disk space"),
        (_E.FileSizeError("too big"), status.HTTP_413_CONTENT_TOO_LARGE, "too big"),
        (_E.ActivityLimitError("too many"), status.HTTP_413_CONTENT_TOO_LARGE, "too many"),
        (_E.ZipStructureError("bad zip"), status.HTTP_400_BAD_REQUEST, "bad zip"),
        (_E.JSONParseError("parse fail"), status.HTTP_400_BAD_REQUEST, "parse fail"),
        (_E.SchemaValidationError("bad schema"), status.HTTP_400_BAD_REQUEST, "bad schema"),
        (_E.FileSystemError(), status.HTTP_507_INSUFFICIENT_STORAGE, "File system error"),
        (_E.MemoryAllocationError("OOM"), status.HTTP_507_INSUFFICIENT_STORAGE, "Insufficient memory"),
        (ValueError("something unexpected"), status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error"),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else None,
)
def test_each_failure_becomes_the_answer_that_names_it(error, http_status, message):
    result = profile_exceptions.to_domain_error(error, "profile data export")

    assert isinstance(result, core_exceptions.DomainError)
    assert result.status_code == http_status
    assert message in str(result.detail)
    assert "profile data export" in str(result.detail)


def test_an_unexpected_error_does_not_leak_its_message():
    result = profile_exceptions.to_domain_error(ValueError("secret detail"), "import")

    assert "secret detail" not in str(result.detail)


class TestIsTransient:
    @pytest.mark.parametrize(
        "error",
        [
            OperationalError("s", {}, Exception("db down")),
            OSError("disk"),
            core_exceptions.ServiceUnavailableError("x"),
        ],
        ids=["database", "storage", "unavailable"],
    )
    def test_a_database_storage_or_availability_failure_may_pass_on_its_own(self, error):
        assert profile_exceptions.is_transient(error) is True

    @pytest.mark.parametrize(
        "error",
        [_E.FileFormatError("x"), _E.FileSizeError("x"), _E.ImportTimeoutError("x"), ValueError("x")],
        ids=["format", "size", "timeout", "other"],
    )
    def test_the_archives_own_faults_and_limits_are_final(self, error):
        assert profile_exceptions.is_transient(error) is False

    def test_the_cause_chain_is_read(self):
        try:
            try:
                raise OperationalError("s", {}, Exception("db down"))
            except OperationalError as database_error:
                raise _E.DataCollectionError("Failed to collect gears") from database_error
        except _E.DataCollectionError as wrapped:
            assert profile_exceptions.is_transient(wrapped) is True
