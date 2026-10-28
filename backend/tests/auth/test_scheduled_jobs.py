"""Auth runtime contributions declare recurring and startup maintenance."""

import module_registry as runtime_module_registry


def test_auth_runtime_modules_are_registered():
    names = {module.name for module in runtime_module_registry.MODULES}
    assert {
        "oauth_state",
        "sessions",
        "rotated_refresh_tokens",
        "mfa",
        "identity_provider_link_tokens",
        "password_reset_tokens",
        "sign_up_tokens",
    } <= names


def test_token_purges_are_startup_tasks():
    modules = {module.name: module for module in runtime_module_registry.MODULES}
    for name in ("oauth_state", "identity_provider_link_tokens", "password_reset_tokens", "sign_up_tokens"):
        assert modules[name].startup_tasks
