# API reference (OpenAPI)

Browse every REST endpoint, its parameters, request bodies and responses. The schema is generated from the backend code at documentation build time, so it always matches the released version.

Each operation declares the errors it can answer (`401`, `403`, `404`, `409`, `412`, `413`, `415`, `428`, `429`, `503`) as [problem documents](errors-and-limits.md), the headers it sends (`ETag`, `Location`, `Content-Location`, `Retry-After`) and whether it requires `If-Match`. Every path starts with the API root, `/api/v1`.

For authentication, scopes, errors and rate limits see the other pages in this section. Requests cannot be sent from this page; use your own Endurain instance's `/docs` for that.

<swagger-ui src="./openapi.json"/>
