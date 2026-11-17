# Changes from v0.20 to v0.21

What changed between v0.20 and v0.21 for the people who run Endurain and for the clients that call its API: third-party apps, mobile apps and scripts that use [API keys](api-keys.md). If you only use the Endurain web app, you need only the first section. For the rules that hold from now on, see [Compatibility between releases](compatibility.md).

## Before you upgrade

Back up the database and the `data` folder first. The upgrade converts every integer id to a UUID and cannot be undone: restoring the backup is the only way back to v0.20.

- **Upgrade from v0.20.x only, with every data migration finished.** The first revision refuses to run on a database that has users and a pending v0.20 data migration, and says which ones. Start the latest v0.20.x release, let the data migrations finish, then upgrade.
- **Stop every Endurain process** (web and worker containers) before the upgrade, so nothing runs against the old schema while it converts.
- **A provider slug can be a reserved word.** The upgrade refuses to run while an identity provider uses the slug `login`, `callback`, `icon` or `backchannel-logout`. Change the slug and register the new callback URL (`<ENDURAIN_HOST>/api/v1/public/idp/callback/<slug>`) at the provider, then upgrade again. A new or renamed provider cannot use `link` either.
- **Two providers cannot share an issuer.** The upgrade refuses to run while two identity providers have the same issuer URL (trailing slashes ignored). Change the issuer URL of, or delete, all but one.
- **Everyone signs in again once.** Every web and mobile session ends. API keys keep working, and keys that never expired now expire 365 days after the upgrade (see [API keys](api-keys.md)).
- **Single sign-on stops creating accounts.** The new setting **Allow new user sign-ups through single sign-on** is off after the upgrade, so a first sign-in that matches no account is refused with `sso_auto_create_disabled`. Existing accounts sign in and link as before. Turn it on in *Settings > Server settings* if providers should keep creating accounts. Existing providers keep linking by email and syncing the email as they did (`link_by_email` on, `sync_email` set from `sync_user_info`); a new provider starts with both off.
- **Stored files and folders are renamed** to the new UUIDs at the first start: activity files, thumbnails and media, identity-provider icons, profile photos, failed bulk-import files, staged profile exports and imports, and the per-user bulk import and Strava import folders. Account lockouts are lifted. See [Storage and backups](../getting-started/storage-and-backups.md).
- **The schema upgrade runs in one transaction** and takes longer on a large database. Run `VACUUM (ANALYZE)` on the database afterwards, for example `docker exec -it <postgres container> psql -U endurain -d endurain -c 'VACUUM (ANALYZE);'`.

### Environment variables

