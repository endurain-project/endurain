# Changes from v0.20 to v0.21

What changed between v0.20 and v0.21 for the people who run Endurain and for the clients that call its API: third-party apps, mobile apps and scripts that use [API keys](api-keys.md). If you only use the Endurain web app, you need only the first section. For the rules that hold from now on, see [Compatibility between releases](compatibility.md).

## Before you upgrade

Back up the database and the `data` folder first. The upgrade converts every integer id to a UUID and cannot be undone: restoring the backup is the only way back to v0.20.

- **Upgrade from v0.20.x only, with every data migration finished.** The first revision refuses to run on a database that has users and a pending v0.20 data migration, and says which ones. Start the latest v0.20.x release, let the data migrations finish, then upgrade.
- **Stop every Endurain process** (web and worker containers) before the upgrade, so no job is left in the queue.
- **A provider slug can be a reserved word.** The upgrade refuses to run while an identity provider uses the slug `login`, `callback`, `icon` or `backchannel-logout`. Change the slug and register the new callback URL (`<ENDURAIN_HOST>/api/v1/public/idp/callback/<slug>`) at the provider, then upgrade again. A new or renamed provider cannot use `link` either.
- **Two providers cannot share an issuer.** The upgrade refuses to run while two identity providers have the same issuer URL (trailing slashes ignored). Change the issuer URL of, or delete, all but one.
- **Everyone signs in again once.** Every web and mobile session ends. API keys keep working, and keys that never expired now expire 365 days after the upgrade (see [API keys](api-keys.md)).
- **Stored files and folders are renamed** to the new UUIDs at the first start: activity files, thumbnails, photos, identity-provider icons, profile photos, and the per-user bulk import and Strava import folders. Account lockouts are lifted. See [Storage and backups](../getting-started/storage-and-backups.md).
- **The schema upgrade runs in one transaction** and takes longer on a large database. Run `VACUUM (ANALYZE)` afterwards.

### Environment variables

