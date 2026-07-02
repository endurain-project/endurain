# Auth Boundary Guide

This guide defines the supported authentication boundary for non-auth modules.

## Public Boundary

Non-auth modules must consume auth **only** through these public entry points:

- `auth.dependencies`
- `auth.identity_service.IdentityService`

`IdentityService` exposes both credential resolution (e.g. `resolve_from_access_token`,
`resolve_from_api_key`) and the higher-level account-security workflows (sessions,
password change, MFA lifecycle, IdP linking). Non-auth modules call these methods on
the injected `IdentityService`; they do **not** import the implementations.

The workflow implementations live in `auth.services.*` (see *Auth Service Modules*
below), but those modules are **auth-internal**: `IdentityService` delegates to them,
and import-linter forbids non-auth modules from importing them directly. Do not import
low-level auth internals or `auth.services.*` from non-auth modules.

## Principal Model

`IdentityService` resolves identity into a `Principal` object that carries auth-relevant identity and authorization data for the current request.

Core fields include:

- `user_id`
- `username`
- `email`
- `is_active`
- `is_superuser`
- `scopes`
- `credential`

Callers should prefer helper methods on `Principal` (for example `is_api_key()` and credential ID helpers) instead of matching against internal credential-shape details in non-auth modules.

## Credential Discriminated Union

`Principal.credential` is a discriminated union, not a set of parallel optionals. Variants include:

- `PasswordCred`
- `AccessTokenCred`
- `ApiKeyCred`
- `SessionCookieCred`
- `OAuthCred`

Each variant contains only the fields meaningful for that authentication method (for example, access-token metadata for `AccessTokenCred`, API-key identifiers for `ApiKeyCred`, and session IDs for `SessionCookieCred`).

## Ownership Map

Auth-owned modules include:

- Credentials and token lifecycle (`auth.token_manager`, `auth.password_hasher`)
- Sessions and rotated refresh tokens (`auth.sessions`)
- API keys (`auth.api_keys`)
- MFA setup state, TOTP logic, and backup-code lifecycle (`auth.mfa`, `auth.mfa.backup_codes`)
- OAuth state and IdP link tokens (`auth.oauth_state`, `auth.identity_providers.link_tokens`)
- Identity-provider config, links, and link tokens (`auth.identity_providers`, `auth.identity_providers.links`, `auth.identity_providers.link_tokens`)
- Password reset tokens (`auth.password_reset_tokens`)
- Sign-up verification tokens (`auth.sign_up_tokens`)
- Step-up credential verification with lockout (`auth.services.step_up_service`)
- Password change workflows (`auth.services.account_security_service`)
- MFA management workflows (`auth.services.mfa_workflow`)
- Identity-link management workflows (`auth.services.identity_link_service`)

Users/profile-owned modules include:

- Profile fields
- Privacy settings
- User-facing profile routes and orchestration
- Business-level user data unrelated to auth credential/state ownership

## Auth Service Modules

The following facade modules implement the account-security workflows that
`IdentityService` delegates to. They are **auth-internal**: non-auth modules reach
this behaviour through the matching `IdentityService` methods, never by importing
these modules directly. Each encapsulates a cluster of related auth workflows so the
delegators stay thin and low-level auth persistence modules are not imported across
the boundary.

| Module (internal) | Responsibility | Reached via `IdentityService` |
| ----------------- | -------------- | ----------------------------- |
| `auth.services.account_security_service` | `change_own_password`, `change_managed_user_password`, session listing/revocation | `get_user_sessions`, `delete_user_session`, `change_own_password`, `change_managed_user_password` |
| `auth.services.mfa_workflow` | MFA status, setup, enable, disable, backup-code status and regeneration | `get_mfa_status`, `setup_mfa`, `enable_mfa`, `disable_mfa`, `verify_mfa`, `get_backup_code_status`, `generate_backup_codes` |
| `auth.services.identity_link_service` | IdP link listing, token generation, link removal, browser-redirect claiming, link counts and membership | `get_user_identity_provider_links`, `generate_link_token`, `delete_identity_provider_link`, `validate_and_claim_browser_link_token`, `get_identity_link_counts_for_users`, `get_user_ids_with_identity_links` |
| `auth.services.step_up_service` | `verify_step_up_credentials` with progressive lockout (5/5 min, 10/30 min, 15/2 hr) | used internally by the workflow modules above |

