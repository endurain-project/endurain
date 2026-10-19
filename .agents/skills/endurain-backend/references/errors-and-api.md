# Errors and API conventions

## Raising errors

- Application layers (`service`, `crud`, pipeline, parsers) raise `core.exceptions.DomainError` subclasses, never `fastapi.HTTPException`.
- The app registers one handler that renders every error as an RFC 9457 problem document, so the durable-job worker and unit tests need no FastAPI.
- Pass a caller-safe message or nothing; the subclass supplies a default.
- Never put SQL, paths or stack detail in `detail` (it is returned verbatim); log diagnostics with `exc_info`.

| Exception | Status | Use when |
| --- | --- | --- |
| `NotFoundError` | 404 | Missing, or not visible to the caller and the code cannot tell which (prefer 404 over 403 to avoid confirming existence) |
| `AccessConcealedError` | 404 | The code *knows* it is refusing the caller and answers like a missing resource (invalid capability token, a follower network the caller may not view). Same response as `NotFoundError`; log a WARNING in the same function |
| `PermissionDeniedError` | 403 | Authenticated but not allowed |
| `InvalidInputError` | 400 | Well-formed but semantically unusable |
| `ConflictError` | 409 | Conflicts with current state (duplicates, races) |
| `PreconditionFailedError` | 412 | `If-Match` precondition failed |
| `UnsupportedFormatError` | 406 | Payload format cannot be processed |
| `UnsupportedMediaTypeError` | 415 | File media type not accepted |
| `PayloadTooLargeError` | 413 | Payload exceeds the accepted size (upload caps) |
| `ProcessingError` | 500 | Internal failure the caller cannot fix |

- New kind: subclass `DomainError` with `status_code`, `code`, `title`, `default_detail`.
- `code` becomes the response `type` URN (`urn:endurain:error:<code>`); clients match on it, so a released `code` never changes.
- A bare `HTTPException` is still tolerated in unconverted modules and is rendered as a problem document too.
- Persistence modules may not import `fastapi` (enforced by `TestLayerRules.test_persistence_raises_domain_errors_not_http_ones`).

## Problem document shape

- Members: `type` (URN), `title`, `status`, `detail`, `instance` (request path), `request_id`.
- `request_id` is the `X-Request-ID` the logging middleware assigned, so a user can quote it and you find the log line.
- The OpenAPI schema is patched so generated clients see the problem schema, not FastAPI's `HTTPValidationError`.
- The frontend reads it through `HttpError` (`status`, `type`, `detail`, `requestId`).

## Endpoints

- `response_model` on every JSON route (bytes routes declare `responses=` with the media type); status 200 GET, 201 POST create, 202 POST accepted for background processing, 204 DELETE.
- Routers validate and delegate; domain rules live in `service`.
- Authorization through `Depends`/`Security(auth_dependencies.check_scopes, scopes=[...])`.
- Blob routes addressed by a signed capability token answer 404, not 403, for a bad token, and log a WARNING.

## Pagination

- Offset lists return `core.pagination.Page[T]`, built with `Page.build(items, total, page, num_records)`; `next` is derived server-side.
- Defaults: 25 per page, maximum 200; child collections default to the maximum.
- `total` carries the same filters and access scoping as `items`.
- Lists that grow at the head (feeds) use `CursorPage` keyset pagination, not offset, so concurrent inserts cannot duplicate or skip rows.
- Batch sizes for maintenance and external I/O have their own constants (500 and 200); do not reuse the page size.

## Rate limiting

- Decorate with `@core_rate_limit.limiter.limit(<tier>)` and take `request: Request` as the first parameter.
- Tiers: `DEFAULT` 120/min, `WRITE` 30/min, `SENSITIVE` 10/min (auth, secrets), `UPLOAD` 20/min, `PROVIDER_SYNC` 6/min.
- Reads take the global default (`DEFAULT`, applied by the middleware); every write, upload or provider sync names its own tier, which `TestRouteConventions` enforces.
- Pick the tier by what the endpoint costs or exposes; an authenticated write of caller-supplied bytes is `UPLOAD`.
- Counters live in the shared state backend, so they hold across workers.

## After changing the API

- Regenerate the frontend client: `npm run gen:api` (see the `endurain-frontend` skill).
- Update `docs/reference/**` for the affected resource.
- Treat a changed response shape or error `code` as a breaking change in the commit (`!`).
