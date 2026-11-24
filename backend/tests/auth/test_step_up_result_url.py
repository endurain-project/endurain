"""The URL the browser returns to after an identity-provider step-up carries its outcome in the fragment."""

import modules.auth.identity_providers.utils as idp_utils


def test_the_outcome_travels_in_the_fragment():
    url = idp_utils.build_step_up_result_url(
        "https://app.example.com", "/settings/security?tab=1", {"step_up_ticket": "t-1"}
    )

    assert url == "https://app.example.com/settings/security?tab=1#step_up_ticket=t-1"


def test_without_a_return_path_it_goes_to_the_security_settings():
    url = idp_utils.build_step_up_result_url("https://app.example.com", None, {"step_up_error": "failed"})

    assert url == "https://app.example.com/settings/security#step_up_error=failed"
