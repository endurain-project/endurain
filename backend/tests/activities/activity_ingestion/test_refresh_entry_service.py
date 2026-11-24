"""A refresh asks every linked provider, and a provider that fails is reported the way its failure deserves."""

import logging
import uuid

import psycopg
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.provider_registry as ingestion_provider_registry
import modules.activities.activity_ingestion.refresh_entry_service as refresh_entry_service
from tests._helpers import database as test_database

_USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000d1")


def _register(name: str, error: BaseException | None, asked: list[str]) -> None:
    def fetch_window(user_id, window_start, window_end):
        asked.append(name)
        if error is not None:
            raise error
        return []

    ingestion_provider_registry.register(
        ingestion_provider_registry.ActivityProvider(name, fetch_window, lambda *_args, **_kwargs: iter(()))
    )


def _failures(app_log) -> list[logging.LogRecord]:
    return [record for record in app_log.records if record.getMessage().startswith("Provider refresh failed")]


class TestAFailingProvider:
    def test_a_database_outage_is_a_warning_and_is_raised_once_every_provider_was_asked(self, db, providers, app_log):
        asked: list[str] = []
        _register("down", test_database.lost_connection_error(), asked)
        _register("fine", None, asked)

        # The outage stays the cause, so the job runner defers the refresh instead of spending an attempt.
        with pytest.raises(core_exceptions.ProcessingError) as raised:
            refresh_entry_service.sync_linked_providers(_USER_ID)

        assert isinstance(raised.value.__cause__, OperationalError)
        assert asked == ["down", "fine"]
        [record] = _failures(app_log)
        assert record.levelno == logging.WARNING
        assert record.exc_info is None
        assert (record.provider, record.error) == ("down", "OperationalError")

    @pytest.mark.parametrize(
        "error",
        [
            ValueError("unexpected payload"),
            IntegrityError("INSERT", {}, psycopg.errors.UniqueViolation("duplicate key")),
        ],
        ids=["defect", "database-refusal"],
    )
    def test_any_other_failure_is_an_error_with_its_traceback(self, providers, app_log, error):
        asked: list[str] = []
        _register("broken", error, asked)

        with pytest.raises(core_exceptions.ProcessingError) as raised:
            refresh_entry_service.sync_linked_providers(_USER_ID)

        assert raised.value.__cause__ is error

        [record] = _failures(app_log)
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
