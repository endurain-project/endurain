# API key authentication

API keys provide a stateless authentication mechanism for programmatic access and third-party integrations. Unlike JWT sessions, API keys do not require a login flow or token refresh, and are scoped to the account's own data.

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

API keys are granted one or more scopes at creation time, from the list below: the account's own data. A key never holds `account:security`, `account:export`, `account:integrations` or an administrator scope, even when its owner is an administrator. So a key never reaches the password, email, MFA, session, API key or identity provider routes, cannot export or import the account or link a Garmin Connect or Strava account, and administers nothing.

A key holds no more than its owner's role grants at the time of the request, as an access token does, so a scope the role no longer has stops working at once.

The key-management API refuses any other scope with `422`.

<!-- generated:api-key-scopes -->

## How to Authenticate with an API Key

API keys bypass the standard JWT requirements. Send the raw key using either option:

**Option 1: `X-API-Key` header (recommended):**

```http
POST /api/v1/activities/upload
X-API-Key: endurain_abc12345...
Content-Type: multipart/form-data

(file body)
```

**Option 2: `api_key` query parameter (for tools that cannot set custom headers):**

```http
POST /api/v1/activities/upload?api_key=endurain_abc12345...
Content-Type: multipart/form-data

(file body)
```

!!! warning "Query parameter delivery is disabled by default"
    The `?api_key=` query parameter is **disabled by default**. To enable it, set `ALLOW_API_KEY_QUERY_PARAM=true` in your environment. This option exists for self-hosted deployments where an integration cannot set custom request headers (e.g. certain webhook senders). When enabled, every request using this method emits a warning in the application log.

    Query-string credentials appear in server access logs, reverse-proxy logs, and browser history. Use the `X-API-Key` header whenever possible.

If both the `X-API-Key` header and the `?api_key=` query parameter are present, the **header takes precedence**.

## Endpoints That Accept API Keys

Every authenticated endpoint accepts an API key in place of a bearer token, and a key reaches the ones whose scopes it holds. Each operation in the [API reference](api-reference.md) names its scopes under both its `HTTPBearer` and `ApiKey` requirements. A missing scope is `403` with `WWW-Authenticate: Bearer error="insufficient_scope"`, as for a token. A request that sends both a bearer token and a key is authenticated by the token.

