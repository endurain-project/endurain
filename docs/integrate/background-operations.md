# Background operations

Work that can take longer than a request is accepted with `202 Accepted` and runs in the background as a job. The `202` answers only "queued". Every job has an id, and its outcome is read at `GET /jobs/{job_id}`, which you poll. All paths are under `/api/v1`.

Every job answers the same envelope, so a client reads one vocabulary whatever the job is. Read the table first, then the section of the operation you call.

| Member | Meaning |
| ------ | ------- |
| `id` | The job's identifier, a UUID |
| `kind` | What the job does, from the table below. It also tells which other members the job carries |
| `status` | `queued`, `running`, `succeeded` or `failed`, for every kind of job |
| `error_code` | Why the job failed, from a closed set per kind. `null` unless `status` is `failed`, and for a kind that records no reason |
| `created_at`, `finished_at` | When the job was accepted and when it reached `succeeded` or `failed` (`null` until then) |

Each kind adds its own members to the envelope: `mfa_required` on the Garmin Connect link, `size_bytes` and `expires_at` on an export, `imported` on a profile import and the members listed under [Activity ingestion jobs](#activity-ingestion-jobs).

Every `202` carries the job in its body and two headers:

- `Content-Location` is the path of the job, `/api/v1/jobs/{job_id}`.
- `Retry-After` is the number of seconds to wait before the first poll.

The only `202` whose job you cannot read is [your own account deletion](#delete-your-account).

| Operation | Start | `kind` | Idempotency-Key |
| --------- | ----- | ------ | --------------- |
| Upload an activity file | `POST /activities/upload` | `activity_upload` | Yes |
| Import a ZIP archive of activity files | `POST /activities/bulk-import` | `activity_bulk_import` | Yes |
| Import the files in your folder on the server | `POST /activities/bulk-import/folder` | `activity_bulk_import` | No |
| Sync linked providers (last 24 hours) | `POST /activities/refresh` | `activity_refresh` | No |
| Sync Garmin Connect or Strava activities for a date range | `POST /garmin/activities`, `POST /strava/activities` | `activity_refresh` | No |
| Link Garmin Connect | `POST /garmin/link` | `garmin_link` | No |
| Sync Garmin Connect gear or health | `POST /garmin/gear`, `POST /garmin/health` | `garmin_sync_gear`, `garmin_sync_health` | No |
| Link Strava | `POST /strava/link` | `strava_link` | No |
| Sync Strava gear | `POST /strava/gear` | `strava_gear` | No |
| Unlink Strava | `DELETE /strava/link` | `strava_unlink` | No |
| Export your profile | `POST /profile/export` | `profile_export` | No |
| Import a profile | `POST /profile/import` | `profile_import` | No |
| Bulk edit activity visibility | `PATCH /activities` | `activities_bulk_edit` | No |
| Delete a user (administrators) | `POST /users/{user_id}/delete` | `user_deletion` | No |
| Delete your account | `POST /profile/delete-account` | `user_deletion`, not readable, see [below](#delete-your-account) | No |

The activity upload and the archive bulk import take an `Idempotency-Key`. Every other start route refuses a second request while one of the same kind is still running (see [`409`](#conflicts-409)), which is what protects a retry.

## Reading a job

`GET /jobs/{job_id}` reads one job. Poll the path that `Content-Location` names, and wait the seconds in `Retry-After` between polls (slower while a [realtime hint](realtime.md) connection is open). A job that is not finished sends `Retry-After` again; a final state, `succeeded` or `failed`, sends none, so stop there.

- Reading a job needs the scope its kind asks for: `activities:upload` for an activity upload, refresh or bulk import (an [API key](api-keys.md) works too), `activities:read` for a bulk edit, `account` for a Garmin Connect or Strava link or sync, `account:export` for a profile export or import, and `users:read-all` for an account deletion. Without it the read is `403`.
- You read the jobs you started. Any administrator with `users:read-all` can also read an account deletion. Another user's job is `404`, never `403`, so an id cannot be probed.
- An unknown id is `404`. So is a job whose record has expired. An activity ingestion job is kept for its retention period. Every other job is kept for a limited time after it starts: 7 minutes for a Garmin Connect link, 30 minutes for a Garmin Connect or Strava sync or a Strava link or unlink, 1 hour for a bulk edit, 2 hours for a profile export or an account deletion and 4 hours for a profile import. Starting the next job of the same kind replaces it sooner. Poll until a final state and do not rely on reading the result later.
- A `202` can also be refused with `503` when the server runs without a durable job worker and its in-process pool is full. Retry later.

## Listing your jobs

`GET /jobs` lists the jobs you started, newest first, as a keyset page: `items`, `num_records` and `next_cursor`. Pass `next_cursor` back as `cursor` for the next slice; `num_records` sets the slice size. Filter with `kind` (one of the values above) and `status`. Only the kinds your scopes can read are listed, so an API key with `activities:upload` sees its uploads, imports and refreshes alone.

Use it to pick a job up again when the client lost its id, for example after a restart: `GET /jobs?kind=profile_export` finds the export to download, and `GET /jobs?status=running` the work still in progress. A job is listed for as long as it can be read.

## Activity ingestion jobs

These routes start a job of one shape, `ActivityIngestionJobRead`, whatever the source of the activities.

```json
{
  "id": "0c0f8e0e-3f0b-4a50-9a58-6a1d0a2d5d11",
  "kind": "activity_upload",
  "filename": "morning-run.fit",
  "status": "succeeded",
  "error_code": null,
  "activity_ids": [412],
  "created_at": "2026-11-05T07:30:00Z",
  "updated_at": "2026-11-05T07:30:04Z",
  "finished_at": "2026-11-05T07:30:04Z"
}
```

| Member | Meaning |
| ------ | ------- |
| `kind` | `activity_upload`, `activity_bulk_import` or `activity_refresh` |
| `status` | `queued`, `running`, `succeeded` or `failed` |
| `error_code` | Set when `status` is `failed`: `unsupported_format`, `invalid_file`, `no_activities_found`, `processing_failed` or `provider_unavailable` |
| `activity_ids` | The activities the job created, once it succeeds |
| `files_total`, `files_done`, `files_failed` | Bulk import progress. A finished import with failed files still ends `succeeded` |
| `import_source` | The archive layout of a bulk import |
| `provider` | The provider a refresh syncs. Empty when it syncs every linked provider |
| `retry_after` | When a refresh that is waiting for a provider's rate limit runs again |
| `finished_at` | When the job reached `succeeded` or `failed` |

A refresh that is waiting for a provider's rate limit to clear is `queued` with `retry_after` set. It is not a failure: the job runs again by itself at `retry_after`.

Reading the job needs the `activities:upload` scope and accepts an API key. Starting a bulk import, a folder import, a refresh or a provider range sync needs `activities:write` and a signed-in session (an API key is not accepted).

### Upload an activity file

`POST /activities/upload`, a multipart form with the file in `file`. It needs the `activities:upload` scope and accepts a bearer token or an [API key](api-keys.md). The file is stored and queued, then the route answers `202` with the job. Cheap refusals come back at once as errors instead of a job: an unsupported extension or a file whose content is not that type is `415`, a file over the limit is `413`, and a file that is empty or fails the other content checks is `400`.

Send an `Idempotency-Key` header (up to 255 characters) to make a retry safe. A client that never saw the `202` has no job id to poll, and a replay without a key would import the file twice.

- **A replay with the same key and the same file** answers `202` with the original job, in whatever state it has now, and does not import again.
- **The same key with a different file** is `409`.
- **A key is scoped to the user** and to uploads. The same key may also be used on a bulk import.
- **A key is released** only when the job succeeded, recorded activities and every one of them has since been deleted. The same file can then be uploaded again under that key. A job that failed, is still running or created no activities keeps its key.

### Bulk import

`POST /activities/bulk-import?source=generic` takes a `.zip` archive in `file`. `source` is `generic` (the default, every supported activity file in the archive) or a provider export such as `strava`. `POST /activities/bulk-import/folder?source=...` imports the files that are in your own folder on the server instead, and removes them from the folder once they are safely staged.

Poll `GET /jobs/{job_id}` and read `files_done` and `files_failed` against `files_total`. A file that cannot be read counts as failed and does not stop the import.

- `409` when you already have a bulk import running. One runs per user. The problem document carries `job_id`, the running import, and the response carries `Content-Location` naming it, so a client that lost the `202` picks the import up again from there.
- `400` for an unknown `source`, a name that is not `.zip`, an archive with no importable files, or an empty folder.

`POST /activities/bulk-import` also takes an `Idempotency-Key` header (up to 255 characters), with the same rules as the [upload](#upload-an-activity-file): a repeat with the same key, the same archive and the same `source` answers `202` with the original import, in whatever state it has now (including while it is the import that is running), and does not start another. The same key with a different archive or `source` is `409`. A key is released only when its job record is removed. The folder import takes no key, because it has no request body to compare.

### Provider refresh and range sync

`POST /activities/refresh` queues a sync of the last 24 hours from the providers you have linked. `POST /garmin/activities` and `POST /strava/activities` take `start_date` and `end_date` (query parameters) and queue a sync of that range. The range may not be longer than 366 days, may not end in the future and may not start after its end, or it is `400`. A longer history is imported with several requests.

## Provider links and syncs

**Garmin Connect link.** `POST /garmin/link` with the login starts the sign-in and answers `202` with a `garmin_link` job. Poll it. The status is `running` while it signs in, then `succeeded` or `failed`. While Garmin Connect wants a code the status stays `running` and `mfa_required` is `true`. A failed link carries `error_code`: `invalid_credentials`, `incorrect_mfa`, `too_many_requests` or `internal`. When `mfa_required` is `true`, send the code to `POST /garmin/mfa` (`204`) within 3 minutes and keep polling. `POST /garmin/mfa` is `409` when no login is waiting for a code. `POST /garmin/link` is `409` while an attempt is running.

**Garmin Connect gear and health sync.** `POST /garmin/gear` and `POST /garmin/health` (with `start_date` and `end_date`, at most 31 days) answer `202` with a `garmin_sync_gear` or `garmin_sync_health` job. A second request of the same kind while one is queued or running is `409`.

**Strava link, gear sync and unlink.** `POST /strava/link` (the `state`, `code` and `scope` from the Strava callback), `POST /strava/gear` and `DELETE /strava/link` answer `202` with a `strava_link`, `strava_gear` or `strava_unlink` job. A second request of the same kind while one is queued or running is `409`. A link whose granted scopes are too few is refused at once with `400` and `urn:endurain:error:provider-scope-insufficient`. Unlinking revokes the authorization with Strava and deletes the activities and gear imported from it. When the user withdraws Endurain's access on Strava instead, Endurain clears the tokens at the next sync and `GET /profile` carries two read-only fields until the user connects again or the data is deleted: `strava_revoked_at`, when Strava access ended, and `strava_data_deletion_at`, 7 days later, when the Strava-synced activities and gear are deleted. Both are `null` otherwise, and neither can be set by a client.

A provider that answers with a rate limit makes the job `failed` (gear and health syncs) or `queued` with `retry_after` set (activity refreshes). The routes that start a provider sync (`/activities/refresh`, `/garmin/activities`, `/garmin/gear`, `/garmin/health`, `/strava/activities` and `/strava/gear`) are limited to 6 requests per minute.

## Profile export and import

**Export.** `POST /profile/export` takes the [step-up](account-security.md#step-up-authentication) body, `{"step_up": {...}}` (`current_password`, `idp_reauth` for an account without a password, and `mfa_code` when MFA is on) and answers `202` with a `profile_export` job. A succeeded export carries `size_bytes` and `expires_at`: fetch the ZIP with `GET /profile/export/download` before it expires (2 hours). A failed one carries `error_code`: `timed_out` or `processing_failed`. `409` while an export is running, `404` from the download when there is nothing finished to fetch. A client that lost the job finds it with `GET /jobs?kind=profile_export`.

**Import.** `POST /profile/import` takes a `.zip` archive in `file`, validates and stages it, and answers `202` with a `profile_import` job. The status is `running` for the database part (one transaction: a failed import leaves nothing behind) and for the writing of the files that follows. A succeeded import carries `imported`, the number of items of each kind. A failed one carries `error_code`: `invalid_file`, `too_large`, `too_many_activities`, `timed_out`, `wrong_account`, `files_incomplete` or `processing_failed`. `409` while an import is running.

## Bulk visibility edit

`PATCH /activities` with `{"visibility": "public"|"followers"|"private"}` changes the visibility of every activity you own and answers `202` with an `activities_bulk_edit` job. `409` while an edit is pending, and `400` when the body names no field to change. This route has no `If-Match`, because it addresses no single record.

## Delete a user (administrators)

`POST /users/{user_id}/delete` needs `users:write`, the user's `ETag` in `If-Match` (see [Errors, concurrency and rate limits](errors-and-limits.md#concurrent-edits-with-etag-and-if-match)) and the administrator's own [step-up](account-security.md#step-up-authentication) in the body's `step_up` object (`current_password`, or `idp_reauth` for an administrator without a password, and `mfa_code` when MFA is on). It signs the user out everywhere, deactivates the account and answers `202` with a `user_deletion` job, which then erases the data. Any administrator with `users:read-all` can read the job; it is kept for 2 hours. Until the account is gone, the administrator's user reads (`GET /users` and `GET /users/{user_id}`) carry `deletion_requested_at`, when the deletion was queued. It is `null` for an account that is not being deleted, and no client can set it.

- `409` with `urn:endurain:error:last-administrator` when the user is the only administrator; make another user an administrator first. A `409` (`urn:endurain:error:conflict`) naming the running job when a deletion is already pending.
- `403` when an administrator targets their own account. Use `POST /profile/delete-account` for that.
- `403` with `urn:endurain:error:step-up-failed` (or `401` `idp-reauth-required`) when the administrator's step-up does not verify; nothing is deleted.
- `412` and `428` as for any versioned write.
- If the job fails, the account stays deactivated and signed out. Endurain queues the deletion again every hour, up to five times, and after that an administrator deletes the account again.

## Delete your account

`POST /profile/delete-account` is confirmed with step-up in the body's `step_up` object (the current password, or a fresh identity-provider sign-in, and an MFA code when MFA is on; see [Account security](account-security.md)). It answers `202` with the `user_deletion` job (`"status": "queued"`), and it is fire and forget.

- **The account is closed before the answer.** Every session of the user ends, the account is deactivated, and the web client's refresh cookie is cleared on the response. The access token that made the request stops working too.
- **There is nothing for the user to poll.** The response has no `Content-Location`: reading an account deletion needs an administrator scope, and the user can no longer sign in to call anything. A client should treat the `202` as final: sign the user out locally and show that the account is being deleted.
- **How long the erasure takes is not fixed.** The data is removed in batches, so a large account takes longer. The job's record lives for 2 hours. There is no completion message.
- **It cannot be undone.** Export the profile first to keep a copy.
- `409` with `urn:endurain:error:last-administrator` when the user is the only administrator, and a `409` (`urn:endurain:error:conflict`) when a deletion is already pending. `403` with `urn:endurain:error:step-up-failed` when the step-up does not verify (or `401` `idp-reauth-required` when an account without a password sends no `idp_reauth`); nothing is deleted.

## Conflicts (`409`)

A start route answers `409` with `urn:endurain:error:conflict` while the same kind of work is already running for the user. The problem document carries the running job's id as `job_id`, and the response carries `Content-Location` naming it, so a client that lost the `202` of the first request picks the job up again from there:

- a bulk import, a profile export, a profile import, a bulk visibility edit, a Garmin Connect link, a Garmin Connect gear or health sync, a Strava link, gear sync or unlink, an account deletion.

A job that a server before this version started has no id to name; its `409` carries neither member. The same `409` code, with no job, also answers:

- an upload or a bulk import whose `Idempotency-Key` was used for a different request;
- `POST /garmin/mfa` when no login waits for a code.

Do not retry a `409` straight away. Poll the running job until it reaches a final state, then start again if you still need to. Activity uploads and refreshes have no such limit: you can queue several, and each gets its own job.

## Upload limits and formats

An attachment a record has one of (a profile photo, a user's photo, an identity provider's icon, the login page photo) is replaced with `PUT` on its path (`/profile/photo`, `/users/{user_id}/photo`, `/identity-providers/{idp_id}/icon`, `/server-settings/login-photo`), a multipart form with the image in `file`. The route answers `201` when there was nothing there before and `200` when it replaced an image; `DELETE` on the same path removes it.

Every upload route declares its body limit in the OpenAPI document as `x-max-body-bytes`: the largest file plus 1 MiB for the multipart framing. A body over the limit is `413` with `urn:endurain:error:payload-too-large`, refused before the route runs. A file of a type the route does not accept is `415` (`urn:endurain:error:unsupported-format` for an activity file, `urn:endurain:error:unsupported-media-type` for an image or media file); any other file the server cannot accept is `400`. See [Errors, concurrency and rate limits](errors-and-limits.md#upload-size-limits).

| Route | Accepts | Largest file |
| ----- | ------- | ------------ |
| `POST /activities/upload` | `.gpx`, `.fit`, `.tcx`, or any of them gzipped (`.gz`) | 200 MiB |
| `POST /activities/bulk-import` | A `.zip` of activity files (the same extensions, and `.fit.gz` entries). `source=strava` reads a Strava export | 500 MiB |
| `POST /profile/import` | A `.zip` made by `POST /profile/export` | 500 MiB |

An archive may also hold at most 2000 files of the same type and 2 GiB once unpacked. The upload routes in this table, and `POST /activities/bulk-import/folder`, are limited to 20 requests per minute. See [Supported types](supported-types.md) for the activity types a file can map to.

## Realtime hint

A client that holds a [WebSocket](realtime.md) can learn that a job changed without waiting for its next poll. The server sends `{"message": "JOB_STATUS_CHANGED", "job_id": "<id>", "kind": "<kind>"}` to the user who started the job. The hint is best effort and carries no status: read the job at `GET /jobs/{job_id}`. It is sent each time a job reaches a final state, `succeeded` or `failed`, and also when a `garmin_link` job starts waiting for an MFA code.

An activity refresh waiting for a rate limit sends no hint until it ends. A job that the server closes because it stopped making progress (an ingestion job idle for a day) and an account deletion send no hint, so keep polling them. A finished Garmin Connect or Strava gear sync also sends `GEARS_CHANGED`, and a Garmin Connect health sync `HEALTH_CHANGED`, which mean "fetch that data again" and do not name a job.
