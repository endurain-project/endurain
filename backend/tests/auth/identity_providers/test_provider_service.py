"""Administration of identity-provider configuration."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.provider_service as provider_service


def test_a_delete_that_races_past_the_version_check_is_a_precondition_failure(mock_db):
    with (
        patch.object(provider_service.idp_crud, "get_identity_provider", return_value=MagicMock()),
        patch.object(
            provider_service.identity_provider_links_integration,
            "check_user_identity_providers_by_idp_id",
            return_value=False,
        ),
        patch.object(provider_service.idp_crud, "delete_identity_provider", side_effect=StaleDataError("moved")),
        patch.object(provider_service.idp_crud, "identity_provider_exists", return_value=True),
        pytest.raises(core_exceptions.PreconditionFailedError),
    ):
        provider_service.delete_identity_provider(3, mock_db, if_match='"1"')

    mock_db.commit.assert_not_called()
