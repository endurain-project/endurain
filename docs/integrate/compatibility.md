# Compatibility between releases

The rules a client can rely on when the server is upgraded. They hold for the Endurain web and mobile apps from v0.21.0 on, and for other clients that use [API keys](api-keys.md). A change that breaks one of them is announced as a breaking change in the release notes.

!!! warning "First-party sign-in"
    The `/auth` sign-in routes (login, MFA verification, password change, token exchange and refresh) and the SSO hand-off through `ALLOWED_REDIRECT_URIS` are first-party protocols for Endurain's own web and mobile apps. Other applications use API keys today and the OAuth endpoints, reserved under `/oauth/*`, when they exist, and may be refused on the first-party routes then.

## Responses gain members

- A response object may gain new members in any release. Ignore a member you do not know; do not refuse the response because of it.
- A member keeps its name, type and meaning. A new meaning arrives as a new member.
- Send only the request fields the documentation describes. A new optional request field can appear in any release, and an older server may refuse a field it does not know.

## Open sets

These values are open: a release can add one. Handle a value you do not know as described, never as one of the known values.

| Value | Known today | When a value is unknown |
| ----- | ----------- | ----------------------- |
| `next_step` in a sign-in or token answer (`/auth/login`, `/auth/mfa/verify`, `/auth/password-change`, `/auth/refresh`, `/auth/sessions/{session_id}/tokens`) | `mfa`, `password_change`, `exchange`, `tokens` | The client is not signed in. Tell the user that this client cannot finish the sign-in and should be updated. See [Sign-in steps](authentication.md#sign-in-steps). |
| A problem document's `type` | The [error types](errors-and-limits.md#error-types) | Act on the `status`. |
| The `error` query parameter of a failed SSO sign-in (`/login?error=<code>`) | The codes in [SSO failures](oauth-sso-pkce.md#sso-failures) | Show a general sign-in failure. |
| The `type` of a step-up challenge (a `401` with `WWW-Authenticate: Bearer error="insufficient_user_authentication"`) | `urn:endurain:error:idp-reauth-required`. See [Step-up Refusal](account-security.md#step-up-refusal) | The client does not support that method. Stop, keep no partial state and tell the user to make the change in a client that does. |
| `provider_type` of an identity provider | `oidc`, `oauth2` | Show the provider as it is named and do not assume the protocol it speaks. |
| `require_mfa` of the server settings | `off`, `administrators`, `everyone` | Treat the account as one that may be required to have MFA, and send the user to the web app to set it up. |
| `access_type` of a user | `regular`, `admin` | Treat the user as a regular user and rely on the scopes of the token for what it may do. |
| `security` of the mail settings | `starttls`, `ssl`, `none` | Show the value as it is and do not assume how the connection is secured. |
| The `X-Client-Type` header | `web`, `mobile` | Send one of the documented values. A value the server does not know is refused with `422`. |

The `action` a step-up request body names is a request value, and a release can add an operation to it.

## Refusals

The status code is the stable part of a refusal. A case answered today with a general problem `type` may get a more specific `type` of its own in a later release, with the same status. Branch on the specific types you handle and fall back on the status for everything else. A `type` that exists keeps its URN and its meaning.

## New ways to sign in

A new way to authenticate, such as passkeys, arrives as new optional request fields or new routes. An existing field never changes meaning to carry it. It can make a sign-in answer a `next_step` your client does not know yet, which is why `next_step` is an open set.

## Tokens

Access tokens, refresh tokens, `session_id`, MFA and password-change challenges, tickets and API keys are opaque strings. Do not parse them, read their claims or assume a length or format: they can change in any release. Read lifetimes from the response fields (`expires_in`, `refresh_token_expires_in`), not from the token.

Every response that carries a token or another secret is sent with `Cache-Control: no-store` and `Pragma: no-cache`, so no browser or proxy cache keeps it. The list is in [Responses that carry a secret](account-security.md#responses-that-carry-a-secret).

The scopes `profile`, `profile:export` and `profile:security` were renamed `account`, `account:export` and `account:security` in v0.21.0, so they no longer clash with the OpenID Connect `profile` scope. The old names are refused like any unknown scope, and an access token issued before the upgrade lacks the new names until its next refresh, so those routes answer `403` for at most one access-token lifetime.

The scopes with an underscore were renamed to kebab-case in v0.21.0, so every scope name follows one rule: `health_targets:read` and `health_targets:write` are `health-targets:read` and `health-targets:write`, `identity_providers:read` and `identity_providers:write` are `identity-providers:read` and `identity-providers:write`, `server_settings:read`, `server_settings:write`, `server_settings:logs` and `server_settings:logs_clear` are `server-settings:read`, `server-settings:write`, `server-settings:logs` and `server-settings:logs-clear`, and `users:read_all` is `users:read-all`. As with the `account` rename, the old names are refused and an access token issued before the upgrade answers `403` on those routes until its next refresh.

Linking and unlinking Garmin Connect and Strava moved from `account` to the new `account:integrations` scope in v0.21.0, so a token can hold the account's data without being able to hand a provider's credentials to the server. Every user holds it. An access token issued before the upgrade lacks it until its next refresh, so those routes, and reading a `garmin_link`, `strava_link` or `strava_unlink` job, answer `403` for at most one access-token lifetime.

The identity-provider API changed in v0.21.0. `jwks_uri` is gone from its requests and responses: the signing keys come from the provider's discovery document. A `client_id` or `client_secret` sent as `null` on `PATCH /identity-providers/{idp_id}` is refused with `422` instead of clearing the stored credential, and an `oidc` provider needs an `issuer_url` and the `openid` scope. The slugs `login`, `callback`, `icon` and `backchannel-logout` are reserved and refused with `422`; the upgrade stops when an existing provider uses one. Disabling a provider ends every session it signed in.

`PATCH /users/{user_id}` is a partial edit and answers `409` when it would activate a user who awaits approval; use `POST /users/{user_id}/approve`. A username changes through `POST /profile/username/change`, which needs step-up, and `PATCH /profile` refuses a `username` field. A replay of the SSO token exchange (`POST /auth/sessions/{session_id}/tokens`) answers `404` like any session that is not eligible, and never `409`.

The web client's device cookie and the identity-provider binding cookie are renamed with the `__Host-` prefix and set with `Path=/` in `production` and `demo`, so each browser gets one new-device notice after the upgrade. A request to a route under `/auth/` or `/public/` with a body over 64 KiB is refused with `413`. `SECRET_KEY` needs at least 10 distinct characters, and `ENDURAIN_HOST` is read in its canonical form (lower-case scheme and host, the default port dropped), which changes the token `iss` and `aud` of a deployment that wrote it differently.

Several requests changed in v0.21.0. `GET /users` with only `users:read` answers `422` unless it sends `username` or `username_contains` of at least 3 characters. `POST /profile/api-keys` answers `409` with `urn:endurain:error:api-key-limit` once the account holds 25 active keys. `PUT /server-settings` needs step-up when it changes a geocoding or tile field. A password shorter than the minimum is still `422`, but with `urn:endurain:error:password-too-short` instead of `urn:endurain:error:validation-failed`, because the password policy now checks the length. `POST /users` no longer requires a `password`. A PKCE `code_verifier` may now contain `.` and `~`.

## Reserved paths

These paths are reserved for planned features, such as third-party OAuth clients and passkeys. Endurain will not use them for anything else, and a client must not expect them to exist yet:

- Under the API root `/api/v1`: `/oauth/`, `/auth/webauthn/`, `/profile/passkeys`, `/profile/grants` and `/oauth-clients`.
- At the server root: `/.well-known/`, as [RFC 8615](https://www.rfc-editor.org/rfc/rfc8615) defines.