A key needs no `X-Client-Type` and no `X-CSRF-Token`. A write to a versioned resource still sends `If-Match`, and an upload may carry an `Idempotency-Key` header so a retry does not import the file twice, and so may the [bulk import](background-operations.md#bulk-import).

A few endpoints act for a signed-in session and refuse a key with `403` whatever its scopes. Nearly all of them already need a scope a key never holds. The one a key's scopes would reach is the WebSocket ticket (`POST /ws/ticket`), which is bound to the session that asked for it, so a key cannot open the [realtime](realtime.md) connection.

Rate limits count key requests per client address, not per user as for bearer tokens, so keys used from one address share a limit.

## Managing API Keys

API keys are managed through the Endurain web UI (Settings → Security → API Keys) or via the REST API. All management endpoints require a valid JWT access token.

Every API key expires. The maximum lifetime is set by an administrator (**Settings → Server settings → Sessions**, 365 days by default, 1 to 3650), and `expires_at` is always present in the responses. Keys that never expired before the upgrade now expire 365 days after it.

Creating an API key also requires step-up verification because the key is a long-lived credential:

The credentials travel in the `step_up` object of the request body:

- Local-password accounts must provide `step_up.current_password`
- Accounts with MFA enabled must also provide `step_up.mfa_code`
- Accounts without a local password must provide `step_up.idp_reauth`, proof of a fresh identity provider sign-in; see [step-up for accounts without a password](account-security.md#step-up-for-accounts-without-a-password)

**Create API Key Request:**

```http
POST /api/v1/profile/api-keys
Authorization: Bearer {access_token}
X-Client-Type: web
X-CSRF-Token: {csrf_token}
Content-Type: application/json

{
  "name": "Home Server Integration",
  "scopes": ["activities:upload"],
  "expires_at": "2027-01-01T00:00:00Z",
  "step_up": {
    "current_password": "current-password",
    "mfa_code": "123456"
  }
}
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | Yes | Human-readable label (max 100 characters) |
| `scopes` | Yes | Array of API-key scopes to grant. Currently only `activities:upload` is accepted |
| `expires_at` | No | ISO 8601 expiry datetime. Omit or `null` for the longest lifetime the server allows (365 days unless an administrator changed it). A later date is refused with `422` and a field error on `expires_at` |
| `step_up` | Yes | The step-up verification object |
| `step_up.current_password` | Conditionally | Required for accounts with a local password |
| `step_up.idp_reauth` | Conditionally | Required for accounts without a local password. Without it the API answers `401` with `urn:endurain:error:idp-reauth-required` |
| `step_up.mfa_code` | Conditionally | Required when MFA is enabled on the account |

**Create API Key Response (HTTP 201):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "2f1c6a3e-8d4b-4c57-9a1e-6b0d3f5e7a12",
  "name": "Home Server Integration",
  "key_prefix": "abc12345",
  "scopes": ["activities:upload"],
  "expires_at": "2027-01-01T00:00:00Z",
  "last_used_at": null,
  "created_at": "2026-03-02T10:00:00Z",
  "is_active": true,
  "key": "endurain_abc12345..."
}
```

!!! warning "Save the key immediately"
    The `key` field is returned **only in this response**. It is not stored by the server and cannot be retrieved later. Store it in a secure location (e.g., a password manager or secrets vault) before dismissing the response. The response is sent with `Cache-Control: no-store`.

**List API Keys Response (`GET /profile/api-keys?page_number=1&num_records=25`):**

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "2f1c6a3e-8d4b-4c57-9a1e-6b0d3f5e7a12",
      "name": "Home Server Integration",
      "key_prefix": "abc12345",
      "scopes": ["activities:upload"],
      "expires_at": "2027-01-01T00:00:00Z",
      "last_used_at": "2026-03-01T08:30:00Z",
      "created_at": "2026-03-02T10:00:00Z",
      "is_active": true
    }
  ],
  "total": 1,
  "page": 1,
  "num_records": 25,
  "next": null
}
```

The `key` field is **never** returned in list or subsequent get responses — only `key_prefix` is shown for identification.

**Revoke API Key (`POST /profile/api-keys/{id}/revoke`):**

Revocation soft-deletes the key by setting `is_active = false`. Revoked keys are rejected immediately but remain visible in the list for a while. Returns HTTP 204 on success.

**Limit and retention:**

An account holds at most 25 active API keys; a key is active while it is not revoked and has not expired. `POST /profile/api-keys` answers `409` with `urn:endurain:error:api-key-limit` at the limit: revoke or delete a key first. Endurain deletes a key 30 days after it was revoked or expired, so it then leaves the list.

**Delete API Key (`DELETE /profile/api-keys/{id}`):**

Permanently removes the key from the database. Returns HTTP 204 on success.

## Security Properties

| Property | Detail |
| -------- | ------ |
| **Storage** | SHA-256 hex digest stored server-side; raw key never persisted |
| **Lookup** | The server hashes the presented key with SHA-256 and finds the row by an indexed equality match on the digest. The 256-bit random key cannot be guessed from timing differences in that lookup |
| **Revocation** | Immediate — revoked keys are rejected at validation time, and deleted after 30 days |
| **Expiry** | Every key expires, at most the server's maximum API key lifetime (365 days by default) after creation; expired keys are rejected at validation time with timezone-aware comparison |
| **Audit and usage tracking** | A successful authentication stamps `last_used_at` on the key, at most once every 5 minutes, and writes a debug log line with key prefix, user ID, endpoint and client IP; it is not an audit row. Every refusal (unknown, revoked or expired key, inactive owner) is audited as `auth.api_key.authenticate` without the key, its prefix or its hash |
| **No self-escalation** | An API key never holds `account:security`, so it cannot create, list, or revoke API keys (JWT required) |
| **Minimum privilege** | Keys carry only the scopes explicitly granted at creation time |

