# Changes from v0.21 to v0.22

What changed between v0.21 and v0.22 for the people who run Endurain and for the clients that call its API. If you only use the Endurain web app on Docker, you need only the first two sections. For the rules that hold from now on, see [Compatibility between releases](compatibility.md).

## Before you upgrade

Back up the database and the `data` folder first. The upgrade cannot be undone: restoring the backup is the only way back to v0.21.

- **Upgrade from v0.21.x only, with every data migration finished.** Endurain refuses to start on a database at a revision this release does not know, which includes any database older than v0.21, before it changes anything. The error says to start the latest v0.21.x release and let it finish its upgrade and data migrations, or, for a database used by a newer release, to run that release or restore a backup taken before it. It also refuses while an install that has users still has one of the v0.21 data migrations 11, 12, 13 or 14 pending, and names the ones that have not finished. A new install has no users and is not affected.
- **On v0.20.x, go through v0.21 first.** Start the latest v0.21.x release, let its data migrations finish, then upgrade to v0.22. See [Changes from v0.20 to v0.21](changes-v0.20-to-v0.21.md).
- **The upgrade removes the v0.21 data migration records** and the table that maps the old integer ids to UUIDs. Restoring the backup is the only way back, because the downgrade is refused.
- **A password set before v0.21 may need a reset.** Since v0.21 Endurain compares passwords in Unicode NFC form, so the same text typed on different devices is the same password. v0.21 still accepted a password stored from the raw text and quietly re-saved it in NFC form at the next sign-in; v0.22 does not. A password is affected only if it contains an accented character that was entered in decomposed form (a base letter followed by a separate accent, as some keyboards and macOS or iOS text fields produce) and the account has not signed in since v0.21. Passwords with only plain ASCII characters, or with accented characters in composed form, are not affected. The account then answers like a wrong password. The user resets it with the emailed link, or an administrator [sets a password](../features/user-management.md#resetting-a-password). See [Accounts, sign-up and password reset](../features/accounts-and-sign-in.md#password-rules).

## Environment variables that stop startup

Endurain refuses to start while any of these variables is set. It logs every variable it finds, with where the setting lives now, and stops with an error that lists them all, so you can fix the deployment in one pass. Remove them from your environment, compose file and secret files, then start again. See [Supported environment variables](../getting-started/advanced-setup.md#supported-environment-variables) for the full list.

| Variable | Where the setting lives now |
| -------- | --------------------------- |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `SESSION_IDLE_TIMEOUT_ENABLED`, `SESSION_IDLE_TIMEOUT_HOURS`, `SESSION_ABSOLUTE_TIMEOUT_HOURS` | *Settings > Server settings > Access & security > Sessions* |
| `READ_NOTIFICATION_RETENTION_DAYS` | *Settings > Server settings > General > Data retention* |
| `REVERSE_GEO_PROVIDER`, `PHOTON_API_HOST`, `PHOTON_API_USE_HTTPS`, `NOMINATIM_API_HOST`, `NOMINATIM_API_USE_HTTPS`, `GEOCODES_MAPS_API`, `REVERSE_GEO_RATE_LIMIT` | *Settings > Server settings > Maps & location > Reverse geocoding* (service, host, HTTPS, rate limit and API key) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`, `SMTP_SECURE`, `SMTP_SECURE_TYPE`, `SMTP_PASSWORD`, `SMTP_PASSWORD_FILE` | *Settings > Server settings > Email* (host, port, security, username, sender and password) |
| `ALGORITHM`, `ALGORITHM_FILE` | Nowhere: tokens are always signed with HS256, so there is nothing to configure |

v0.21 saved the values of these variables (except `ALGORITHM` and `ALGORITHM_FILE`, which it ignored) into the database each time it started, so an install that ran v0.21 with a variable set already has its value stored and removing the variable loses nothing. The mail variables were saved only when `SMTP_HOST` was set, and an invalid value was skipped and the stored setting kept. Check the settings in *Settings > Server settings* after the upgrade.

## API changes

These changes affect clients of the administrator settings routes, which need the `server-settings:read` or `server-settings:write` scope.

- **`env_managed` is gone** from the answer of `GET /server-settings` and `PUT /server-settings` (`ServerSettingsAdminRead`), and from the answer of `GET /server-settings/email/settings` and `PUT /server-settings/email/settings` (`MailSettingsAdminRead`). Settings are no longer tied to environment variables, so no field is read-only for that reason. A client that reads `env_managed` must stop doing so.
- **The `409` for an environment-managed field is gone.** The two `PUT` routes used to answer `409` when the body changed a field that an environment variable set. They save the change now.

## Idempotency keys

- **Creates accept an optional `Idempotency-Key` header.** `POST /gear-components`, `/gears`, `/health/{fasting,poop,sleep,steps,water,weight}`, `/identity-providers`, `/profile/goals`, `/users` and `/users/{user_id}/followers` answer a repeat of a request, sent with the same key, with the first answer instead of creating the record again. A request without the header behaves as before. See [Idempotency keys](idempotency.md).
- **The key is a quoted string.** The header value is an RFC 9651 Structured Field String (`Idempotency-Key: "8e03978e-40d5-43e8-bc93"`), and the bare form is refused with `400` and `urn:endurain:error:idempotency-key-invalid`. This applies to the activity upload and the archive bulk import too: **a client that sent a bare key to those routes must now quote it.**
- **A key reused for another request is `422`.** The upload and the archive bulk import answered `409` when a key came back with a different file; they answer `422` with `urn:endurain:error:idempotency-key-reused` now, as every route that takes a key does. A `409` on these routes now means a request with the key is still running (`urn:endurain:error:idempotency-key-in-flight`) or another existing conflict.

- **A sleep record holds at most 1440 stages.** `POST /health/sleep` with more `sleep_stages` is `422`, and the schema publishes `maxItems`. The limit is one stage per minute of a day, the finest granularity of a stage.

## Requirements for bare-metal and development installs

- **Python 3.15** for the backend.
- **Node.js 26** for the frontend.

The Docker image already ships both, so a Docker install needs nothing. See [Setup a development environment](../developer-guide/setup-dev-env.md).
