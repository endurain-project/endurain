"""Tests for the durable-jobs admin route handlers."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import modules.server_settings.jobs_router as jobs_router


class TestReadJobsSummary:
    def test_delegates_with_hours(self):
        sentinel = MagicMock()
        with patch(
            "modules.server_settings.jobs_router.jasil_admin.get_jobs_summary", return_value=sentinel
        ) as get_summary:
            result = jobs_router.read_jobs_summary(_check_scopes=None, hours=12)
        assert result is sentinel
        get_summary.assert_called_once_with(hours=12)

    def test_defaults_to_24_hours(self):
        with patch("modules.server_settings.jobs_router.jasil_admin.get_jobs_summary") as get_summary:
            jobs_router.read_jobs_summary(_check_scopes=None)
        get_summary.assert_called_once_with(hours=24)


class TestReplayDeadLetterJob:
    def test_returns_result_when_replayed(self):
        outcome = MagicMock(replayed=True)
        with patch(
            "modules.server_settings.jobs_router.jasil_admin.replay_dead_letter_job", return_value=outcome
        ) as replay:
            result = jobs_router.replay_dead_letter_job(job_id="j1", _check_scopes=None)
        assert result is outcome
        replay.assert_called_once_with("j1")

    def test_404_when_not_found(self):
        with (
            patch(
                "modules.server_settings.jobs_router.jasil_admin.replay_dead_letter_job",
                return_value=MagicMock(replayed=False),
            ),
            pytest.raises(HTTPException) as excinfo,
        ):
            jobs_router.replay_dead_letter_job(job_id="nope", _check_scopes=None)
        assert excinfo.value.status_code == 404
