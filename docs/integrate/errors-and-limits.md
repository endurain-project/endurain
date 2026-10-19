# Errors, concurrency and rate limits

Behaviour that applies to every endpoint of the API.

## Error responses

Every error the API returns is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document with the media type `application/problem+json`. This holds whatever raised the error: a domain error, a request validation failure, an authentication failure or a rate-limit rejection. A client needs only one error path.

```json
{
  "type": "urn:endurain:error:not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Activity not found",
  "instance": "/api/v1/activities/42",
  "request_id": "5f0d3c1e8b7a4c9d"
}
```

| Member | Meaning |
| ------ | ------- |
| `type` | Stable URN for the kind of error. **Branch on this.** It is not a URL and it does not change between releases. `about:blank` means the status code says everything. |
| `title` | Short summary of the kind. The same for every occurrence of a `type`. |
| `status` | The HTTP status code, repeated in the body. |
| `detail` | Explanation of this occurrence. Safe to show to a user and never contains internal diagnostics. |
| `instance` | The request path. |
| `request_id` | The `X-Request-ID` of the request. Quote it in a bug report or to your server operator, who can find the exact log line with it. |
| `errors` | Field-level problems. Present only for a validation failure (`422`). |

Clients that only read `detail` keep working. Some errors carry extra members, such as `code` for a machine-readable subtype.

### Error types

<!-- generated:error-types -->

A request validation failure is `422` with `urn:endurain:error:validation-failed` and an `errors` list. Exceeding a rate limit is `429` with `urn:endurain:error:rate-limited`. An error raised without a specific type uses a slug of the HTTP status phrase.

### Authentication errors

Authentication and authorization failures use the same shape. Typical causes:

| Status | Common causes |
| ------ | ------------- |
| `400` | Missing required fields, invalid client type, no pending MFA login |
| `401` | Invalid credentials, expired token, invalid MFA code |
| `403` | Insufficient permissions, missing required scope |
| `404` | Invalid session ID, user not found |
| `429` | Too many login or OAuth attempts |

## Concurrent edits with `If-Match`

Two clients that read the same activity and then save it would silently overwrite each other. To prevent this, reading an activity returns an `ETag`. Send it back in `If-Match` when you edit.

```http
GET /api/v1/activities/42
→ 200  ETag: "7"

PATCH /api/v1/activities/42
If-Match: "7"
```

- If the activity is still at that version, the edit applies and the response carries the new `ETag`.
- If someone else changed it in between, the API answers `412` with `urn:endurain:error:precondition-failed`. Read the activity again, reapply your change and retry.
- `If-Match: *` matches any version. Omitting the header skips the check, so existing clients keep working.

## Rate limits

Limits are counted per caller: an authenticated request is counted per access token, so users behind the same network address do not share a bucket, and an unauthenticated request is counted per client address.

<!-- generated:rate-limits -->

When you exceed a limit the API answers `429` and sets these headers:

| Header | Meaning |
| ------ | ------- |
| `Retry-After` | Seconds until you can retry. |
| `X-RateLimit-Limit` | The limit you hit. |
| `X-RateLimit-Remaining` | Always `0` on a `429`. |

Each endpoint uses one tier. The rate limits listed per endpoint in the authentication pages are these tiers, and the full API documentation shows the rest.
