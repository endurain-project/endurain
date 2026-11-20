# Idempotency keys

A client that sends a request and never sees the answer cannot tell whether the server did the work. For a read that does not matter. For a create it does: repeating the request creates the record twice. Send an `Idempotency-Key` header with a create, and a repeat of the same request is answered with the first outcome instead of being done again.

The header follows the IETF draft [The Idempotency-Key HTTP Header Field](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/). The key is optional on every route that accepts it: a request without one behaves as it always did.

## The header

The value is one [RFC 9651](https://www.rfc-editor.org/rfc/rfc9651) Structured Field String: printable ASCII between double quotes, 1 to 255 characters. Only `\"` and `\\` are escapes. The quotes are part of the value:

```http
POST /api/v1/gear-components
Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"
Content-Type: application/json
```

Generate a new key, such as a random UUID, for each distinct request, and send the same key again when you repeat that request. A value that is not one quoted string (a bare value, an empty string, a longer one, a non-ASCII character, a list or a parameter) is refused with `400`.

## Where the key is accepted

<!-- generated:idempotency-routes -->

The routes that return a stored response keep it for 24 hours. The upload and the archive import keep their key on the import job instead, for as long as the job exists, so a repeat returns that job (see [Background operations](background-operations.md#activity-ingestion-jobs)).

The creates that return a secret or a single-use credential (`POST /profile/api-keys`, `POST /profile/mfa/setup`, `POST /profile/mfa/backup-codes`, `POST /strava/state` and `POST /ws/ticket`), the public `POST /public/onboarding` and the photo upload `POST /activities/{activity_id}/media` take no key. The first five must not have their answer kept by the server, and a repeat of each is a new request by design. The photo upload is already safe to repeat: the same file for the same activity is stored once.

## What a repeat gets

The server remembers a request by the key and the account that sent it, and by what the request asked for: the method, the path, the query and the JSON body. The body is compared as data, so key order and whitespace do not matter. The key belongs to the account, not to the credential: a session and an API key of the same user share their keys, and another user can send the same key without any effect on yours.

| Situation | Answer |
| --------- | ------ |
| The first request with this key | It runs and its answer is stored when it succeeds. |
| A repeat of a request that succeeded | The stored status, `Content-Type`, `Location`, `ETag`, `Content-Location`, `Cache-Control` and body, byte for byte. Nothing runs again: no second record, audit entry or event. The answer carries no header that marks it as a replay. |
| A repeat while the first request is still running | `409` with `urn:endurain:error:idempotency-key-in-flight` and `Retry-After`. Wait, then send it again. |
| The same key with another request | `422` with `urn:endurain:error:idempotency-key-reused`, whether the first request has finished or not. |
| A malformed key | `400` with `urn:endurain:error:idempotency-key-invalid`. |
| The server cannot reach its state store | `503` with `Retry-After`. A request with a key is refused rather than run unprotected; a request without one is not affected. |

The three errors carry `Link: <https://docs.endurain.com/integrate/idempotency/>; rel="describedby"`, which names this page.

A request that fails is not stored. The key is free again, so you can repeat the request, with the same key, once you have fixed what the answer says. A response of more than 256 KiB is sent but not stored, so a repeat of that request runs again.

## Lifetimes

| What | How long |
| ---- | -------- |
| A stored response | 24 hours from the first request. After that the key is new again. |
| The claim a running request holds on its key | 120 seconds. A request that crashes releases the key when the claim expires. |

## Limits to know

- **A crash at the wrong moment can repeat a create.** The server commits the record, then stores the answer. If the process stops between the two, the key holds a claim and no answer; a retry after the claim expires (120 seconds) runs the request again and creates the record a second time. A retry sooner than that is answered `409`.
- **A replay carries the `ETag` of the first answer.** If the record was edited since, the version moved on, so the next write that sends this `ETag` as `If-Match` gets `412`. Read the record again to get its current `ETag`, as for any other `412` (see [Concurrent edits](errors-and-limits.md#concurrent-edits-with-etag-and-if-match)).
- **Retry only what you can recognise.** Repeat a request after a network error, a timeout, a `502`, a `503` or a `409` with `idempotency-key-in-flight`. After a `4xx` answer the request was refused, and repeating it without a change gives the same answer.
