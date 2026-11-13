"""Scheduled work owned by identity providers runs on one replica at a time."""

from unittest.mock import patch

import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs


def test_each_sweep_holds_its_own_distributed_lock():
    jobs = idp_scheduled_jobs.recurring_jobs()

    assert [job.lock_name for job in jobs] == [
        idp_scheduled_jobs.ICON_SWEEP_LOCK_NAME,
        idp_scheduled_jobs.REVOCATION_SWEEP_LOCK_NAME,
    ]
    assert jobs[0].func is idp_scheduled_jobs.sweep_unreferenced_icons
    assert jobs[1].func is idp_scheduled_jobs.revoke_ended_session_tokens


@patch("modules.auth.identity_providers.scheduled_jobs.idp_token_revocation_service.IdpTokenRevocationService")
@patch("modules.auth.identity_providers.scheduled_jobs.idp_oidc_client.OidcClientService")
@patch("modules.auth.identity_providers.scheduled_jobs.platform_runtime")
def test_the_revocation_sweep_resolves_state_at_the_entry_point_and_covers_every_user(
    mock_runtime, mock_oidc, mock_service
):
    idp_scheduled_jobs.revoke_ended_session_tokens()

    mock_oidc.assert_called_once()
    assert mock_oidc.call_args.args[0] is mock_runtime.get_state.return_value
    mock_service.assert_called_once_with(mock_oidc.return_value)
    mock_service.return_value.revoke_ended_sessions.assert_called_once_with()


@patch("modules.auth.identity_providers.scheduled_jobs.idp_icon_service.sweep_unreferenced_icons")
@patch("modules.auth.identity_providers.scheduled_jobs.platform_runtime")
def test_the_icon_sweep_resolves_storage_at_the_entry_point(mock_runtime, mock_sweep):
    idp_scheduled_jobs.sweep_unreferenced_icons()

    mock_sweep.assert_called_once_with(mock_runtime.get_active_platform.return_value.storage)
