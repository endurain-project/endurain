"""Aggregate SQLAlchemy model contributions owned by auth child modules."""

import modules.auth.api_keys.model_registry as api_keys_model_registry
import modules.auth.credentials.model_registry as credentials_model_registry
import modules.auth.identity_provider_link_tokens.model_registry as identity_provider_link_tokens_model_registry
import modules.auth.identity_provider_links.model_registry as identity_provider_links_model_registry
import modules.auth.identity_providers.model_registry as identity_providers_model_registry
import modules.auth.mfa.model_registry as mfa_model_registry
import modules.auth.mfa_backup_codes.model_registry as mfa_backup_codes_model_registry
import modules.auth.oauth_state.model_registry as oauth_state_model_registry
import modules.auth.password_reset_tokens.model_registry as password_reset_tokens_model_registry
import modules.auth.rotated_refresh_tokens.model_registry as rotated_refresh_tokens_model_registry
import modules.auth.sessions.model_registry as sessions_model_registry
import modules.auth.sign_up_tokens.model_registry as sign_up_tokens_model_registry

MODEL_MODULES = (
    *api_keys_model_registry.MODEL_MODULES,
    *credentials_model_registry.MODEL_MODULES,
    *identity_provider_link_tokens_model_registry.MODEL_MODULES,
    *identity_provider_links_model_registry.MODEL_MODULES,
    *identity_providers_model_registry.MODEL_MODULES,
    *mfa_model_registry.MODEL_MODULES,
    *mfa_backup_codes_model_registry.MODEL_MODULES,
    *oauth_state_model_registry.MODEL_MODULES,
    *password_reset_tokens_model_registry.MODEL_MODULES,
    *rotated_refresh_tokens_model_registry.MODEL_MODULES,
    *sessions_model_registry.MODEL_MODULES,
    *sign_up_tokens_model_registry.MODEL_MODULES,
)