See [Supported environment variables](../getting-started/advanced-setup.md#supported-environment-variables) for the full list.

| Variable | What happens |
| -------- | ------------ |
| `ALLOWED_REDIRECT_SCHEMES` | Removed. Endurain refuses to start while it is set. List the exact addresses in `ALLOWED_REDIRECT_URIS` instead. A scheme `endurain` becomes `endurain://auth/sso/callback`. |
| `UID`, `GID`, `FRONTEND_PROTOCOL`, `RATE_LIMIT_STORAGE_URI`, `AUTH_SECURITY_STORAGE_URI` | Retired in earlier releases. Endurain refuses to start while any of them is set, and the log says what replaces it. |
| `ALGORITHM` | Removed. Tokens are always signed with HS256. A leftover value (or `ALGORITHM_FILE`) is ignored with a warning. |
| `SESSION_IDLE_TIMEOUT_ENABLED`, `SESSION_IDLE_TIMEOUT_HOURS`, `SESSION_ABSOLUTE_TIMEOUT_HOURS`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Deprecated. Now *Settings > Server settings > Access & security*. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURE`, `SMTP_SECURE_TYPE` | Deprecated. Now *Settings > Server settings > Email*. |
| `REVERSE_GEO_PROVIDER`, `PHOTON_API_HOST`, `PHOTON_API_USE_HTTPS`, `NOMINATIM_API_HOST`, `NOMINATIM_API_USE_HTTPS`, `GEOCODES_MAPS_API`, `REVERSE_GEO_RATE_LIMIT` | Deprecated. Now *Settings > Server settings > Maps & location*. |
| `READ_NOTIFICATION_RETENTION_DAYS` | Deprecated. Now *Settings > Server settings > General*. |
| `BEHIND_PROXY` | `true` now requires `TRUSTED_PROXIES`. The container refuses to start without a usable entry. |
| `ENDURAIN_HOST` | Must be only `scheme://host[:port]`, with no path, query, fragment or user info, or Endurain refuses to start. It is read in canonical form (lower-case scheme and host, default port dropped). If yours was written differently, the token `iss` and `aud` change, so everyone signs in again. |
| `SECRET_KEY` | At least 32 characters with at least 10 distinct ones. List several keys separated by commas to rotate it: the first signs, all of them verify. |
| `FERNET_KEY` | List several keys separated by commas to rotate it. |
| `SECRET_KEY`, `FERNET_KEY`, `DB_PASSWORD` | The example values published in `.env.example` and in the docs are refused at startup, including through the `*_FILE` variants. |

The deprecated variables that moved to the admin settings are still read. At every start, Endurain saves each one that is set into the database when it differs from the stored value, logs one warning naming them, and shows the setting as read-only while the variable is set. Remove them after the first start. From v0.22.0 Endurain refuses to start while any of them is set.

### Mobile app redirect

The default `ALLOWED_REDIRECT_URIS` is `com.endurain.endurain:/auth/sso/callback`. Older mobile app builds send `endurain://auth/sso/callback`, which is not in the default. If you still serve such builds, add that address to the list, and keep the default in it, because setting the variable replaces the default:

```text
ALLOWED_REDIRECT_URIS=com.endurain.endurain:/auth/sso/callback,endurain://auth/sso/callback
```

An app listed there receives tokens with every scope the signing-in user holds, so list only apps you trust. See [Redirect schemes](oauth-sso-pkce.md#redirect-schemes).

## Authentication and sessions

- **Tokens issued before the upgrade are refused.** The `sub` claim is the user's UUID, and tokens carry `typ` and `kid` headers. Refresh tokens are separate tokens. Treat tokens as opaque, as [Compatibility](compatibility.md#tokens) says.
- **`client_id` is now `client_type`.** The claim that said `web` or `mobile` is `client_type`, and tokens carry no `client_id`. Clients that read a token instead of treating it as opaque must read `client_type`.
- **Cookies.** In `production` and `demo`, the refresh, device and identity-provider binding cookies carry the `__Host-` prefix. A web browser signs in again and counts as a new device once. A mobile client sends its refresh token in the request body.
- **Sign-in errors.** Every refusal of `POST /auth/refresh`, and a dead pending sign-in at `POST /auth/mfa/verify` and `POST /auth/password-change`, is `401` with `urn:endurain:error:session-ended` and `WWW-Authenticate: Session`: sign in again, do not retry. A failed password sign-in challenges with `Session`, not `Bearer`. `invalid-token` now means "refresh once and replay the request" on resource routes only. See [Authentication errors](errors-and-limits.md#authentication-errors).
- **No CSRF token.** The web token responses no longer carry `csrf_token`, and `X-CSRF-Token` is neither read nor allowed. `POST /auth/refresh` and `POST /auth/logout` from a web client must carry an `Origin` header the server allows (browsers add it) and are refused with `403` when `Sec-Fetch-Site` is `cross-site`. See [Authentication](authentication.md).
- **SSO sign-in with MFA** follows the steps of a password sign-in: `POST /auth/sessions/{session_id}/tokens` answers `200` with `next_step: "mfa"`, and the client finishes at `POST /auth/mfa/verify`. The exchange no longer accepts `mfa_code`, and the `mfa-required` problem is gone. See [Sign-in steps](authentication.md#sign-in-steps).
- **MFA reads.** `GET /profile/mfa/status` gains `factors`, and the MFA-required sign-in answer gains `methods`. Both are open sets.
- **Step-up.** Sensitive requests carry one `step_up` object (`current_password` and/or an MFA code), and every refusal is `403` with `urn:endurain:error:step-up-failed`. The destructive actions below became `POST` routes with a `step_up` body. See [Operations that require step-up](account-security.md#operations-that-require-step-up).
- **One `429` type.** Every `429` is `too-many-requests`, with a `scope` member (`requests`, `sign-in`, `mfa`, `step-up`, `provider`, `follow-request`). `rate-limited` is gone.
- **Sessions and devices.** Session and device reads carry `is_current`, and `last_login` of an identity-provider link is `last_login_at`.
- **API keys** always expire (365 days by default, set by an administrator), and an account holds at most 25 active keys (`409` with `urn:endurain:error:api-key-limit`).

## Scopes

A scope name is lower-case kebab-case. The old names are refused like any unknown scope. See [Available scopes](auth-reference.md#available-scopes).

| Old scope | New scope |
| --------- | --------- |
| `profile` | `account` |
| `profile:export` | `account:export` |
| `profile:security` | `account:security` |
| `health_targets:read`, `health_targets:write` | `health-targets:read`, `health-targets:write` |
| `identity_providers:read`, `identity_providers:write` | `identity-providers:read`, `identity-providers:write` |
| `server_settings:read`, `server_settings:write` | `server-settings:read`, `server-settings:write` |
| `server_settings:logs`, `server_settings:logs_clear` | `server-settings:logs`, `server-settings:logs-clear` |
| `users:read_all` | `users:read-all` |

Linking and unlinking Garmin Connect and Strava moved from `account` to the new `account:integrations` scope. Every user holds it, and a session started after the upgrade carries it.

The token's scope is enforced: an endpoint checks the scopes in the token, limited to the scopes the user's role holds when the request arrives. An API key gets only the scopes its owner's role grants.

## Identifiers

Every resource id is a UUID string: users, activities and their laps, sets, steps, streams and photos, gear and components, health records, goals, notifications, known devices, identity providers and their links, sessions, API keys and jobs.

- A malformed id in a path, query or body answers `422`, and an unknown one `404`.
- Do not assume a format or an order. Treat `id` as a string, also in the public provider list (`GET /public/idp`).
- An activity feed cursor issued before the upgrade answers `400`. Restart the feed without a cursor.
- Public share links and saved activity links from before the upgrade stop working, because the link carries the activity id. Share the activity again.

## Routes and requests

| Old route | New route |
| --------- | --------- |
| `POST /profile/devices/revoke` | `POST /profile/devices/delete-others` |
| `POST /profile/devices/delete` | `POST /profile/devices/delete-all` |
| `DELETE /server-settings/logs` | `POST /server-settings/logs/clear` (`step_up` body) |
| `DELETE /strava/link` | `POST /strava/unlink` (`step_up` body) |
| `DELETE /garmin/link` | `POST /garmin/unlink` (`step_up` body) |
| `/notifications/number` | `/notifications/unread-count` |

`PUT /strava/client` takes a `step_up` object next to the client id and secret. `PUT /server-settings` needs step-up when it changes a security, geocoding or tile field. `POST /profile/mfa/verify` and the user email lookup route are removed.

**Requests**

- **`PATCH /profile`** no longer accepts `username`, `photo_path` or `mfa_enabled`. Change the username at `POST /profile/username/change`, which needs step-up.
- **`PATCH /users/{user_id}`** is a partial edit. It needs the administrator's `step_up` to change the email, access type, active flag, username or email-verified flag, and it answers `409` instead of activating a user who awaits approval: use `POST /users/{user_id}/approve`. `POST /users` no longer requires a `password`.
- **`GET /users`** with only `users:read` answers `422` unless it sends `username` (exact) or `username_contains` (3 or more characters). The user directory shows less about other users.
- **Gear.** The acquisition date is `acquired_on`, and the component field `expected_kms` is `expected_usage`. Gear distance is in meters and prices are decimal strings.
- **Follow requests** live under `/profile/follow-requests` and are accepted with `POST`. Notifications are paged by cursor, with routes to delete one and to mark many as read. The server log is paged by cursor.

**Conventions.** The full rules are in [HTTP API conventions](../developer-guide/http-api.md), [Data conventions](data-conventions.md) and [Errors, concurrency and rate limits](errors-and-limits.md).

- Creates return `201` with `Location` and `ETag`, and writes that only carry a message return `204`. Edits use `PATCH` (identity providers, users), and singleton uploads use `PUT`.
- `PUT` and `PATCH` on a versioned resource require `If-Match`, and a stale write is `412`.
- A request that does not fit the account's state is `409`, an unsupported file type is `415`, and a NUL character or out-of-range value is `422`. New typed problems include `password-too-short`, `password-breached`, `api-key-limit`, `mfa-enrolment-required` and `components-outside-gear-type`.
- Lists share one filter, page and date-window vocabulary. Enums are strings on the wire, units are stated in field descriptions, and health requests need a UTC offset on every instant. The identity-provider and identity-link lists are paged.
- The sleep and activity lists leave heavy fields out. Read the full record by id. Activity lists embed each activity's media.
- Every `202` returns a job with an id and `Content-Location: /jobs/{id}`. Read it at `GET /jobs/{job_id}` and list your jobs at `GET /jobs`. See [Background operations](background-operations.md#reading-a-job).
- A request under `/auth/` or `/public/` with a body over 64 KiB is `413`.
- `/openapi.json` is served only in development and demo installs. Use the published API reference otherwise.

## Single sign-on and identity providers

- **Mobile SSO requires PKCE and an exact redirect address** listed in `ALLOWED_REDIRECT_URIS`. An SSO sign-in is bound to the browser that started it. For a custom-scheme address, the browser passes the `session_id` to the app only after the user confirms it; a claimed `https` address is forwarded at once. See [OAuth/SSO and PKCE](oauth-sso-pkce.md).
- **Provider API.** `jwks_uri` is gone, because the signing keys come from the discovery document. `client_id` is required when creating a provider. Providers are typed (`oidc` needs an `issuer_url` and the `openid` scope), and there is one provider per issuer. A `client_id` or `client_secret` sent as `null` is refused with `422` instead of clearing the credential.
- **Locked fields.** The slug, `client_id`, provider type, issuer and endpoints cannot change while users are linked: `409` with `urn:endurain:error:identity-provider-locked`.
- **Reserved slugs:** `login`, `link`, `callback`, `icon` and `backchannel-logout`.
- **Opt-in linking.** Linking by email and profile sync are off until an administrator enables them. An existing account is not changed before its second factor passes.
- **Unverified emails.** A provider email that is not verified never matches or creates an account. It is refused with `sso_email_unverified`, before any account is looked up.
- **Last sign-in method.** Unlinking a provider answers `409` with `urn:endurain:error:last-sign-in-method` when the account would have no other way to sign in. A disabled provider does not count.
- **Native apps can link a provider.** `POST /profile/identity-providers/{idp_id}/link` with a native `redirect` returns an Endurain address, `GET /public/idp/link?ticket=...`, for the system browser. The one-time link-token route is removed. See [Linking accounts](oauth-sso-pkce.md#linking-accounts).
- **Sessions.** A session started by a native app records the address as `app_redirect_uri` (read-only). Disabling a provider ends the sessions it signed in.

## Emails and links

- Links in emails (password reset, sign-up confirmation and invitation, email change and its cancellation) carry the token in the URL fragment (`#token=`), so it stays out of logs and `Referer` headers. The web app still reads `?token=` for one release, so links sent before the upgrade work.
- Changing an email address is confirmed by pressing a button on the page, and `POST /public/email-change/confirm` answers `204`. The address switches only after the new one is confirmed. See [Confirming a link](public-endpoints.md#confirming-a-link).

## Profile export and import

- A profile archive exported by an Endurain version before v0.21.0 cannot be imported. The job fails with `error_code: older_version` and nothing is imported. Export again after the upgrade.
- Health records are part of the export and import. An import from a different account is refused (`wrong_account`).
- Profile export needs step-up. See [Profile export](account-security.md#profile-export) and [Background operations](background-operations.md#profile-export-and-import).

## Sync

`GET /sync` is new. It reports what changed in a user's records since a cursor, for clients that keep a local copy. See [Keeping a local copy in sync](sync.md).

## Checklist for client developers

1. Sign in again, and request the new scope names. Replace `profile*`, underscore scopes and `users:read_all`.
2. Treat every id as a UUID string, and drop any code that parses, sorts or compares ids as numbers.
3. Read `client_type` instead of `client_id` if you inspect a token, or stop inspecting it.
4. On a `401` with `session-ended`, sign in again without retrying. Refresh once and replay only on `invalid-token`.
5. Stop sending and reading CSRF tokens. A web client sends `Origin` on `POST /auth/refresh` and `POST /auth/logout`.
6. Send a `step_up` object on sensitive requests, and move to the renamed `POST` routes for unlink, log clearing and device sign-out.
7. Send `If-Match` with the `ETag` you read on `PUT` and `PATCH`, and refetch on `412`.
8. Follow `Content-Location` on every `202` and poll `GET /jobs/{job_id}`.
9. Read email-link tokens from the URL fragment, and register `com.endurain.endurain:/auth/sso/callback` for mobile SSO (or ask the operator to allow your address).
10. Export profile archives again, because archives from v0.20 cannot be imported.
