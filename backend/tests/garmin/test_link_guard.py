"""Tests for the Garmin Connect link flow guards in garmin.utils and garmin.router."""

from unittest.mock import MagicMock

import garminconnect
import pytest
from fastapi import HTTPException
from jasil.backends.state_memory import MemoryState

import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.router as garmin_router
import modules.garmin.schema as garmin_schema
import modules.garmin.utils as garmin_utils


def _store() -> mfa_code_store.GarminMFACodeStore:
    return mfa_code_store.GarminMFACodeStore(state=MemoryState())


class TestLinkConcurrencyGuard:
    """A second link for the same user must not start a second Garmin login."""

    @pytest.fixture(autouse=True)
    def _clear_links_in_progress(self):
        garmin_utils._links_in_progress.clear()
        yield
        garmin_utils._links_in_progress.clear()

    async def test_rejects_link_already_in_progress(self):
        garmin_utils._links_in_progress.add(1)

        with pytest.raises(HTTPException) as exc:
            await garmin_utils.link_garminconnect(1, "a@b.c", "pw", MagicMock(), _store(), MagicMock())

        assert exc.value.status_code == 409

    async def test_releases_guard_after_failed_login(self, monkeypatch):
        failing = MagicMock()
        failing.return_value.login.side_effect = garminconnect.GarminConnectAuthenticationError("bad")
        monkeypatch.setattr(garmin_utils.garminconnect, "Garmin", failing)

        with pytest.raises(HTTPException) as exc:
            await garmin_utils.link_garminconnect(1, "a@b.c", "pw", MagicMock(), _store(), MagicMock())

        assert exc.value.status_code == 424
        assert 1 not in garmin_utils._links_in_progress


class TestMfaCodeNormalisation:
    """Pasted or autofilled codes reach Garmin without separators."""

    @pytest.mark.parametrize("submitted", ["123456", " 123 456 ", "123-456", "123\t456\n"])
    async def test_strips_whitespace_and_dashes(self, submitted):
        store = _store()

        await garmin_router.garminconnect_mfa_code(
            garmin_schema.MFARequest(mfa_code=submitted),
            token_user_id=1,
            mfa_codes=store,
        )

        assert store.get_code(1) == "123456"