See [Supported environment variables](../getting-started/advanced-setup.md#supported-environment-variables) for the full list.

| Variable | What happens |
| -------- | ------------ |
| `ALLOWED_REDIRECT_SCHEMES` | Removed. Endurain refuses to start while it is set. List the exact redirect addresses in `ALLOWED_REDIRECT_URIS` instead: a scheme allowed every address under it, an entry allows only itself (see [Mobile app redirect](#mobile-app-redirect)). |
| `ALGORITHM` | No longer read. Tokens are always signed with HS256. A leftover value (or `ALGORITHM_FILE`) is ignored with a warning. |
| `SESSION_IDLE_TIMEOUT_ENABLED`, `SESSION_IDLE_TIMEOUT_HOURS`, `SESSION_ABSOLUTE_TIMEOUT_HOURS`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Deprecated. Now *Settings > Server settings > Access & security*. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURE`, `SMTP_SECURE_TYPE` | Deprecated. Now *Settings > Server settings > Email*. |
| `REVERSE_GEO_PROVIDER`, `PHOTON_API_HOST`, `PHOTON_API_USE_HTTPS`, `NOMINATIM_API_HOST`, `NOMINATIM_API_USE_HTTPS`, `GEOCODES_MAPS_API`, `REVERSE_GEO_RATE_LIMIT` | Deprecated. Now *Settings > Server settings > Maps & location*. |
| `READ_NOTIFICATION_RETENTION_DAYS` | Deprecated. Now *Settings > Server settings > General*. |
| `ENVIRONMENT` | Must be `production`, `demo` or `development`. Any other value stops Endurain at startup. |
| `BEHIND_PROXY` | `true` now requires a usable `TRUSTED_PROXIES` entry: the container refuses to start without one (it used to log an error and start). |
| `TRUSTED_PROXIES` | No longer defaults to `*` in `development`. |
| `LOG_ACCESS` | New. The per-request access log is off unless it is `true`. |
| `ENDURAIN_HOST` | Must be only `scheme://host[:port]`, with no path, query, fragment or user info, or Endurain refuses to start. It is read in canonical form (lower-case scheme and host, default port dropped), and the token `iss` and `aud` use that form. |
| `SECRET_KEY` | At least 32 characters with at least 10 distinct ones. List several keys separated by commas to rotate it: the first signs, all of them verify. |
| `FERNET_KEY` | List several keys separated by commas to rotate it: the first encrypts, all of them decrypt. |
| `SECRET_KEY`, `FERNET_KEY`, `DB_PASSWORD` | The example values published in `.env.example` and in the docs are refused at startup, including through the `*_FILE` variants. |

The deprecated variables that moved to the admin settings are still read. At every start, Endurain saves the ones that are set into the database, logs one warning naming them, and shows those settings as read-only while the variables are set. The email variables are read only when `SMTP_HOST` is set, an invalid email or geocoding value is skipped with a warning and the stored setting kept, and session values that contradict each other (an absolute timeout below the idle timeout, an access token lifetime not below the idle timeout) stop Endurain at startup. Remove the variables after the first start. From v0.22.0 Endurain refuses to start while any of them is set.

### Mobile app redirect

The default `ALLOWED_REDIRECT_URIS` is `com.endurain.endurain:/auth/sso/callback`. If you serve app builds that send `endurain://auth/sso/callback`, add that address to the list, and keep the default in it, because setting the variable replaces the default:

```text
ALLOWED_REDIRECT_URIS=com.endurain.endurain:/auth/sso/callback,endurain://auth/sso/callback
```

An app listed there receives tokens with every scope the signing-in user holds, so list only apps you trust. See [Redirect schemes](oauth-sso-pkce.md#redirect-schemes).

## Authentication and sessions

**Tokens**

- **Tokens issued before the upgrade are refused.** The `sub` claim is the user's UUID. Tokens carry `typ` and `kid` headers (the `typ` claim is gone), and a new `client_type` claim (`web` or `mobile`). The `scope` claim is a space-separated string instead of a JSON list. Access and refresh tokens are signed with separate keys and carry a different `aud`. Treat tokens as opaque, as [Compatibility](compatibility.md#tokens) says.
- **Cookies.** The refresh cookie is set with `Path=/` instead of `/api/v1/auth`. Two cookies are new: the device cookie (`endurain_device`) and the identity-provider binding cookie (`endurain_idp_binding`). In `production` and `demo` all three carry the `__Host-` prefix. A web browser signs in again after the upgrade and counts as a new device once.

**Signing in**

- **Sign-in steps.** Every answer of `POST /auth/login`, `POST /auth/mfa/verify`, `POST /auth/password-change` and `POST /auth/sessions/{session_id}/tokens` carries a required `next_step`: `mfa` (with `mfa_challenge` and `methods`), `password_change` (with `password_change_challenge`), `exchange` (mobile: `session_id` and `device_id`) or `tokens`. `mfa_required`, `username` and `message` are gone, and `POST /auth/login` answers `200` for every step (a web client's MFA step was `202`). Switch on `next_step`; a value the client does not know means the app needs an update, so stop the sign-in and keep no partial state. See [Sign-in steps](authentication.md#sign-in-steps).
- **`X-Client-Type`** on the `/auth/` routes: a missing or unknown value is `422` instead of `400`.
- **Token exchange route.** The PKCE exchange moved from `POST /public/idp/session/{session_id}/tokens` to `POST /auth/sessions/{session_id}/tokens`, for password and SSO sign-ins alike. Its `X-Client-Type` must match the one the sign-in started with (`400` otherwise), and its body takes only `code_verifier` (any other member is `422`).
- **PKCE on mobile password sign-in.** `code_challenge` and `code_challenge_method` are form fields of `POST /auth/login`, next to `username` and `password`, instead of optional query parameters. Both are required for `mobile` and refused for `web`. A mobile password sign-in finishes with `exchange`, never tokens.
- **MFA step.** `POST /auth/mfa/verify` takes `{"mfa_challenge": …, "mfa_code": …}`: the challenge from the previous step replaces `username`, and the request carries no PKCE values. The challenge lives 5 minutes; the first two wrong codes are `400` and the third ends it with `401`, after which the client restarts the sign-in.
- **SSO sign-in with MFA.** An SSO sign-in now asks for the account's Endurain second factor. For an account with MFA, `POST /auth/sessions/{session_id}/tokens` answers `200` with `next_step: "mfa"`, and the client finishes at `POST /auth/mfa/verify` with the same `X-Client-Type`, which answers the tokens directly, never a second session to exchange.
- **Password change at sign-in** is new. When an administrator set the account's password, sign-in answers `next_step: "password_change"` and creates no session. The client asks for a new password and sends it with the challenge to `POST /auth/password-change`, which answers `exchange` (mobile) or `tokens` (web). See [Password change at sign-in](authentication.md#password-change-at-sign-in).
- **Known devices** are new. A mobile client sends `X-Device-Id` on `/auth/login`, `/auth/mfa/verify`, `/auth/password-change` and the token exchange, with the `device_id` the server returned on an earlier sign-in; a browser sends the device cookie. A sign-in from a device the account does not know sends the user a new-device notice, so a client that does not send its id makes every sign-in a new device. Store the id next to the tokens. Devices are listed and forgotten under `/profile/devices`.

**Refresh and logout**

- **Mobile refresh and logout.** `POST /auth/refresh` and `POST /auth/logout` take the refresh token in the JSON body, `{"refresh_token": "…"}`, instead of the `Authorization` header, which carries access tokens only. Both token bodies carry `next_step: "tokens"` and `refresh_token_expires_in`.
- **Logout** answers `200` with `{"idp_logout_url": …}` instead of `{"message": …}`, also for a refresh token that is missing, expired or already revoked (it was `401`). Open the URL in the system browser to also end the provider session, or ignore it.
- **No CSRF token.** The web token responses no longer carry `csrf_token`, and `X-CSRF-Token` is neither read nor allowed. `POST /auth/refresh` and `POST /auth/logout` from a web client must carry an `Origin` header the server allows (browsers add it) and are refused with `403` when `Sec-Fetch-Site` is `cross-site`. See [Authentication](authentication.md).

**Errors**

- **Sign-in errors.** Every refusal of `POST /auth/refresh`, and a dead pending sign-in at `POST /auth/mfa/verify` and `POST /auth/password-change`, is `401` with `urn:endurain:error:session-ended` and `WWW-Authenticate: Session`: sign in again, do not retry. A failed password sign-in challenges with `Session`, not `Bearer`. `invalid-token` means "refresh once and replay the request" on resource routes only. See [Authentication errors](errors-and-limits.md#authentication-errors).
- **One `429` type.** Every `429` is `too-many-requests`, with a `scope` member (`requests`, `sign-in`, `mfa`, `step-up`, `provider`, `follow-request`). `rate-limited` is gone.
- **Missing scope.** A `403` for a missing scope carries `WWW-Authenticate: Bearer error="insufficient_scope", scope="…"` and a `missing_scopes` member.
- **Required MFA** is new: when an administrator requires two-step verification, an account it covers without MFA gets `403` with `urn:endurain:error:mfa-enrolment-required` until it sets it up.

**Step-up and account security**

- **Step-up.** Sensitive requests carry one `step_up` object instead of the flat `current_password` and `mfa_code` fields: `current_password`, `mfa_code`, and for an account without a password `idp_reauth`. A step-up that does not verify is `403` with `urn:endurain:error:step-up-failed` (it was `401`). An account without a password that sends no `idp_reauth` gets `401` with `urn:endurain:error:idp-reauth-required`, and a locked-out one `429` with scope `step-up`. See [Operations that require step-up](account-security.md#operations-that-require-step-up).
- **MFA reads.** `GET /profile/mfa/status` gains `factors`, and the MFA step of a sign-in gains `methods`. Both are open sets.
- **Sessions.** Session reads carry `is_current` and `app_redirect_uri`, and session lists are paged. `last_login` of an identity-provider link is `last_login_at`.
- **Signing out everywhere.** `DELETE /profile/sessions` ended the other sessions only. Its replacement, `POST /profile/sessions/revoke`, ends every session including the current one, unless the body sends `keep_current: true`.
- **API keys** always expire (365 days by default; an administrator sets the maximum, 1 to 3650 days), and an account holds at most 25 active keys (`409` with `urn:endurain:error:api-key-limit`). `scopes` is an array instead of a string. A key could hold only `activities:upload`; it can now hold the data scopes listed in [API keys](api-keys.md), never the `account:security`, `account:export`, `account:integrations` or administrator scopes.

## Scopes

A scope name is lower-case kebab-case. The old names are refused like any unknown scope. See [Available scopes](auth-reference.md#available-scopes).

| Old scope | New scope |
| --------- | --------- |
| `profile` | `account`, split as described below |
| `health_targets:read`, `health_targets:write` | `health-targets:read`, `health-targets:write` |
| `identity_providers:read`, `identity_providers:write` | `identity-providers:read`, `identity-providers:write` |
| `server_settings:read`, `server_settings:write` | `server-settings:read`, `server-settings:write` |

- **`profile` was split.** Security operations (password, MFA, sessions, devices, API keys, identity-provider links, closing the account) need `account:security`, profile export and import need `account:export`, and linking and unlinking Garmin Connect and Strava (and `PUT /strava/client`) need `account:integrations`. Every user holds all three. The Garmin and Strava sync and import routes need the data scopes instead (`activities:write`, `gears:write`, `health:write`).
- **Health targets** used `health:read` and `health:write` in v0.20; they now need `health-targets:read` and `health-targets:write`.
- **`identity-providers:read` is administrator-only.** Regular users held `identity_providers:read` in v0.20.
- **New administrator scopes:** `users:read-all`, `api-keys:read`, `api-keys:write`, `server-settings:logs` and `server-settings:logs-clear`.
- **Enforcement.** A token's scopes are limited at every request to the scopes the user's role holds then, so a demotion applies at the next request; v0.20 trusted the token's claim. An API key holds the scopes it was created with, limited the same way by its owner's role.

## Identifiers and values

The ids of users, activities and their laps, sets, steps, streams and media, gear and components, health records, goals, notifications, identity providers and their links are UUID strings instead of integers. Session, API key and job ids were already UUID strings. Exercise titles keep integer ids, and the Strava and Garmin ids (`strava_activity_id`, `garminconnect_activity_id`) stay numbers.

- A malformed id in a path, query or body answers `422`, and an unknown one `404`.
- Do not assume a format or an order. Treat `id` as a string, also in the public provider list (`GET /public/idp`).
- An activity feed cursor issued before the upgrade answers `400`. Restart the feed without a cursor.
- Public share links and saved activity links from before the upgrade stop working, because the link carries the activity id. Share the activity again.
- **Enums are strings.** `activity_type`, activity `visibility`, media `media_type`, stream `stream_type` and notification `type` were integers and are now string names. The activity types are the keys of `GET /activities/types` (see [Data conventions](data-conventions.md#activity-types-and-sports)). The keys of the activity stats follow the same names: `snowshoeing`, `stand_up_paddleboarding` and `surfing` are `snow_shoeing`, `stand_up_paddling` and `surf`, and `other` is new.
- **Booleans.** `is_strava_linked` and `is_garminconnect_linked` of the profile are booleans instead of `0` or `1`.
- **Prices** (`purchase_value`, `total_components_cost`) are decimal strings such as `"129.90"` instead of numbers.

## Routes

Paths are under `/api/v1`. Routes not listed kept their method and path. A row without a new route was removed.

**Sign-in and public flows**

| v0.20 | v0.21 |
| ----- | ----- |
| `POST /public/idp/session/{session_id}/tokens` | `POST /auth/sessions/{session_id}/tokens` |
| `POST /sign-up/request`, `POST /sign-up/confirm` | `POST /public/sign-up/request`, `POST /public/sign-up/confirm` |
| `POST /password-reset/request`, `POST /password-reset/confirm` | `POST /public/password-reset/request`, `POST /public/password-reset/confirm` |
| `GET /public/server_settings` | `GET /public/server-settings` |
| `GET /public/server_settings/tile_maps_templates`, `GET /server_settings/tile_maps_templates` | `GET /public/server-settings/tile-maps-templates` |
| `GET /server_images/{server_img}` | `GET /public/server-settings/login-photo` |
| `GET /public/users/id/{user_id}` | |

**Your profile**

| v0.20 | v0.21 |
| ----- | ----- |
| `PUT /profile` | `PATCH /profile` |
| `POST /profile/image` | `PUT /profile/photo` |
| `PUT /profile/photo` (removed the photo) | `DELETE /profile/photo` |
| `PUT /profile/password` | `POST /profile/password/change` |
| `PUT /profile/privacy` | `PATCH /profile/privacy` |
| `GET /profile/default_gear`, `PUT /profile/default_gear` | `GET /profile/default-gear`, `PATCH /profile/default-gear` |
| `PUT /profile/goals` | `PUT /profile/goals/{goal_id}` |
| `GET /profile/export` | `POST /profile/export`, then `GET /profile/export/download` |
| `DELETE /profile/sessions` | `POST /profile/sessions/revoke` |
| `PUT /profile/mfa/enable`, `PUT /profile/mfa/disable` | `POST /profile/mfa/enable`, `POST /profile/mfa/disable` |
| `POST /profile/mfa/verify` | |
| `GET /profile/api_keys`, `POST /profile/api_keys`, `DELETE /profile/api_keys/{api_key_id}` | `GET /profile/api-keys`, `POST /profile/api-keys`, `DELETE /profile/api-keys/{api_key_id}` |
| `PATCH /profile/api_keys/{api_key_id}/revoke` | `POST /profile/api-keys/{api_key_id}/revoke` |
| `GET /profile/idp` | `GET /profile/identity-providers` |
| `GET /profile/idp/{idp_id}/link` | `POST /profile/identity-providers/{idp_id}/link` |
| `POST /profile/idp/{idp_id}/link/token` | |
| `POST /profile/idp/{idp_id}/unlink` | `POST /profile/identity-providers/{idp_id}/unlink` |
| `GET /followers/follow-requests` | `GET /profile/follow-requests` |
| `PATCH /followers/follow-requests/{follower_id}` | `POST /profile/follow-requests/{follower_id}/accept` |
| `DELETE /followers/follow-requests/{follower_id}` | `DELETE /profile/follow-requests/{follower_id}` |

**Users, followers and sessions**

| v0.20 | v0.21 |
| ----- | ----- |
| `GET /users/id/{user_id}` | `GET /users/{user_id}` |
| `GET /users/username/{username}` | `GET /users?username=` |
| `GET /users/username/contains/{username}` | `GET /users?username_contains=` |
| `GET /users/email/{email}` | |
| `PUT /users/{user_id}` | `PATCH /users/{user_id}` |
| `DELETE /users/{user_id}` | `POST /users/{user_id}/delete` |
| `PUT /users/{user_id}/approve` | `POST /users/{user_id}/approve` |
| `PUT /users/{user_id}/password` | `POST /users/{user_id}/password/change` |
| `POST /users/{user_id}/image` | `PUT /users/{user_id}/photo` |
| `DELETE /users/{user_id}/identity-providers/{idp_id}` | `POST /users/{user_id}/identity-providers/{idp_id}/unlink` |
| `GET /sessions/user/{user_id}` | `GET /users/{user_id}/sessions` |
| `DELETE /sessions/user/{user_id}` | `POST /users/{user_id}/sessions/revoke` |
| `DELETE /sessions/{session_id}/user/{user_id}` | `POST /users/{user_id}/sessions/{session_id}/revoke` |
| `GET /activities/users/{user_id}`, `GET /activities/users/{user_id}/stats` | `GET /users/{user_id}/activities`, `GET /users/{user_id}/activities/stats` |
| `/followers/users/{user_id}/followers` (`GET`, `POST`) | `/users/{user_id}/followers` (`GET`, `POST`) |
| `DELETE /followers/users/{user_id}/followers/{follower_id}` | `DELETE /users/{user_id}/followers/{follower_id}` |
| `GET /followers/users/{user_id}/following` | `GET /users/{user_id}/following` |
| `GET /followers/users/{user_id}/relationship` | `GET /users/{user_id}/relationship` |

**Activities, gear and health**

| v0.20 | v0.21 |
| ----- | ----- |
| `GET /activities/ingestion-jobs/{job_id}` | `GET /jobs/{job_id}` |
| `GET /activities/gears/{gear_id}` | `GET /activities?gear_id=` |
| `GET /activities/exercise-titles/all`, `GET /public/activities/exercise-titles/all` | `GET /activities/exercise-titles`, `GET /public/activities/exercise-titles` |
| `GET /gears/id/{gear_id}` | `GET /gears/{gear_id}` |
| `PUT /gears` | `PATCH /gears/{gear_id}` |
| `GET /gears/nickname/contains/{nickname}` | `GET /gears?nickname_contains=` |
| `GET /gears/type/{gear_type}` | `GET /gears?gear_type=` |
| `GET /gears/nickname/{nickname}` | |
| `GET /gear_components`, `POST /gear_components` | `GET /gear-components`, `POST /gear-components` |
| `PUT /gear_components` | `PATCH /gear-components/{gear_component_id}` |
| `DELETE /gear_components/{gear_component_id}` | `DELETE /gear-components/{gear_component_id}` |
| `GET /gear_components/types` | `GET /gear-components/types` |
| `GET /gear_components/gear_id/{gear_id}` | `GET /gears/{gear_id}/components` |
| `PUT /health/weight`, `/health/sleep`, `/health/steps`, `/health/water`, `/health/fasting`, `/health/poop` (id in the body) | `PATCH /health/weight/{id}` and likewise for each kind (id in the path) |
| `PUT /health/targets` | `PATCH /health/targets` |

**Notifications and integrations**

| v0.20 | v0.21 |
| ----- | ----- |
| `GET /notifications/page_number/{page_number}/num_records/{num_records}` | `GET /notifications` (cursor) |
| `GET /notifications/number` | `GET /notifications/unread-count` |
| `PUT /notifications/{notification_id}/mark_as_read` | `POST /notifications/{notification_id}/read` |
| `PUT /notifications/mark_all_as_read` | `POST /notifications/read` |
| `GET /garminconnect/activities`, `GET /garminconnect/gear`, `GET /garminconnect/health` | `POST /garmin/activities`, `POST /garmin/gear`, `POST /garmin/health` |
| `POST /garminconnect/link`, `POST /garminconnect/mfa` | `POST /garmin/link`, `POST /garmin/mfa` |
| `DELETE /garminconnect/unlink` | `POST /garmin/unlink` |
| `GET /strava/activities`, `GET /strava/gear` | `POST /strava/activities`, `POST /strava/gear` |
| `PUT /strava/link` | `POST /strava/link` |
| `PUT /strava/state/{state}` | `POST /strava/state` (the server issues the state) |
| `DELETE /strava/unlink` | `POST /strava/unlink` |
| `POST /strava/import/bikes`, `POST /strava/import/shoes` | `POST /strava/import/gear` |

**Administration**

| v0.20 | v0.21 |
| ----- | ----- |
| `GET /idp`, `POST /idp` | `GET /identity-providers`, `POST /identity-providers` |
| `GET /idp/templates` | `GET /identity-providers/templates` |
| `PUT /idp/{idp_id}` | `PATCH /identity-providers/{idp_id}` |
| `DELETE /idp/{idp_id}` | `POST /identity-providers/{idp_id}/delete` |
| `GET /server_settings`, `PUT /server_settings` | `GET /server-settings`, `PUT /server-settings` |
| `GET /server_settings/email` | `GET /server-settings/email/settings` |
| `POST /server_settings/email/test` | `POST /server-settings/email/test` |
| `POST /server_settings/upload/login`, `DELETE /server_settings/upload/login` | `PUT /server-settings/login-photo`, `DELETE /server-settings/login-photo` |

**New routes** a v0.20 client may use: `GET /sync`, `GET /jobs`, `GET /activities/{activity_id}/detail`, the health chart routes (`GET /health/weight/chart` and one for each kind), device management under `/profile/devices`, blocking under `/profile/blocked-users`, the email change under `/profile/email/change`, `POST /profile/username/change`, `POST /profile/delete-account`, the server log under `/server-settings/logs`, and `PUT /server-settings/email/settings`. The [API reference](api-reference.md) lists them all.

## Requests and responses

**Status codes**

- Writes that only carried a message answer `204` with no body: password reset, password change, MFA disable, user approval, `PUT /strava/client`, the email test, Garmin's MFA code and unlink.
- These answer `202` with a job instead of finishing in the request: `PATCH /activities` (bulk edit), `DELETE /gears/{gear_id}`, `POST /users/{user_id}/delete`, `POST /profile/export`, `POST /profile/import`, `POST /garmin/link`, `POST /strava/link`, `POST /strava/unlink` and the Garmin and Strava gear and health syncs. `POST /profile/delete-account` also answers `202`, without a job to poll.
- `POST /public/sign-up/request` answers `200` instead of `201`, and the photo uploads answer `{"photo_path"}` instead of a bare string.

**Lists**

- **One page shape.** The gear, health and user lists answered `{records, total, page_number, num_records}`; they answer `{items, total, page, num_records, next}`. The exercise titles, gear components, goals and their results, sessions, API keys, identity providers, identity-provider links and `GET /public/idp` were bare arrays and are pages now, with optional `page_number` and `num_records`.
- **Notifications** are a cursor page, `{items, next_cursor, num_records}`, and each item has a typed shape by `type`. `GET /notifications/unread-count` answers `{"count"}` instead of a bare number. `POST /notifications/read` marks the ids it is sent (at most 100), or every unread notification without a body. `DELETE /notifications/{notification_id}` is new.
- **Followers.** The follower, following and follow-request lists carry the public profile of each user in `users`, keyed by user id.
- **Filters** are query parameters with one vocabulary (see [Data conventions](data-conventions.md#list-filters)). `GET /activities` takes `name_contains` instead of `name`, and `gear_id`. `GET /gears` takes `active` instead of `show_inactive`, and `gear_type` and `nickname_contains`. `GET /users` takes `active`, `email_verified`, `pending_approval` and `external_auth` instead of the `show_*` flags, and `username` and `username_contains`. The health lists take `start_date` and `end_date`. `GET /activities/feed` takes `scope`.
- **`GET /users`** with only `users:read` answers `422` unless it sends `username` (exact) or `username_contains` (3 or more characters). The user directory shows less about other users.
- **Heavy fields are left out of lists.** The activity lists leave out `private_notes` and `import_info` (read the activity by id), and embed the media of the caller's own activities. The sleep list leaves out the stages and says `has_sleep_stages`.

**Fields**

- **Health records name their unit.** Weight: `weight`, `body_fat`, `body_water`, `bone_mass` and `muscle_mass` are `weight_kg`, `body_fat_percent`, `body_water_percent`, `bone_mass_kg` and `muscle_mass_kg`. Sleep: `avg_spo2`, `highest_spo2` and `lowest_spo2` are `avg_spo2_percent`, `highest_spo2_percent` and `lowest_spo2_percent`. Targets: `weight`, `sleep` and `fasting` are `weight_kg`, `sleep_seconds` and `fasting_seconds`. A request no longer sends `source`, `user_id` or, on an edit, `id`, and a fasting session no longer takes `actual_duration_seconds`.
- **Health instants carry a UTC offset.** Every instant in a health request (`fast_start_time`, `fast_end_time`, a poop record's `date_time`, a sleep's `sleep_start_time_gmt` and `sleep_end_time_gmt`, its stage times) must have one; `sleep_start_time_local` and `sleep_end_time_local` are wall-clock times without one.
- **Gear.** `initial_kms` (kilometres) is `initial_distance` (meters), and `created_at` is `acquired_on`, the acquisition date. A gear request no longer sends `user_id`, `strava_gear_id` or `garminconnect_gear_id`. A component's `expected_kms` is `expected_usage`: meters for gear tracked by distance, seconds for gear tracked by time. Only `GET /gears/{gear_id}/components` still carries a component's `current_distance` and `current_time`.
- **Activity streams** are typed by `stream_type`, a string name: `stream_waypoints` has the shape of its kind. See [Activity streams](health-and-streams.md#activity-streams).
- **Activities** gain `media` and `updated_at`. A finished activity job lists the activities it created in `activity_ids`.
- **Profile.** `PATCH /profile` no longer accepts `username` or `email`, and gains `weight_units`. Change the username at `POST /profile/username/change` and the email at `POST /profile/email/change`; both need step-up.
- **Users (administrators).** `PATCH /users/{user_id}` is a partial edit. It needs the administrator's `step_up` to change the email, access type, active flag, username or email-verified flag, and it answers `409` instead of activating a user who awaits approval: use `POST /users/{user_id}/approve`. `POST /users` without a `password` sends the new user an invitation when email is configured, and is refused with `password-required` otherwise; creating an administrator needs `step_up`.
- **Sign-up.** `POST /public/sign-up/request` takes only `name`, `username`, `email`, `preferred_language` and `password`; the profile fields (birthdate, city, units and the rest) are refused. The password is required there only when email verification is off; with verification on, it is chosen at `POST /public/sign-up/confirm`, which takes `{"token", "password"}`. Both answer `{"next_step"}` instead of `admin_approval_required`, `email_verification_required` and `message`. See [Confirming a link](public-endpoints.md#confirming-a-link).
- **Password reset.** `POST /public/password-reset/confirm` takes `password` instead of `new_password`.
- **MFA.** `POST /profile/mfa/enable` takes `totp_code` and `step_up` instead of `mfa_code` and `current_password`, and answers the backup codes. MFA enable, disable and backup-code requests, and starting an identity-provider link, take `revoke_other_sessions` (password changes already did).
- **Server settings.** `password_type` is gone. The public settings replace `allowed_redirect_schemes` with `allowed_redirect_uris`, the exact addresses an SSO sign-in may return to, so a native app can check that its callback is allowed before it opens the browser. The admin settings return `tileserver_api_key_set` instead of the key.
- **Strava.** `POST /strava/link` takes `code`, `scope` and `state` in the body. `PUT /strava/client` takes a `step_up` object next to the client id and secret.

**Concurrency**

- Reads of a versioned resource carry an `ETag`. `PUT` and `PATCH` on a versioned resource, and `DELETE` of an activity, gear, gear component, health record or goal, require `If-Match`. So do `POST /users/{user_id}/delete`, `POST /identity-providers/{idp_id}/delete` and `POST /health/fasting/{health_fasting_id}/complete`. A missing `If-Match` is `428` and a stale one `412`. In v0.20 only activities had an `ETag`. See [Concurrent edits](errors-and-limits.md#concurrent-edits-with-etag-and-if-match).

**Jobs**

- Every `202` except `POST /profile/delete-account` returns a job with an id and `Content-Location: /jobs/{id}`. Read it at `GET /jobs/{job_id}` and list your jobs at `GET /jobs`. See [Background operations](background-operations.md#reading-a-job).
- Poll the path `Content-Location` names and wait the seconds in `Retry-After` between polls; a finished job sends no `Retry-After`. The job statuses are renamed: `pending` → `queued`, `processing` → `running`, `completed` → `succeeded`, and `failed` stays. `completed_at` is `finished_at`. A client that treats an unknown status as "still running" polls a finished job until it gives up. A bulk import with failed files still ends `succeeded`; read `files_failed`.
- **Activity uploads.** A user may have at most 10 uploads open at once; the 11th `POST /activities/upload` is `409` with `urn:endurain:error:conflict`, and a replay with an `Idempotency-Key` that already has a job answers that job even at the limit. An unsupported or mismatched file type is `415` instead of `400`.
- **Garmin link.** `POST /garmin/link` answers `202` with a job. When the job reports `mfa_required`, send the code to `POST /garmin/mfa` and keep polling.

**Errors and limits**

- A request that does not fit the account's state is `409`, an unsupported file type is `415`, and a NUL character or out-of-range value is `422`. New typed problems include `password-too-short`, `password-breached`, `password-required`, `api-key-limit`, `mfa-enrolment-required`, `precondition-required` and `components-outside-gear-type`. See [Errors, concurrency and rate limits](errors-and-limits.md).
- A request under `/auth/` or `/public/` with a body over 64 KiB is `413`.
- `/openapi.json` is served only in development and demo installs. Use the published API reference otherwise.

## Single sign-on and identity providers

- **Mobile SSO needs an exact redirect address** listed in `ALLOWED_REDIRECT_URIS`. A `redirect` that is not listed exactly (other path, extra query or fragment) is `400`; the scheme is matched case-insensitively and the rest exactly. A claimed `https` address (Android App Link, iOS Universal Link) can be listed; v0.20 refused every `http` and `https` redirect.
- **Hand-off to the app.** For a custom-scheme address, the web page passes the `session_id` to the app only after the user confirms it; a claimed `https` address is forwarded at once. The app reads `session_id`, or `error`, from the query of the deep link. A failed sign-in that started from an app now returns to the app with `error` (`sso_failed`, `sso_email_missing`, `sso_email_unverified`, `sso_auto_create_disabled`, `sso_link_by_email_disabled`, `sso_approval_pending`, `sso_account_disabled`) instead of the web login page.
- **An SSO sign-in is bound to the browser that started it.** Open the login in a browser that keeps cookies (system browser, Custom Tabs, `ASWebAuthenticationSession`) and finish it there: the `endurain_idp_binding` cookie must come back on the callback. Start it on the `ENDURAIN_HOST` origin, over `https` in production and demo. A login started on a LAN address or another host name is refused at the callback with `400` and "Invalid or expired OAuth state". See [OAuth/SSO and PKCE](oauth-sso-pkce.md).
- **Provider API.** Creating, editing and deleting a provider needs step-up, and an edit or delete needs `If-Match`. `jwks_uri` is gone, because the signing keys come from the discovery document. `client_id` is required when creating a provider. Providers are typed (`oidc` needs an `issuer_url` and the `openid` scope), `saml` is refused (existing `saml` providers became `oauth2`), and there is one provider per issuer. A `client_id` or `client_secret` sent as `null` is refused with `422` instead of clearing the credential. `icon` takes only a built-in key (`authelia`, `authentik`, `casdoor`, `keycloak`, `pocketid`), and an uploaded icon is set at `PUT /identity-providers/{idp_id}/icon`. Reads gain `version`, `icon_uploaded`, `has_linked_users`, `link_by_email` and `sync_email`.
- **Locked fields.** The slug, `client_id`, provider type, issuer and endpoints cannot change while users are linked: `409` with `urn:endurain:error:identity-provider-locked`.
- **Reserved slugs:** `login`, `link`, `callback`, `icon` and `backchannel-logout`.
- **Linking by email and email sync** are per-provider switches, `link_by_email` and `sync_email`. Linking by email also requires the Endurain account's own email to be verified. An existing account is not changed before its second factor passes.
- **Unverified emails.** A provider email that is not verified never matches or creates an account. It is refused with `sso_email_unverified`, before any account is looked up. v0.20 created an account from it.
- **Last sign-in method.** Unlinking a provider answers `409` with `urn:endurain:error:last-sign-in-method` (it was `400`) when the account would have no other way to sign in. A disabled provider does not count, and a password counts only when the account's type may sign in with one.
- **Linking a provider.** `POST /profile/identity-providers/{idp_id}/link` takes a `step_up` body and an optional `redirect`, and answers `{"authorization_url"}`. With a native `redirect` that URL is an Endurain address, `GET /public/idp/link?ticket=...`, for the system browser. The one-time link-token route is removed. See [Linking accounts](oauth-sso-pkce.md#linking-accounts).
- **Disabling a provider** ends the sessions it signed in.

## Emails and links

- Links in emails carry the token in the URL fragment (`#token=`), so it stays out of logs and `Referer` headers: password reset (`/reset-password#token=`), sign-up confirmation and invitation (`/signup/confirm#token=`), and email change and its cancellation (`/confirm-email-change#token=`, `/cancel-email-change#token=`). The web app still reads `?token=` on `/reset-password`, so a reset link sent before the upgrade works. Sign-up verification links moved from `/verify-email` to `/signup/confirm`, so one sent before the upgrade no longer opens; the user asks for a new one.
- **Email change** is a new flow. `POST /profile/email/change` (with step-up) emails a link to the new address, and `POST /public/email-change/confirm` (`204`) switches the address when the person presses the button on the page. The old address gets a link to cancel it. See [Confirming a link](public-endpoints.md#confirming-a-link).

## Profile export and import

- **Export runs as a job.** `GET /profile/export` streamed the archive; now `POST /profile/export` takes a `step_up` body and answers `202` with a job, and `GET /profile/export/download` returns the archive for two hours after the job succeeds. `POST /profile/import` answers `202` with a job instead of `201`. See [Profile export](account-security.md#profile-export) and [Background operations](background-operations.md#profile-export-and-import).
- A profile archive exported by an Endurain version before v0.21.0 cannot be imported. The job fails with `error_code: older_version` and nothing is imported. Export again after the upgrade.
- Sleep, steps, water, fasting and bowel movement records are now part of the export and import (v0.20 had only weight and targets).
- An import from a different account is refused (`wrong_account`): the archive's username or email must match the importing account's.

## Realtime

`POST /ws/ticket` answers `{"ticket"}`, needs `notifications:read`, and the ticket is bound to the session. The socket checks the browser's `Origin`, limits handshakes, and closes with `4401` when the session ends. An API key cannot open it. See [Realtime updates](realtime.md).

## Sync

`GET /sync` is new. It reports what changed in a user's records since a cursor, for clients that keep a local copy. See [Keeping a local copy in sync](sync.md).

## Checklist for client developers

1. Sign in again, and request the new scope names: `account` instead of `profile`, kebab-case instead of underscores, and `account:security`, `account:export` or `account:integrations` where the routes need them.
2. Treat every id as a UUID string, and drop any code that parses, sorts or compares ids as numbers.
3. Read enums (`activity_type`, `visibility`, `media_type`, `stream_type`, notification `type`) as strings and prices as decimal strings.
4. Move every renamed route (see [Routes](#routes)), and send `PATCH` with the id in the path for edits.
5. Rename the health and gear fields, read lists as `{items, …, next}` pages, and send the new filter names.
6. Send `X-Client-Type` on every `/auth/` request, drive sign-in by `next_step` (including `password_change`), and treat an unknown step as "update the app".
7. Send the mobile login PKCE values as form fields, `mfa_challenge` instead of `username` to `/auth/mfa/verify`, and exchange the session at `POST /auth/sessions/{session_id}/tokens`.
8. On mobile, send the refresh token in the JSON body of `/auth/refresh` and `/auth/logout`, and store and send `X-Device-Id`.
9. On a `401` with `session-ended`, sign in again without retrying. Refresh once and replay only on `invalid-token`.
10. Stop sending and reading CSRF tokens. A web client sends `Origin` on `POST /auth/refresh` and `POST /auth/logout`.
11. Send a `step_up` object on sensitive requests.
12. Send `If-Match` with the `ETag` you read on `PUT`, `PATCH` and `DELETE` of versioned resources, and refetch on `412`.
13. Follow `Content-Location` on every `202`, poll `GET /jobs/{job_id}`, and map the renamed job statuses (`queued`, `running`, `succeeded`, `failed`).
14. Register `com.endurain.endurain:/auth/sso/callback` for mobile SSO (or ask the operator to allow your address), open the SSO login in a browser that keeps cookies, and handle the `error` codes on the deep link.
15. Read email-link tokens from the URL fragment.
16. Export profile archives again, because archives from v0.20 cannot be imported.
