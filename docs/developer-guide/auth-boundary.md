# Auth Boundary Guide

This guide describes the supported identity and authentication boundary for the rest of the application.

## Public surfaces

Other modules use:

- `modules.auth.dependencies` for authenticated request dependencies, `Principal` resolution, scope checks, auth context, and shared auth stores.
- The owning auth child's `integration_service.py` for authentication operations. A caller chooses the child that owns the capability; auth CRUD and services remain private to their package.

Auth consumes users data through `modules.users.users.integration_service`. Users consumes credentials, MFA, identity links, account security, and sign-up email operations through their auth integration surfaces. Do not import another module's CRUD, service, models, or private helpers.

## Principal and credentials

`modules.auth.contracts.Principal` is the authenticated identity and authorization context. It carries the user id, username, email, active/superuser state, scopes, and a typed credential.

The credential is a discriminated union of `PasswordCred`, `AccessTokenCred`, `ApiKeyCred`, `SessionCookieCred`, and `OAuthCred`. Each variant contains only fields relevant to that method. Prefer `Principal` helpers such as `is_api_key()` and `credential_id()` over matching on credential internals.

`modules.auth.authentication.principal_service` resolves access tokens and API keys. Request dependencies call the published `authentication.integration_service` and cache the resolved principal for the request.

## Ownership map

| Package | Owns |
| --- | --- |
| `access_tokens` | JWT access-token validation and signing |
| `api_keys` | API-key persistence, scopes, hashing and serialization |
| `authentication` | Login, MFA login, refresh/logout, principal resolution and failed-login state |
| `account_security` | Password changes, session management, step-up, MFA workflows, API-key routes and IdP link management |
| `credentials` | Local password hashes and password policy |
| `identity_provider_link_tokens` | One-time browser IdP-link tokens |
| `identity_provider_links` | User-to-provider link persistence |
| `identity_providers` | Provider configuration, OIDC flows, callbacks and provider tokens |
| `lockout` | Shared lockout-state operations |
| `mfa` and `mfa_backup_codes` | MFA factors, setup state and recovery codes |
| `oauth_state` | OAuth state and nonce persistence |
| `password_reset_tokens` | Password-reset tokens and email workflow |
| `rotated_refresh_tokens` | Refresh-token reuse detection |
| `sessions` | Auth session lifecycle and refresh-cookie sessions |
| `sign_up_tokens` | Sign-up verification and approval email workflow |

User profile fields, profile routes, privacy settings, and non-auth account data belong to `modules.users`.

## Transaction ownership

CRUD functions stage database changes with `flush()` and raise domain errors from `core.exceptions`. A service owns the complete workflow and commits after all related writes are staged. An integration surface never ends a transaction: it stages through its package's service or crud and the caller, which holds the unit of work (the `users` services for the account-security actions, the `authentication` service for login, refresh, logout and the SSO exchange), commits. Where a write is advisory and must not sit on the request path, such as an API key's last-used time, the package publishes a best-effort event and a subscriber commits in its own session. Application migrations use each package's migration service and commit through application-level migration orchestration.

## Step-up for accounts without a local password

`modules.auth.account_security.step_up_service.verify_step_up_credentials` verifies a password for an account that has one. For an account without one it requires an `idp_reauth` proof, and MFA alone never passes. Without the proof it raises `IdpReauthRequiredError` (`401`, RFC 9470 challenge).

The flow lives in `identity_providers`: `account_security.identity_link_service.start_idp_step_up` stages the state through `authorization_service.stage_step_up`, and `callback_service.complete_step_up_callback` verifies the ID token and issues a single-use ticket in `step_up_ticket_store`. The ticket records the user, session, action and PKCE challenge; `account_security` reads and redeems it only through `identity_providers.integration_service`, after every other factor passed, so a wrong MFA code does not cost the ticket.

The provider's `auth_time` claim decides freshness, not the `prompt=login` the request sends, because providers differ in honouring `prompt` and `max_age`. A provider that cannot put a recent `auth_time` in the ID token cannot step up; an administrator then sets a local password for the user.
