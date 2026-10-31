"""FastAPI providers for MFA state stores."""

import core.dependencies as core_dependencies
import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa.setup_store as setup_store

PendingMFAStore = pending_login_store.PendingMFAStore
get_pending_mfa_store = pending_login_store.get_pending_mfa_store


def get_mfa_secret_store(
    state: core_dependencies.PlatformState,
) -> setup_store.MFASecretStore:
    """Build the temporary MFA-secret store from the active platform state provider."""
    return setup_store.MFASecretStore(state)


MFASecretStoreBackend = mfa_contracts.MFASecretStoreBackend