## Service Placement Rule

- `auth.services.*` owns high-level workflows, reached by non-auth callers through
  `IdentityService` (not imported directly).
- `auth.<domain>.crud` owns persistence for one auth domain.
- `auth.<domain>.schema` owns request/response models for that domain.
- Pure helpers may live in `auth.<domain>.*` when they do not orchestrate step-up,
  route behavior, or multi-module workflows.
- New non-auth callers must use `auth.dependencies` or `IdentityService`, not
  `auth.services.*` or low-level CRUD modules.

## Import-Linter Contracts

The backend import-linter enforces two key constraints:

1. Non-auth modules cannot import:
   - `auth.internal_dependencies`
   - `auth.password_hasher`
   - `auth.token_manager`
2. Non-auth modules cannot import low-level ownership modules or the internal
   workflow layer directly:
   - `auth.password_reset_tokens.crud`
   - `auth.sign_up_tokens.crud`
   - `auth.sessions.crud`
   - `auth.mfa.crud`
   - `auth.mfa.backup_codes.crud`
   - `auth.identity_providers.links.crud`
   - `auth.identity_providers.link_tokens.crud`
   - `auth.credentials.crud`
   - `auth.security_stores`
   - `auth.services`

These workflows and persistence helpers are reached through `IdentityService`
instead. A small set of route/service facade exceptions is explicitly
allow-listed in `backend/.importlinter`.

## Transaction Contract

`IdentityService` does not own transaction policy. It delegates DB operations to auth CRUD helpers, and those helpers own commit/refresh behavior. When callers need multi-step atomic workflows, use dedicated CRUD/service helpers designed for that workflow.

## Identity-Link Database Constraints

The `auth.identity_providers.links` table enforces uniqueness at the database level via two named constraints:

| Constraint | Columns | Purpose |
| ---------- | ------- | ------- |
| `uq_identity_links_user_idp` | `(user_id, idp_id)` | Prevents a user from linking the same provider more than once |
| `uq_identity_links_idp_subject` | `(idp_id, idp_subject)` | Prevents the same external identity from being linked to more than one Endurain account |

Duplicate link attempts return HTTP 409. These constraints were added in migration `v0_18_1` (revision `a1b2c3d4e5f6`).

## Known Structural Debt

These items are intentionally deferred and tracked here for contributor awareness.

### Credential-table split (deferred — original-plan Phase 19)

`users/users/models.py` still declares ORM relationships to every auth table
(`users_sessions`, `password_reset_tokens`, `sign_up_tokens`, `oauth_states`,
`mfa_backup_codes`, `auth_mfa`, `users_api_keys`, `user_identity_providers`) and
the `password` column is still a `nullable=False` column on the `Users` model.
The import boundary is enforced by import-linter, but the data model has not been
split. Moving credential columns and their relationships to an auth-owned model is
a separate, higher-risk schema project and is explicitly out of scope for the
import-boundary refactor.

Until the split lands, keep auth-table relationships read-only from within `users`
code and do not add new credential columns to `users/users/models.py`.

### Step-up verification gap for SSO-only accounts

SSO-only accounts (no local password) skip the password factor in
`auth.services.step_up_service.verify_step_up_credentials`. MFA still gates if
enabled, but an SSO-only user with no MFA configured receives no step-up challenge.

The correct fix is to require a fresh IdP re-authentication for SSO-only accounts
on the same sensitive-endpoint set. This is not yet implemented.
TODO(issue): create and link a tracker issue for fresh IdP re-auth on SSO-only step-up.
