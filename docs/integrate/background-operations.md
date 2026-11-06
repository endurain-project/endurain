# Background operations

Work that can take longer than a request is accepted with `202 Accepted` and runs in the background. The `202` answers only "queued". The outcome comes from a status route that you poll. All paths are under `/api/v1`.

Every status read answers the same envelope, so a client reads one vocabulary whatever the job is. Read the table first, then the section of the operation you call.

| Member | Meaning |
| ------ | ------- |
| `status` | `queued`, `running`, `succeeded` or `failed`, for every kind of job |
| `error_code` | Why the job failed, from a closed set per kind. `null` unless `status` is `failed`, and for a kind that records no reason |
| `id` | The job's identifier, for a job that has one of its own (an ingestion job). `null` for work that is one per user and kind |
| `created_at`, `finished_at` | When the job was accepted and when it ended, for a kind that records them (an ingestion job). `null` otherwise |

Each kind adds its own members to the envelope: `kind` on a provider sync, `mfa_required` on the Garmin Connect link, `size_bytes` and `expires_at` on an export, `imported` on a profile import and the members listed under [Activity ingestion jobs](#activity-ingestion-jobs).

Every `202` carries two headers, so a client does not build the status URL itself:

- `Content-Location` is the path of the status route to poll (for example `/api/v1/activities/ingestion-jobs/0c0f8e0e-...` or `/api/v1/garmin/sync/gear`). It tells an ingestion job from a sync status, which the body alone does not.
- `Retry-After` is the number of seconds to wait before the first poll.

The only `202` with no status route is [your own account deletion](#delete-your-account).

| Operation | Start | Poll | Idempotency-Key |
| --------- | ----- | ---- | --------------- |
| Upload an activity file | `POST /activities/upload` | `GET /activities/ingestion-jobs/{job_id}` | Yes |
| Import a ZIP archive of activity files | `POST /activities/bulk-import` | `GET /activities/ingestion-jobs/{job_id}` | Yes |
| Import the files in your folder on the server | `POST /activities/bulk-import/folder` | `GET /activities/ingestion-jobs/{job_id}` | No |
| Sync linked providers (last 24 hours) | `POST /activities/refresh` | `GET /activities/ingestion-jobs/{job_id}` | No |
| Sync Garmin Connect or Strava activities for a date range | `POST /garmin/activities`, `POST /strava/activities` | `GET /activities/ingestion-jobs/{job_id}` | No |
| Link Garmin Connect | `POST /garmin/link` | `GET /garmin/link/status` | No |
| Sync Garmin Connect gear or health | `POST /garmin/gear`, `POST /garmin/health` | `GET /garmin/sync/{kind}` | No |
| Link Strava | `POST /strava/link` | `GET /strava/sync/link` | No |
| Sync Strava gear | `POST /strava/gear` | `GET /strava/sync/gear` | No |
| Unlink Strava | `DELETE /strava/link` | `GET /strava/sync/unlink` | No |
| Export your profile | `POST /profile/export` | `GET /profile/export` | No |
| Import a profile | `POST /profile/import` | `GET /profile/import` | No |
| Bulk edit activity visibility | `PATCH /activities` | `GET /activities/bulk-edit` | No |
| Delete a user (administrators) | `POST /users/{user_id}/delete` | `GET /users/{user_id}/deletion` | No |
| Delete your account | `POST /profile/delete-account` | None, see [below](#delete-your-account) | No |

The activity upload and the archive bulk import take an `Idempotency-Key`. Every other start route refuses a second request while one of the same kind is still running (see [`409`](#conflicts-409)), which is what protects a retry.

## Polling

A status route reads a record that the job updates. Poll the route that `Content-Location` names, and wait the seconds in `Retry-After` between polls (slower while a [realtime hint](realtime.md) connection is open). A status read that is not finished sends `Retry-After` again; a final state, `succeeded` or `failed`, sends none, so stop there.

- A status read with nothing recorded answers `200` with `null`: `GET /activities/bulk-edit`, `GET /garmin/link/status`, `GET /garmin/sync/{kind}`, `GET /strava/sync/{kind}`, `GET /users/{user_id}/deletion`, `GET /profile/export` and `GET /profile/import`. That is the answer before the first start and once a record has expired. An ingestion job is read by its id, so an unknown id is `404`. The records of these operations are kept for a limited time after they start: 7 minutes for a Garmin Connect link, 30 minutes for a Garmin Connect or Strava sync or a Strava link or unlink, 1 hour for a bulk edit, 2 hours for a profile export or an account deletion and 4 hours for a profile import. Poll until a final state and do not rely on reading the result later.
- An ingestion job of another user is `404`, never `403`, so an id cannot be probed.
- A `202` can also be refused with `503` when the server runs without a durable job worker and its in-process pool is full. Retry later.

## Activity ingestion jobs

These routes return one job shape, `ActivityIngestionJobRead`, so a client has one thing to poll.

```json
{
  "id": "0c0f8e0e-3f0b-4a50-9a58-6a1d0a2d5d11",
  "kind": "upload",
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
| `kind` | `upload`, `bulk_import` or `refresh` |
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

Poll `GET /activities/ingestion-jobs/{job_id}` and read `files_done` and `files_failed` against `files_total`. A file that cannot be read counts as failed and does not stop the import.

- `409` when you already have a bulk import running. One runs per user. The problem document carries `job_id`, the running import, and the response carries `Content-Location` naming its status route, so a client that lost the `202` picks the import up again from there.
- `400` for an unknown `source`, a name that is not `.zip`, an archive with no importable files, or an empty folder.

`POST /activities/bulk-import` also takes an `Idempotency-Key` header (up to 255 characters), with the same rules as the [upload](#upload-an-activity-file): a repeat with the same key, the same archive and the same `source` answers `202` with the original import, in whatever state it has now (including while it is the import that is running), and does not start another. The same key with a different archive or `source` is `409`. A key is released only when its job record is removed. The folder import takes no key, because it has no request body to compare.

### Provider refresh and range sync

`POST /activities/refresh` queues a sync of the last 24 hours from the providers you have linked. `POST /garmin/activities` and `POST /strava/activities` take `start_date` and `end_date` (query parameters) and queue a sync of that range. The range may not be longer than 366 days, may not end in the future and may not start after its end, or it is `400`. A longer history is imported with several requests.

## Provider links and syncs

These keep a small status record instead of an ingestion job.

**Garmin Connect link.** `POST /garmin/link` with the login starts the sign-in and answers `202`. Poll `GET /garmin/link/status`. The status is `running` while it signs in, then `succeeded` or `failed`. While Garmin Connect wants a code the status stays `running` and `mfa_required` is `true`. A failed link carries `error_code`: `invalid_credentials`, `incorrect_mfa`, `too_many_requests` or `internal`. When `mfa_required` is `true`, send the code to `POST /garmin/mfa` (`204`) within 3 minutes and keep polling. `POST /garmin/mfa` is `409` when no login is waiting for a code. `POST /garmin/link` is `409` while an attempt is running. The status is `null` when no attempt is recorded.

**Garmin Connect gear and health sync.** `POST /garmin/gear` and `POST /garmin/health` (with `start_date` and `end_date`, at most 31 days) answer `202` with the envelope and `kind`. Poll `GET /garmin/sync/{kind}`, where `kind` is `gear` or `health`. The status is `null` when no sync is recorded. A second request of the same kind while one is queued or running is `409`.

**Strava link, gear sync and unlink.** `POST /strava/link` (the `state`, `code` and `scope` from the Strava callback), `POST /strava/gear` and `DELETE /strava/link` answer `202` with the envelope and `kind`. Poll `GET /strava/sync/{kind}`, where `kind` is `link`, `gear` or `unlink`. The status is `null` when no sync is recorded. A second request of the same kind while one is queued or running is `409`. A link whose granted scopes are too few is refused at once with `400` and `urn:endurain:error:provider-scope-insufficient`. Unlinking revokes the authorization with Strava and deletes the activities and gear imported from it. When the user withdraws Endurain's access on Strava instead, Endurain clears the tokens at the next sync and `GET /profile` carries two read-only fields until the user connects again or the data is deleted: `strava_revoked_at`, when Strava access ended, and `strava_data_deletion_at`, 7 days later, when the Strava-synced activities and gear are deleted. Both are `null` otherwise, and neither can be set by a client.

A provider that answers with a rate limit makes the job `failed` (gear and health syncs) or `queued` with `retry_after` set (activity refreshes). The routes that start a provider sync (`/activities/refresh`, `/garmin/activities`, `/garmin/gear`, `/garmin/health`, `/strava/activities` and `/strava/gear`) are limited to 6 requests per minute.

## Profile export and import

**Export.** `POST /profile/export` takes the [step-up](account-security.md#step-up-authentication) body, `{"step_up": {...}}` (`current_password`, `idp_reauth` for an account without a password, and `mfa_code` when MFA is on) and answers `202` with the envelope. Poll `GET /profile/export`. A succeeded export carries `size_bytes` and `expires_at`: fetch the ZIP with `GET /profile/export/download` before it expires (2 hours). A failed one carries `error_code`: `timed_out` or `processing_failed`. `409` while an export is running, `404` from the download when there is nothing finished to fetch.

**Import.** `POST /profile/import` takes a `.zip` archive in `file`, validates and stages it, and answers `202`. Poll `GET /profile/import`. The status is `running` for the database part (one transaction: a failed import leaves nothing behind) and for the writing of the files that follows. A succeeded import carries `imported`, the number of items of each kind. A failed one carries `error_code`: `invalid_file`, `too_large`, `too_many_activities`, `timed_out`, `wrong_account`, `files_incomplete` or `processing_failed`. `409` while an import is running.

## Bulk visibility edit

`PATCH /activities` with `{"visibility": "public"|"followers"|"private"}` changes the visibility of every activity you own and answers `202` with the envelope. Poll `GET /activities/bulk-edit`. `409` while an edit is pending, and `400` when the body names no field to change. This route has no `If-Match`, because it addresses no single record.

## Delete a user (administrators)

`POST /users/{user_id}/delete` needs `users:write`, the user's `ETag` in `If-Match` (see [Errors, concurrency and rate limits](errors-and-limits.md#concurrent-edits-with-etag-and-if-match)) and the administrator's own [step-up](account-security.md#step-up-authentication) in the body's `step_up` object (`current_password`, or `idp_reauth` for an administrator without a password, and `mfa_code` when MFA is on). It signs the user out everywhere, deactivates the account and answers `202` with the envelope. A background job then erases the data. An administrator polls `GET /users/{user_id}/deletion` (needs `users:read_all`); the record is kept for 2 hours.

- `409` when the user is the only administrator, or when a deletion is already pending.
- `403` when an administrator targets their own account. Use `POST /profile/delete-account` for that.
- `403` with `urn:endurain:error:step-up-failed` (or `401` `idp-reauth-required`) when the administrator's step-up does not verify; nothing is deleted.
- `412` and `428` as for any versioned write.
- If the job fails, the account stays deactivated and signed out. Endurain queues the deletion again every hour, up to five times, and after that an administrator deletes the account again.

## Delete your account

`POST /profile/delete-account` is confirmed with step-up in the body's `step_up` object (the current password, or a fresh identity-provider sign-in, and an MFA code when MFA is on; see [Account security](account-security.md)). It answers `202` with the envelope (`"status": "queued"`), and it is fire and forget.

- **The account is closed before the answer.** Every session of the user ends, the account is deactivated, and the web client's refresh cookie is cleared on the response. The access token that made the request stops working too.
- **There is nothing for the user to poll.** `GET /users/{user_id}/deletion` needs an administrator scope, and the user can no longer sign in to call anything. A client should treat the `202` as final: sign the user out locally and show that the account is being deleted.
- **How long the erasure takes is not fixed.** The data is removed in batches, so a large account takes longer. The job's record lives for 2 hours. There is no completion message.
- **It cannot be undone.** Export the profile first to keep a copy.
- `409` when the user is the only administrator, or a deletion is already pending. `401` when step-up fails.

## Conflicts (`409`)

A start route answers `409` with `urn:endurain:error:conflict` while the same kind of work is already running for the user. For the operations that have a status route, the response carries `Content-Location` naming it (the status of the work that is running), and a bulk import also carries the running job's id as the `job_id` member of the problem document:

- a bulk import, a profile export, a profile import, a bulk visibility edit, a Garmin Connect link, a Garmin Connect gear or health sync, a Strava link, gear sync or unlink, an account deletion (this one carries no `Content-Location`);
- an upload or a bulk import whose `Idempotency-Key` was used for a different request;
- `POST /garmin/mfa` when no login waits for a code.

Do not retry a `409` straight away. Poll the running operation until it reaches a final state, then start again if you still need to. Activity uploads and refreshes have no such limit: you can queue several, and each gets its own job.

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

A client that holds a [WebSocket](realtime.md) can learn that a job changed without waiting for its next poll. The server sends `{"message": "JOB_STATUS_CHANGED", "job": "<name>"}`. The hint is best effort and carries no status: read the status from the poll route. It is sent each time a job reaches a final state, `succeeded` or `failed`:

| `job` | Sent when |
| ----- | --------- |
| `ingestion:<job id>` | An **upload**, a **bulk import** or a **provider refresh or range sync** reaches `succeeded` or `failed`. It is not sent while a refresh waits for a rate limit |
| `garmin-link` | The Garmin Connect link needs an MFA code, and when it ends `succeeded` or `failed` |
| `garmin:gear`, `garmin:health` | A Garmin Connect gear or health sync ends |
| `strava:link`, `strava:gear`, `strava:unlink` | A Strava link, gear sync or unlink ends |
| `profile:export`, `profile:import` | A profile export or import ends |
| `activities:bulk-edit` | A bulk visibility edit ends |

A job that the server closes because it stopped making progress (an ingestion job idle for a day) and an account deletion send no hint, so keep polling them. A finished Garmin Connect or Strava gear sync also sends `GEARS_CHANGED`, and a Garmin Connect health sync `HEALTH_CHANGED`, which mean "fetch that data again" and do not name a job.
