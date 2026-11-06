# API reference (OpenAPI)

Browse every REST endpoint, its parameters, request bodies and responses. The schema is generated from the backend code at documentation build time, so it always matches the released version.

Each operation declares the errors it can answer (`401`, `403`, `404`, `409`, `412`, `413`, `415`, `428`, `429`, `503`) as [problem documents](errors-and-limits.md), the headers it sends (`ETag`, `Location`, `Content-Location`, `Retry-After`) and whether it requires `If-Match`. Every path starts with the API root, `/api/v1`. Each operation's `operationId` is the name of its handler (`read_users_me`), which does not change when the route moves; a generated client names its methods after it. A description is the prose of the handler's docstring. An operation lists the credentials it accepts: the bearer token (`OAuth2PasswordBearer`), the `X-API-Key` header (`ApiKey`, only where API keys work) and, on `POST /auth/refresh` and `POST /auth/logout`, the refresh cookie (`RefreshTokenCookie`). `X-Client-Type` and `X-CSRF-Token` are ordinary header parameters. The `?api_key=` query parameter is not listed because it is off by default; see [API keys](api-keys.md).

For authentication, scopes, errors and rate limits see the other pages in this section. Requests cannot be sent from this page; use your own Endurain instance's `/docs` for that.

<swagger-ui src="./openapi.json"/>
