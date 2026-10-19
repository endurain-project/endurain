# API key authentication

API keys provide a stateless, long-lived authentication mechanism for programmatic access and third-party integrations. Unlike JWT sessions, API keys do not require a login flow or token refresh, and are scoped to specific operations.

!!! warning "Security Notice"
    API keys are powerful credentials. Treat them like passwords: store them securely and never expose them in client-side code, public repositories, or logs.

## Key Format

API keys use the following format:

```
endurain_<43-character-base64url-random-string>
```

- **Prefix**: `endurain_` — identifies Endurain API keys in secret scanning tools (e.g., GitHub secret scanning)
- **Random part**: 256 bits of cryptographically secure random data (`secrets.token_urlsafe(32)`), encoded as a 43-character base64url string
- **Total length**: ~52 characters

The raw key is shown **once** at creation time and is never stored by the server (only the SHA-256 hash is stored). If lost, the key must be deleted and a new one created.

## Scopes

API keys are granted one or more API-key scopes at creation time. Currently only `activities:upload` is accepted; JWT-only scopes such as `profile`, `activities:read`, or `users:write` cannot be granted to API keys.

The key-management API rejects any requested scope outside the API-key allow-list. This keeps long-lived API keys limited to the endpoint that currently supports API-key authentication.

<!-- generated:api-key-scopes -->

## How to Authenticate with an API Key

API keys bypass the standard JWT and `X-Client-Type` requirements. Send the raw key using either option:

**Option 1: `X-API-Key` header (recommended):**

```http
POST /api/v1/activities/create/upload
X-API-Key: endurain_abc12345...
Content-Type: multipart/form-data

(file body)
```

**Option 2: `api_key` query parameter (for tools that cannot set custom headers):**

```http
POST /api/v1/activities/create/upload?api_key=endurain_abc12345...
Content-Type: multipart/form-data

(file body)
```

!!! warning "Query parameter delivery is disabled by default"
    The `?api_key=` query parameter is **disabled by default**. To enable it, set `ALLOW_API_KEY_QUERY_PARAM=true` in your environment. This option exists for self-hosted deployments where an integration cannot set custom request headers (e.g. certain webhook senders). When enabled, every request using this method emits a warning in the application log.

    Query-string credentials appear in server access logs, reverse-proxy logs, and browser history. Use the `X-API-Key` header whenever possible.

If both the `X-API-Key` header and the `?api_key=` query parameter are present, the **header takes precedence**.

## Endpoints That Accept API Keys

| Method | Endpoint | Required Scope | Description |
| ------ | -------- | -------------- | ----------- |
| `POST` | `/activities/create/upload` | `activities:upload` | Upload a .gpx, .tcx, .fit, or .gz activity file |

The upload endpoint also accepts JWT authentication through the same unified-auth dependency. JWT upload requests still require `Authorization: Bearer <access token>` and the `activities:upload` scope, but this endpoint does not require `X-Client-Type`.

## Managing API Keys

API keys are managed through the Endurain web UI (Settings → Security → API Keys) or via the REST API. All management endpoints require a valid JWT access token.

Creating an API key also requires step-up verification because the key is a long-lived credential:

- Local-password accounts must provide `current_password`
- Accounts with MFA enabled must also provide `mfa_code`
- SSO-only accounts may omit `current_password` because there is no local password to verify

**Create API Key Request:**

```http
POST /api/v1/profile/api_keys
Authorization: Bearer {access_token}
X-Client-Type: web
X-CSRF-Token: {csrf_token}
Content-Type: application/json

{
  "name": "Home Server Integration",
  "scopes": ["activities:upload"],
  "expires_at": "2027-01-01T00:00:00Z",
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | Yes | Human-readable label (max 100 characters) |
| `scopes` | Yes | Array of API-key scopes to grant. Currently only `activities:upload` is accepted |
| `expires_at` | No | ISO 8601 expiry datetime. Omit or `null` for no expiry |
| `current_password` | Conditionally | Required for accounts with a local password. Omit for SSO-only accounts |
| `mfa_code` | Conditionally | Required when MFA is enabled on the account |

**Create API Key Response (HTTP 201):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 1,
  "name": "Home Server Integration",
  "key_prefix": "abc12345",
  "scopes": "[\"activities:upload\"]",
  "expires_at": "2027-01-01T00:00:00Z",
  "last_used_at": null,
  "created_at": "2026-03-02T10:00:00Z",
  "is_active": true,
  "key": "endurain_abc12345..."
}
```

!!! warning "Save the key immediately"
    The `key` field is returned **only in this response**. It is not stored by the server and cannot be retrieved later. Store it in a secure location (e.g., a password manager or secrets vault) before dismissing the response.

**List API Keys Response (`GET /profile/api_keys`):**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": 1,
    "name": "Home Server Integration",
    "key_prefix": "abc12345",
    "scopes": "[\"activities:upload\"]",
    "expires_at": "2027-01-01T00:00:00Z",
    "last_used_at": "2026-03-01T08:30:00Z",
    "created_at": "2026-03-02T10:00:00Z",
    "is_active": true
  }
]
```

The `key` field is **never** returned in list or subsequent get responses — only `key_prefix` is shown for identification.

**Revoke API Key (`PATCH /profile/api_keys/{id}/revoke`):**

Revocation soft-deletes the key by setting `is_active = false`. Revoked keys are rejected immediately but remain visible in the list (useful for audit purposes). Returns HTTP 204 on success.

**Delete API Key (`DELETE /profile/api_keys/{id}`):**

Permanently removes the key from the database. Returns HTTP 204 on success.

## Security Properties

| Property | Detail |
| -------- | ------ |
| **Storage** | SHA-256 hex digest stored server-side; raw key never persisted |
| **Comparison** | Constant-time (`hmac.compare_digest`) prevents timing attacks |
| **Revocation** | Immediate — revoked keys are rejected at validation time |
| **Expiry** | Optional; expired keys are rejected at validation time with timezone-aware comparison |
| **Audit logging** | Every successful authentication is logged with key prefix, user ID, endpoint, and client IP |
| **No self-escalation** | An API key cannot create, list, or revoke other API keys (JWT required) |
| **Minimum privilege** | Keys carry only the scopes explicitly granted at creation time |

