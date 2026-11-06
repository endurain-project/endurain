# HTTP API conventions

Every route follows one resource model, so a client that has learned one resource can use the next without reading
its code. This page is the reference for the shape of the HTTP API: URLs, methods, status codes, headers, request
and response bodies, uploads, the OpenAPI contract and the client documentation.

Related pages go deeper on one topic each:

- versioned writes: [Optimistic concurrency](optimistic-concurrency.md);
- who the caller is: [Auth boundary](auth-boundary.md);
- what to record: [Audit trail](audit-trail.md);
- how ingestion jobs run: [Activity ingestion](activity-ingestion.md).

Rules marked **(test)** are enforced by `backend/tests/architecture/test_api_contract.py` or
`test_route_conventions.py`. A route that broke a rule before the test existed is listed in that test's register
with the change that will fix it. A register only shrinks: the test fails on a new violation, and on an entry that
no longer violates. Rules the code does not meet yet are listed under [Not yet met](#not-yet-met).

## Resources and URLs

A resource has a collection and an item:

| URL | Method | Does |
| --- | --- | --- |
| `/things` | `GET` | One page of the caller's things (`core.pagination.Page`) |
| `/things` | `POST` | Creates a thing |
| `/things/{thing_id}` | `GET` | Reads one thing, with its `ETag` |
| `/things/{thing_id}` | `PATCH` | Edits it, with `If-Match` |
| `/things/{thing_id}` | `DELETE` | Removes it, with `If-Match` |

- An item that can be edited or deleted can also be read by id **(test)**. Not counted as items: revocations from a
  list (API keys, sessions), relationships (follows, linked identity providers) and items served only as files.
- Paths are plural, kebab-case nouns. A resource has one item URL; a different view of it is a projection decided by
  the caller's scope, not a second path.
- Filtering and search are query parameters on the collection, never path segments: `<field>_contains` for text,
  `active=<bool>` for a state, and `start_date`/`end_date` for an inclusive range of local dates.
- A child collection sits under its parent (`/activities/{activity_id}/laps`).
- A route anyone may call without signing in lives under `/public`.

## Methods

- `PATCH` is a partial edit: an omitted field is kept, `null` clears a nullable field, and `not_clearable` lists the
  fields that cannot be cleared (`core.partial_update.NotClearable`).
- `PUT` replaces the whole resource: a field left out of the body is cleared. The only field kept when omitted is a
  write-only secret the server never returns. Every optional field of a `PUT` body is listed in the test with which
  of the two it is **(test)**. A partial edit is a `PATCH`.
- An action that is neither a replacement nor a partial edit is `POST /things/{thing_id}/<verb>` (`approve`,
  `revoke`, `read`, `complete`) **(test)**.
- A `POST` that creates a resource answers `201`.

## Status codes

| Code | When | Must carry |
| --- | --- | --- |
| `200` | A read, an edit that returns the resource, an action answered at once | `ETag` for a versioned resource |
| `201` | A resource was created | The resource, `Location` and `ETag` when it can be read by id **(test)** |
| `202` | Work was accepted for a background job | The status (a `core.job_status.JobStatus`: `queued`, `running`, `succeeded` or `failed`, `error_code`, `id` and the timestamps the kind records), `Content-Location` of the status resource, `Retry-After` **(test)**. A status read with nothing recorded is `200` with `null`, not `404` |
| `204` | A write with nothing to return | No body. A body that only carries a message is a `204` **(test)** |
| `400` | Input the schema accepted but the domain refuses | Problem document |
| `401` | The credential is missing, invalid or no longer valid (expired session, deleted or deactivated user) | `WWW-Authenticate` |
| `403` | Signed in but not allowed (missing scope, a refusal the caller may know about) | `WWW-Authenticate: Bearer error="insufficient_scope", scope="a b"` for a scope, and the `missing_scopes` member |
| `404` | Missing, or concealed from this caller (the same answer for both) | Problem document |
| `409` | Conflicts with the current state, including "already running" | The running job's `Content-Location` for "already running" |
| `412` / `428` | Stale or missing `If-Match` ([Optimistic concurrency](optimistic-concurrency.md)) | Problem document |
| `413` | The body is too large | Problem document |
| `415` | The uploaded file is a type the route does not accept | Problem document |
| `422` | The request does not match the schema | Problem document with `errors[]` |
| `429` | Rate limit or lockout | `Retry-After`: the seconds until a retry can succeed (a `TooManyRequestsError` with `retry_at` sets it) |
| `503` | A dependency is unavailable for a moment | `Retry-After` |

`406` is only for `Accept` negotiation, never for an upload.

## Headers

- **`ETag`** on every read and every write that returns a versioned resource; writes require `If-Match`.
- **`Location`** on a `201` whose resource has a `GET /{id}`: `core.location.set_location` writes the path.
- **`Content-Location` and `Retry-After`** on every `202` and on a status read that is not finished.
- **`Cache-Control: no-store`** on a response that carries a token or a secret: tokens, a new API key, an MFA secret
  or backup codes, a websocket ticket, a profile export. Other JSON is `private, no-cache` by default (`core.middleware.GetSemanticsMiddleware`). The `ETag` is the version for `If-Match`, not a validator of the body, so an authenticated read never answers `304`.
- A header a browser client must read is listed in `CORS_EXPOSE_HEADERS`, and one it must send in
  `CORS_ALLOW_HEADERS` (`core/middleware.py`).

## Errors

- Raise a `core.exceptions` error; the handler renders it as an RFC 9457 problem document. Never build an error body
  by hand: no `JSONResponse` with a 4xx or 5xx status outside `core/exceptions.py` and `core/problem_details.py`
  **(test)**.
- `detail` is a sentence for a person. Data a client acts on (missing scopes, a retry time) goes in an extension
  member, never as a Python repr in `detail`.
- A refusal that must not reveal whether something exists answers the same `404` as a missing record.

## Naming new fields

These rules are for new fields and parameters; existing names are not renamed to fit them.

- A boolean is `is_<state>` for a state the resource is in (`is_blocked`), `has_<thing>` for the presence of
  something (`has_local_password`), and a plain adjective when the field is a setting, filter or attribute that
  reads naturally as one (`active`, `read`, `discoverable`). Never a negation, and never `hide_*`/`show_*` for a
  new flag: state what is on.
- An instant is `<event>_at` and carries a UTC offset (`created_at`, `declined_at`).
- A calendar date is `<event>_date`, or `date` when the resource is about one day.
- A wall-clock time without a zone is `<event>_local`, as the request-bodies rule says.
- A measurement puts its unit in the name when the name can carry it (`weight_kg`, `sleep_seconds`, `*_percent`).
- A text filter on a collection is `<field>_contains`, naming the field it matches (`name_contains`,
  `message_contains`), and a state filter is `active=<bool>`.

## Request bodies

- Request schemas set `extra="forbid"` and bound every string and number.
- A request schema never accepts a field the server owns: `id`, `user_id`, `version`, `created_at`, `updated_at`,
  `source` or a provider id (`strava_*_id`, `garminconnect_*_id`) **(test)**. The resource comes from the path, the
  owner from the token, provenance from the code path that writes.
- A datetime is an instant and requires a UTC offset (`pydantic.AwareDatetime`) **(test)**. A wall-clock time is a
  `*_local` field documented as such.

## Response bodies

- An enum is a string, and a flag named `is_*` or `has_*` is a boolean **(test)**.
- A measurement states its unit in the field description: metres, seconds, metres per second, kilograms. A new field
  whose name can carry the unit does (`*_seconds`, `*_ml`). Money is a decimal string next to its currency.
- A timestamp is UTC with an offset.
- A list is a `Page`, or a `CursorPage` for a feed that grows at the head **(test)**. The only bare arrays are fixed
  catalogues read whole, named in the test.
- Optional data that is not shown to a caller is `null` or absent for that caller; what a non-owner sees is decided
  in the serializer, not left to the client.

## Uploads

- Every upload goes through `core/file_uploads.py` (`AGENTS.md`), and only that module imports `PIL` or
  `safeuploads` (import-linter `images-through-file-uploads`). One allow-list per upload kind lives there.
- Check that the caller owns the target before reading the body.
- A route that takes a file declares its body cap with `openapi_extra=core_middleware_body_limit.upload_limit(<its
  largest file>)`, reusing the constant its validator uses; the middleware refuses a bigger body before the route
  runs **(test)**.

## OpenAPI contract

- An endpoint docstring is the public OpenAPI description: what the endpoint does for a client, with no `Args:`,
  `Returns:` or `Raises:` sections and no internal parameter names **(test)**.
- `core.problem_details.ProblemDetailsFastAPI` names an operation by its handler (`operationId` is the function name), so
  the id and a generated client's method name do not change when a route moves; two handlers never share a name
  **(test)**. Rename the handler, never add a suffix.
- `core/openapi_contract.py` cuts an operation's description at the first Google section, so a docstring that still
  carries `Args:` or `Returns:` does not reach a client; a new route has none.
- A route that returns bytes declares its media types with `core.openapi_contract.binary_response` and
  `response_class=Response`.
- `core/openapi_contract.py` derives the rest for every operation: `401`/`403` from the security requirement, `404` from a
  path parameter, `413`/`415`/`409` from a body, an upload or a write, `429`/`503` for all, a required `If-Match` with
  `400`/`412`/`428`, `ETag` and `Location` on a versioned success response, and `readOnly` on `id`, `version`,
  `created_at` and `updated_at` of a schema a client does not send. A `202` lists `ACCEPTED_RESPONSE` and a response
  whose version is not a body field lists `ETAG_HEADERS` itself **(test)**.

## Client documentation

- `docs/integrate/` is the contract client authors build against. A change to a route, a status code or a body
  updates it in the same change.
- An API path written in `docs/integrate/`, `docs/reference/` or an endpoint docstring must exist **(test)**.
- A list that comes from the code (scopes, error types, rate limits) is a generated table
  ([Writing the documentation](writing-docs.md#tables-generated-from-the-code)), not a hand-copied one.
- A privacy or security default stated in `docs/features/` (visibility, session lifetime) is pinned by a test, so
  changing the default fails until the page changes too.

## Not yet met

These rules are not met everywhere yet. Each is tracked in the test registers above, or here when no test covers it:

- Several resources that can be edited have no `GET /{id}`, and their creates send no `Location`; no create sends an
  `ETag` yet.
- The one `202` with no status resource is the account owner's `POST /profile/delete-account`.
- Some secret-bearing responses lack `no-store`.
- Uploaded images are stored as received, with their metadata.
- Some enums are integers and some request schemas accept server-owned fields.
- Most endpoint docstrings still carry Google sections. The OpenAPI document cuts them, but the source should lose them.
