# Handling authentication

Endurain supports integration with other apps through a comprehensive OAuth 2.1 compliant authentication system that includes standard username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration, and JWT-based session management with refresh token rotation.

## API Requirements

- **Client Type Header:** Most protected JWT requests must include an `X-Client-Type` header with either `web` or `mobile` as the value. Authentication, public, browser-redirect, API-key, and activity-upload unified-auth flows follow the endpoint-specific requirements below.
- **OAuth/PKCE Client Type Binding:** For `/public/idp/login/{idp_slug}` and password PKCE login, the backend records a `client_type` on the PKCE/OAuth state. During `/public/idp/session/{session_id}/tokens`, that stored value controls the response shape. The token-exchange `X-Client-Type` header is optional, but if provided it must match the stored value; otherwise the exchange returns `400` with `client_type does not match the OAuth state`.
- **Authorization:** Most protected JWT requests must include an `Authorization: Bearer <access token>` header with a valid access token. Login, MFA verification, OAuth initiation/callback/token exchange, password reset, sign-up, and activity uploads authenticated with an API key are exceptions.
- **CSRF Protection (Web Only):** State-changing protected web requests (`POST`, `PUT`, `DELETE`, `PATCH`) must include an `X-CSRF-Token` header. This custom header requirement prevents simple cross-site form submissions and is combined with short-lived in-memory access tokens, `SameSite=Strict` refresh cookies, and CORS controls. `/auth/refresh` supports a bootstrap refresh without this header after page reload; if the header is provided and the session has a stored CSRF binding, the token value must be valid.

!!! note "API Key Authentication"
    Certain endpoints support API key authentication as an alternative to Bearer + `X-Client-Type` headers. API key requests do not require the `X-Client-Type` header or a CSRF token. See [API Key Authentication](#api-key-authentication) for details.

## Token Handling

### Token Lifecycle

- The backend generates an `access_token` valid for 15 minutes (default) and a `refresh_token` valid for 7 days (default).
- The `access_token` is used for authorization; the `refresh_token` is used to obtain new access tokens.
- A `csrf_token` is generated for CSRF protection on state-changing requests.
- Token expiration times can be customized via environment variables (see Configuration section below).

### OAuth 2.1 Token Storage Model (Hybrid Approach)

Endurain implements an OAuth 2.1 compliant hybrid token storage model that provides both security and usability:

| Token | Storage Location | Lifetime | Security Purpose |
|-------|------------------|----------|------------------|
| **Access Token** | In-memory (JavaScript) | 15 minutes | Short-lived, XSS-resistant (not persisted) |
| **Refresh Token** | httpOnly cookie | 7 days | CSRF-protected, auto-sent by browser |
| **CSRF Token** | In-memory (JavaScript) | Session | Prevents CSRF attacks on state-changing requests |

**Security Properties:**

- **XSS Protection:** Access tokens stored in memory cannot be exfiltrated via XSS attacks
- **CSRF Protection:** Refresh token in an httpOnly `SameSite=Strict` cookie plus the web-only CSRF header requirement prevents simple cross-site state changes. `/auth/refresh` also validates the CSRF token value when the client sends it and the session has a stored CSRF binding.
- **Session Persistence:** Page reload triggers `/auth/refresh` with httpOnly cookie to restore tokens
- **Multi-tab Support:** httpOnly cookie shared across browser tabs

### Token Delivery by Client Type

- **For web apps:** 
    - Access token and CSRF token returned in JSON response body (stored in-memory)
    - Refresh token set as httpOnly cookie (`endurain_refresh_token`)
    - On page reload, call `/auth/refresh` to restore in-memory tokens

- **For mobile apps:** 
  - Password login without PKCE returns access and refresh tokens in the JSON response body
  - Password login with PKCE and OAuth/SSO return a `session_id` first; the app exchanges that session with its PKCE verifier to receive access and refresh tokens
    - Store tokens in secure platform storage (iOS Keychain, Android EncryptedSharedPreferences)

## Authentication Flows

### Standard Login Flow (Username/Password)

1. Client sends credentials to `/auth/login` endpoint
2. Backend validates credentials and checks for account lockout
3. If MFA is enabled, backend returns MFA-required response
4. If MFA is disabled or verified, backend generates tokens
5. Tokens are delivered based on client type:
    - **Web:** Access token + CSRF token in response body, refresh token as httpOnly cookie
    - **Mobile:** All tokens in response body (CSRF not included, not needed for mobile logic)
    - **Mobile with PKCE:** Session ID for secure token exchange (see [Mobile Password Login with PKCE](#mobile-password-login-with-pkce) below)

### OAuth/SSO Flow

1. Client requests list of enabled providers from `/public/idp`
2. Client initiates OAuth at `/public/idp/login/{idp_slug}` with a PKCE challenge. Mobile clients should include `X-Client-Type: mobile`; if the header is absent or invalid, the backend records the flow as `web`.
3. User authenticates with the OAuth provider
4. Provider redirects back to `/public/idp/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links the user account, creates a session, and redirects the client with a `session_id`
7. The client exchanges the session for tokens via the PKCE token exchange endpoint `/public/idp/session/{session_id}/tokens`. The exchange response follows the stored client type; an `X-Client-Type` header may be sent for clarity, but conflicting values are rejected:
  - **Web clients:** Access token + CSRF token in response body, refresh token as httpOnly cookie
  - **Mobile clients:** Access token + refresh token in response body

### Token Refresh Flow

The token refresh flow implements OAuth 2.1 compliant refresh token rotation:

1. When access token expires, client calls `POST /auth/refresh`:
    - **Web clients:** Include `X-CSRF-Token` header with the current CSRF token, except bootstrap refresh after page reload may omit it
    - **Mobile clients:** Include refresh token in request
2. Backend validates refresh token and session, checks for token reuse
    - **If token reuse detected:** Entire token family is invalidated (security breach response)
3. New tokens are generated (access, refresh, CSRF) with refresh token rotation
4. Old refresh token is stored for reuse detection (grace period: 60 seconds)
5. Response includes new tokens; web clients receive new httpOnly cookie

**Token Refresh Request (Web):**

```http
POST /api/v1/auth/refresh
X-Client-Type: web
X-CSRF-Token: {current_csrf_token}
Cookie: endurain_refresh_token={refresh_token}
```

**Token Refresh Response (Web):**

```json
{
  "session_id": "uuid",
  "access_token": "eyJ...",
  "csrf_token": "new_csrf_token",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

**Token Refresh Response (Mobile):**

```json
{
  "session_id": "uuid",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

### Refresh Token Rotation & Reuse Detection

Endurain implements automatic refresh token rotation with reuse detection to prevent token theft:

| Security Feature | Description |
|------------------|-------------|
| **Automatic Rotation** | New refresh token issued on every `/auth/refresh` call |
| **Token Family Tracking** | All tokens in a session share a `token_family_id` |
| **Reuse Detection** | Old tokens are stored and monitored for reuse |
| **Grace Period** | 60-second window allows for network retry scenarios |
| **Family Invalidation** | If reuse detected, ALL tokens in family are invalidated |
| **Rotation Count** | Tracks number of rotations for audit purposes |

### API Key Authentication Flow

For integrations that do not maintain a JWT session, API keys provide a stateless alternative:

1. Generate an API key via the web UI (Settings → Security → API Keys) or the management API (requires JWT)
2. Store the raw key securely — it is shown only once at creation time
3. Include the key in requests to supported endpoints via the `X-API-Key` header, or via the `?api_key=` query parameter only when `ALLOW_API_KEY_QUERY_PARAM=true` is explicitly enabled
4. The backend validates the key hash, checks revocation and expiry, and resolves the user identity and scopes
5. The endpoint processes the request if the required scope is present in the key's grant

See [API Key Authentication](#api-key-authentication) for the complete reference.

## API Endpoints 

The API is reachable under `/api/v1`. Below are the authentication-related endpoints. Complete API documentation is available on the backend docs (`http://localhost:98/api/v1/docs` or `http://ip_address:98/api/v1/docs` or `https://domain/api/v1/docs`). You will need to change the ENV variable `ENVIRONMENT` to `development` in order for `/docs` endpoint to be served:

### Core Authentication Endpoints (Web)

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` | Header: `X-Client-Type: web`; `FORM` with fields: `username`, `password`. HTTPS highly recommended | 10 requests/min |
| **Refresh Token** | `/auth/refresh` | Header: `X-Client-Type: web`; Cookie: `endurain_refresh_token`; optional Header: `X-CSRF-Token` (bootstrap logic) | 30 requests/min |
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: web`; JSON `{'username': <username>, 'mfa_code': '123456'}` | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: web`; Cookie: `endurain_refresh_token` | 30 requests/min |

### Core Authentication Endpoints (Mobile)

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` | Header: `X-Client-Type: mobile`; `FORM` with fields: `username`, `password`. Optional query params: `code_challenge`, `code_challenge_method` (mobile PKCE). HTTPS highly recommended | 10 requests/min |
| **Refresh Token** | `/auth/refresh` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: mobile`; JSON body: `{'username': <username>, 'mfa_code': '123456'}`. Optional query params: `code_challenge`, `code_challenge_method` (mobile PKCE) | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/public/idp` | None (public endpoint) | - |
| **Initiate OAuth Login** | `/public/idp/login/{idp_slug}` | Header: `X-Client-Type` (`web` or `mobile`). For mobile OAuth/PKCE this must be `mobile`; query params: `redirect`, `code_challenge`, `code_challenge_method` | 10 requests/min per IP |
| **OAuth Callback** | `/public/idp/callback/{idp_slug}` | Query params: `code=<code>`, `state=<state>` | 10 requests/min per IP |
| **Token Exchange (PKCE)** | `/public/idp/session/{session_id}/tokens` | JSON: `{"code_verifier": "<verifier>"}` (password PKCE or SSO PKCE). Optional Header: `X-Client-Type`; if present, it must match the client type stored on the PKCE/OAuth state. | 10 requests/min |
| **Create IdP Link Token** | `/profile/idp/{idp_id}/link/token` | Requires authenticated session and step-up JSON body: `current_password` for local-password accounts; `mfa_code` when MFA is enabled. Returns a 60-second one-time link token | 10 requests/min |
| **Link IdP to Account** | `/profile/idp/{idp_id}/link?link_token=<token>` | Browser redirect endpoint using the one-time link token | - |

### Session Management Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Get User Sessions** | `/sessions/user/{user_id}` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:read` scope |
| **Delete Session** | `/sessions/{session_id}/user/{user_id}` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:write` scope; web clients must also include `X-CSRF-Token` |

### API Key Management Endpoints

Require JWT authentication with the standard `X-Client-Type` requirement; state-changing web requests must include `X-CSRF-Token`. API keys cannot manage other API keys.

| Method | Url | Description |
| ------ | --- | ----------- |
| `GET` | `/profile/api_keys` | List all API keys for the authenticated user |
| `POST` | `/profile/api_keys` | Create a new API key |
| `PATCH` | `/profile/api_keys/{id}/revoke` | Revoke (deactivate) a key |
| `DELETE` | `/profile/api_keys/{id}` | Permanently delete a key |

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `/activities/create/upload` | .gpx, .tcx, .gz or .fit file. Accepts JWT **or** API key (`X-API-Key` header, or `?api_key=` query param only when `ALLOW_API_KEY_QUERY_PARAM=true`) with `activities:upload` scope. This unified-auth endpoint does not require `X-Client-Type` |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

## Step-up Authentication

Certain sensitive account operations require the user to re-prove possession of their credentials even when they already hold a valid access token. This is called **step-up verification**.

### Operations That Require Step-up

| Operation | Endpoint |
| --------- | -------- |
| Change own password | `PATCH /users/{user_id}/password` |
| Enable MFA | `POST /profile/mfa/enable` |
| Disable MFA | `DELETE /profile/mfa/disable` |
| Regenerate MFA backup codes | `POST /profile/mfa/backup-codes` |
| Create API key | `POST /profile/api_keys` |
| Generate IdP link token | `POST /profile/idp/{idp_id}/link/token` |
| Remove IdP link | `DELETE /profile/idp/{idp_id}/link` |

### Step-up Request Body

All step-up operations accept the following fields in their JSON request body (alongside any operation-specific fields):

| Field | Required | Description |
| ----- | -------- | ----------- |
| `current_password` | Conditionally | Required for accounts with a local password. Omit for SSO-only accounts (no local credential exists) |
| `mfa_code` | Conditionally | Required when MFA is enabled on the account. Accepts TOTP codes or backup codes |

**Example:**

```json
{
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

SSO-only accounts (no local password) may omit `current_password`. The password factor is skipped because there is nothing to verify against. If MFA is enabled, the `mfa_code` is still required regardless of account type.

### Step-up Lockout Policy

Failed step-up verifications are tracked per-user with progressive lockout, independent of login lockout counters:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 15 failures | 2 hours |

The lockout check happens **before** any password or MFA comparison, so the number of guesses is bounded even when an attacker has a valid access token.

**Lockout Response (HTTP 429):**

```json
{
  "detail": "Too many failed step-up attempts. Try again later."
}
```

The response also includes a `Retry-After` header indicating how many seconds remain before the lockout expires.

The counter resets automatically on a successful step-up verification.

## Progressive Account Lockout

Endurain implements progressive brute-force protection to prevent credential stuffing attacks. Password login failures use this policy:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 20 failures | 24 hours |

MFA verification failures use a separate policy:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 15 failures | 2 hours |

**Features:**

- Per-username tracking prevents targeted attacks
- Lockout persists through MFA flow (prevents bypass)
- Counter resets on successful authentication
- Graceful error messages with remaining lockout time

## MFA Authentication Flow

When Multi-Factor Authentication (MFA) is enabled for a user, the authentication process requires two steps:

### Step 1: Initial Login Request
Make a standard login request to `/auth/login`:

**Request:**
```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded
X-Client-Type: web|mobile

username=user@example.com&password=userpassword
```

**Response (when MFA is enabled):**

- **Web clients**: HTTP 202 Accepted

```json
{
  "mfa_required": true,
  "username": "example",
  "message": "MFA verification required"
}
```

- **Mobile clients**: HTTP 200 OK

```json
{
  "mfa_required": true,
  "username": "example",
  "message": "MFA verification required"
}
```

### Step 2: MFA Verification
Complete the login by providing the MFA code (TOTP or backup code) to `/auth/mfa/verify`:

**Request:**
```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
X-Client-Type: web|mobile

{
  "username": "user@example.com",
  "mfa_code": "123456"
}
```

!!! tip "Backup Code Format"
    Users can also use a backup code instead of a TOTP code. Backup codes are in `XXXX-XXXX` format (e.g., `A3K9-7BDF`). See [MFA Backup Codes](#mfa-backup-codes) for details.

**Response (successful verification):**

- **Web clients**: Access token and CSRF token in response body, refresh token as httpOnly cookie

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "csrf_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

- **Mobile clients**: All tokens returned in response body

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

### Error Handling
- **No pending MFA login**: HTTP 400 Bad Request

```json
{
  "detail": "No pending MFA login found for this username"
}
```

- **Invalid MFA code**: HTTP 400 Bad Request

```json
{
  "detail": "Invalid MFA code, backup code or backup code already used."
}
```

- **Account locked out (too many failures)**: HTTP 429 Too Many Requests

```json
{
  "detail": "Too many failed MFA attempts. Account locked for 300 seconds."
}
```

### Important Notes
- The pending MFA login session is temporary and expires after 5 minutes
- After successful MFA verification, the pending login is automatically cleaned up
- The user must still be active at the time of MFA verification
- If no MFA is enabled for the user, the standard single-step authentication flow applies

## MFA Backup Codes

Backup codes provide a recovery mechanism when users lose access to their authenticator app. When MFA is enabled, users receive 10 one-time backup codes that can be used instead of TOTP codes.

### Backup Code Format

- Format: `XXXX-XXXX` (8 alphanumeric characters with hyphen)
- Example: `A3K9-7BDF`
- Characters: Uppercase letters and digits (excluding ambiguous: 0, O, 1, I)
- One-time use: Each code can only be used once

### When Backup Codes Are Generated

1. **Automatically on MFA Enable**: When a user enables MFA, 10 backup codes are generated and returned in the response
2. **Manual Regeneration**: Users can regenerate all backup codes via `POST /profile/mfa/backup-codes` (invalidates all previous codes). This endpoint requires step-up verification and MFA must already be enabled on the account.

### API Endpoints

| What | URL | Method | Description |
| ---- | --- | ------ | ----------- |
| **Get Backup Code Status** | `/profile/mfa/backup-codes/status` | GET | Returns count of unused/used codes |
| **Regenerate Backup Codes** | `/profile/mfa/backup-codes` | POST | Generates new codes (invalidates old). Requires step-up JSON body: `current_password` for local-password accounts and `mfa_code` when MFA is enabled |

### Regenerate Backup Codes Request

```http
POST /api/v1/profile/mfa/backup-codes
Authorization: Bearer {access_token}
X-Client-Type: web
X-CSRF-Token: {csrf_token}
Content-Type: application/json

{
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

For SSO-only accounts, `current_password` may be omitted because there is no local password to verify. If MFA is enabled, `mfa_code` is required.

### Backup Code Status Response

```json
{
  "has_codes": true,
  "total": 10,
  "unused": 8,
  "used": 2,
  "created_at": "2025-12-21T10:30:00Z"
}
```

### Regenerate Backup Codes Response

```json
{
  "codes": [
    "A3K9-7BDF",
    "X2M5-9NPQ",
    "..."
  ],
  "created_at": "2025-12-21T10:30:00Z"
}
```

### Using Backup Codes for Login

Backup codes can be used in the MFA verification step instead of TOTP codes:

```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
X-Client-Type: web|mobile

{
  "username": "user@example.com",
  "mfa_code": "A3K9-7BDF"
}
```

!!! warning "Important"
    - Backup codes are shown only once when generated - users must save them securely
    - Each backup code can only be used once
    - Regenerating codes invalidates ALL previous backup codes
    - Store backup codes in a secure location separate from your authenticator device

## API Key Authentication

API keys provide a stateless, long-lived authentication mechanism for programmatic access and third-party integrations. Unlike JWT sessions, API keys do not require a login flow or token refresh, and are scoped to specific operations.

!!! warning "Security Notice"
    API keys are powerful credentials. Treat them like passwords: store them securely and never expose them in client-side code, public repositories, or logs.

### Key Format

API keys use the following format:

```
endurain_<43-character-base64url-random-string>
```

- **Prefix**: `endurain_` — identifies Endurain API keys in secret scanning tools (e.g., GitHub secret scanning)
- **Random part**: 256 bits of cryptographically secure random data (`secrets.token_urlsafe(32)`), encoded as a 43-character base64url string
- **Total length**: ~52 characters

The raw key is shown **once** at creation time and is never stored by the server (only the SHA-256 hash is stored). If lost, the key must be deleted and a new one created.

### Scopes

API keys are granted one or more API-key scopes at creation time. Currently only `activities:upload` is accepted; JWT-only scopes such as `profile`, `activities:read`, or `users:write` cannot be granted to API keys.

The key-management API rejects any requested scope outside the API-key allow-list. This keeps long-lived API keys limited to the endpoint that currently supports API-key authentication.

| Scope | Description |
| ----- | ----------- |
| `activities:upload` | Upload activity files (.gpx, .tcx, .fit, .gz) |

### How to Authenticate with an API Key

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

### Endpoints That Accept API Keys

| Method | Endpoint | Required Scope | Description |
| ------ | -------- | -------------- | ----------- |
| `POST` | `/activities/create/upload` | `activities:upload` | Upload a .gpx, .tcx, .fit, or .gz activity file |

The upload endpoint also accepts JWT authentication through the same unified-auth dependency. JWT upload requests still require `Authorization: Bearer <access token>` and the `activities:upload` scope, but this endpoint does not require `X-Client-Type`.

### Managing API Keys

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

### Security Properties

| Property | Detail |
| -------- | ------ |
| **Storage** | SHA-256 hex digest stored server-side; raw key never persisted |
| **Comparison** | Constant-time (`hmac.compare_digest`) prevents timing attacks |
| **Revocation** | Immediate — revoked keys are rejected at validation time |
| **Expiry** | Optional; expired keys are rejected at validation time with timezone-aware comparison |
| **Audit logging** | Every successful authentication is logged with key prefix, user ID, endpoint, and client IP |
| **No self-escalation** | An API key cannot create, list, or revoke other API keys (JWT required) |
| **Minimum privilege** | Keys carry only the scopes explicitly granted at creation time |

## OAuth/SSO Integration

### Supported Identity Providers
Endurain supports OAuth/SSO integration with various identity providers out of the box:

- Authelia
- Authentik
- Casdoor
- Keycloak
- Pocket ID

The system is extensible and can be configured to work with:

- Google
- GitHub
- Microsoft Entra ID
- Others/custom OIDC providers

### OAuth Configuration
Identity providers must be configured with the following parameters:

- `client_id`: OAuth client identifier
- `client_secret`: OAuth client secret
- `authorization_endpoint`: Provider's authorization URL
- `token_endpoint`: Provider's token exchange URL
- `userinfo_endpoint`: Provider's user information URL
- `redirect_uri`: Callback URL (typically `/public/idp/callback/{idp_slug}`)

### Linking Accounts
Users can link their Endurain account to an OAuth provider:

1. User must be authenticated with a valid session
2. Create a one-time link token with `POST /profile/idp/{idp_id}/link/token`. Local-password accounts must include `current_password`; accounts with MFA enabled must also include `mfa_code`. SSO-only accounts may omit `current_password`.
3. Open `/profile/idp/{idp_id}/link?link_token=<token>` in the browser before the token expires (60 seconds)
4. Authenticate with the identity provider
5. Provider is linked to the existing account

### OAuth Token Response
When authenticating via OAuth, the response format matches the standard authentication:

- **Web clients**: Redirected to the frontend with a `session_id`; the frontend exchanges the session and receives the access token + CSRF token in the response body, while the refresh token is set as an httpOnly cookie
- **Mobile clients**: Redirected or deep-linked with a `session_id`; the app exchanges the session and receives access + refresh tokens in the response body

!!! info "Mobile OAuth/SSO"
  OAuth/SSO login requires PKCE for all clients. Mobile apps should still prefer the system browser flow because it keeps provider credentials outside the app process.

## Mobile Password Login with PKCE

### Overview

Mobile apps can use PKCE (Proof Key for Code Exchange, RFC 7636) for password authentication, providing enhanced security by preventing token interception in WebViews. This flow mirrors the OAuth/SSO PKCE flow but for local password authentication.

### Why Use PKCE for Password Login?

| Traditional Mobile Password Login | PKCE Password Login |
| --------------------------------- | ------------------- |
| Tokens returned in response | Tokens exchanged via secure API |
| Tokens visible in WebView context | Only session_id visible |
| Potential token interception | No token in response body |
| Simple but less secure | Secure, requires verifier |

### Step-by-Step PKCE Password Implementation

#### Step 1: Generate PKCE Code Verifier and Challenge

Before sending credentials, generate a cryptographically random code verifier and compute its SHA256 challenge (same as [Mobile SSO with PKCE](#step-1-generate-pkce-code-verifier-and-challenge)):

```
code_challenge = BASE64URL(SHA256(code_verifier))
```

#### Step 2: Send Login Request with PKCE Parameters

Include the code challenge in the login request:

**Login Request with PKCE:**

```http
POST /api/v1/auth/login?code_challenge={challenge}&code_challenge_method=S256
Content-Type: application/x-www-form-urlencoded
X-Client-Type: mobile

username=user@example.com&password=userpassword
```

**Form Parameters:**

| Parameter | Required | Description |
| --------- | -------- | ----------- |
| `username` | Yes | Username or email |
| `password` | Yes | User's password |

**Query Parameters:**

| Parameter | Required | Description |
| --------- | -------- | ----------- |
| `code_challenge` | Yes (PKCE) | Base64url-encoded SHA256 hash of code_verifier |
| `code_challenge_method` | Yes (PKCE) | Must be `S256` |

**Successful Response (HTTP 200):**

Instead of tokens, receive a session_id for token exchange:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "mfa_required": false,
  "message": "Complete authentication by exchanging tokens at /public/idp/session/{session_id}/tokens"
}
```

#### Step 3: Exchange Session for Tokens (PKCE Verification)

Use the code verifier to securely exchange the session for tokens:

**Token Exchange Request:**

```http
POST /api/v1/public/idp/session/{session_id}/tokens
Content-Type: application/json
X-Client-Type: mobile

{
  "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
}
```

**Successful Response (HTTP 200):**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 900,
  "refresh_token_expires_in": 604800,
  "token_type": "Bearer"
}
```

**Error Responses:**

| Status | Error | Description |
| ------ | ----- | ----------- |
| 400 | Invalid code_verifier | Verifier doesn't match the challenge |
| 400 | `client_type does not match the OAuth state` | `X-Client-Type` at token exchange differs from the value stored on the PKCE/OAuth state |
| 404 | Session not found | Invalid session_id |
| 409 | Tokens already exchanged | Replay attack prevention |
| 429 | Rate limit exceeded | Max 10 requests/minute per IP |

#### Step 4: Store Tokens Securely

Store the received tokens in secure platform storage:

- **iOS**: Keychain Services
- **Android**: EncryptedSharedPreferences or Android Keystore

#### Step 5: Use Tokens for API Requests

Use the tokens for authenticated API calls (same as [Mobile SSO with PKCE](#step-6-use-tokens-for-api-requests)).

### Backward Compatibility

Mobile clients that don't provide PKCE parameters will receive tokens directly (legacy behavior):

```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded
X-Client-Type: mobile

username=user@example.com&password=userpassword
```

Responds with tokens directly (no PKCE):

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

### With MFA Enabled

If the user has MFA enabled, the flow includes an additional MFA verification step:

1. Client sends login with PKCE parameters
2. Backend returns `"mfa_required": true` with message
3. Client collects MFA code from user
4. Client sends MFA code to `/auth/mfa/verify` with PKCE parameters
5. Backend verifies MFA and returns session_id (for PKCE) or tokens directly
6. Client exchanges session_id for tokens using code_verifier

**MFA Verification with PKCE:**

```http
POST /api/v1/auth/mfa/verify?code_challenge={challenge}&code_challenge_method=S256
Content-Type: application/json
X-Client-Type: mobile

{
  "username": "user@example.com",
  "mfa_code": "123456"
}
```

**Response (Session ID for Exchange):**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "mfa_required": false,
  "message": "Complete authentication by exchanging tokens at /public/idp/session/{session_id}/tokens"
}
```

Then exchange for tokens as in Step 3 above.

### Security Features

| Feature | Description |
| ------- | ----------- |
| **PKCE S256** | SHA256 challenge prevents code interception |
| **One-time exchange** | Tokens can only be exchanged once per session |
| **10-minute exchange window** | The PKCE/OAuth state expires after 10 minutes; the pending session cannot be exchanged after that window |
| **Rate limiting** | 10 token exchange requests per minute |
| **Session binding** | Session is cryptographically bound to PKCE challenge |

## Mobile SSO with PKCE

### Overview
PKCE (Proof Key for Code Exchange, RFC 7636) is required for OAuth/SSO authentication. It provides enhanced security by eliminating the need to extract tokens from WebView cookies, preventing authorization code interception attacks, and enabling a cleaner separation between browser/WebView and app contexts.

### Why Use PKCE?

| Traditional WebView Flow | PKCE Flow |
| ------------------------ | --------- |
| Extract tokens from cookies | Tokens delivered via secure API |
| Cookies may leak across contexts | No cookie extraction needed |
| Complex WebView cookie management | Simple token exchange |
| Potential timing issues | Atomic token exchange |

### PKCE Flow Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Mobile App │     │   Backend   │     │   WebView   │     │     IdP     │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       │ Generate verifier │                   │                   │
       │ & challenge       │                   │                   │
       │──────────────────>│                   │                   │
       │                   │                   │                   │
       │     Open WebView with challenge       │                   │
       │──────────────────────────────────────>│                   │
       │                   │                   │                   │
       │                   │      Redirect to IdP                  │
       │                   │──────────────────────────────────────>│
       │                   │                   │                   │
       │                   │                   │   User logs in    │
       │                   │                   │<─────────────────>│
       │                   │                   │                   │
       │                   │   Callback with code & state          │
       │                   │<──────────────────────────────────────│
       │                   │                   │                   │
       │     Redirect with session_id          │                   │
       │<──────────────────────────────────────│                   │
       │                   │                   │                   │
       │ POST token exchange with verifier     │                   │
       │──────────────────>│                   │                   │
       │                   │                   │                   │
       │   Return tokens   │                   │                   │
       │<──────────────────│                   │                   │
       │                   │                   │                   │
```

### Step-by-Step PKCE Implementation

#### Step 1: Generate PKCE Code Verifier and Challenge

Before initiating the OAuth flow, generate a cryptographically random code verifier and compute its SHA256 challenge:

**Code Verifier Requirements (RFC 7636):**

- Length: 43-128 characters
- Characters accepted by Endurain: `A-Z`, `a-z`, `0-9`, `-`, `_`
- Cryptographically random

**Code Challenge Computation:**

```
code_challenge = BASE64URL(SHA256(code_verifier))
```

#### Step 2: Initiate OAuth with PKCE Challenge

Initiate OAuth from an app-controlled HTTP request so the backend records `X-Client-Type: mobile`, then open the returned redirect target in WebView.

**Initiate Request:**

```http
GET /api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect=/dashboard
X-Client-Type: mobile
```

The response is a redirect to the IdP authorization URL. Load that redirect target in WebView.

**Direct Initiate URL (reference):**

```http
https://your-endurain-instance.com/api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect=/dashboard
```

**Query Parameters:**

| Parameter | Required | Description |
| --------- | -------- | ----------- |
| `code_challenge` | Yes (PKCE) | Base64url-encoded SHA256 hash of code_verifier |
| `code_challenge_method` | Yes (PKCE) | Must be `S256` |
| `redirect` | No | Frontend path after successful login |

#### Step 3: Monitor WebView for Callback

The OAuth flow proceeds as normal. Monitor the WebView URL for the success redirect:

**Success URL Pattern:**

```http
https://your-endurain-instance.com/login?sso=success&session_id={uuid}&redirect=/dashboard
```

Extract the `session_id` from the URL - this is needed for token exchange.

#### Step 4: Exchange Session for Tokens (PKCE Verification)

After obtaining the `session_id`, close the WebView and exchange it for tokens using the code verifier:

**Token Exchange Request:**

```http
POST /api/v1/public/idp/session/{session_id}/tokens
Content-Type: application/json
X-Client-Type: mobile

{
  "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
}
```

**Successful Response (HTTP 200):**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 900,
  "refresh_token_expires_in": 604800,
  "token_type": "Bearer"
}
```

**Error Responses:**

| Status | Error | Description |
| ------ | ----- | ----------- |
| 400 | Invalid code_verifier | Verifier doesn't match the challenge |
| 400 | `client_type does not match the OAuth state` | `X-Client-Type` at token exchange differs from the value stored on the PKCE/OAuth state |
| 404 | Session not found | Invalid session_id or not a PKCE flow |
| 409 | Tokens already exchanged | Replay attack prevention |
| 429 | Rate limit exceeded | Max 10 requests/minute per IP |

#### Step 5: Store Tokens Securely

Store the received tokens in secure platform storage:

- **iOS**: Keychain Services
- **Android**: EncryptedSharedPreferences or Android Keystore

#### Step 6: Use Tokens for API Requests

Use the tokens for authenticated API calls:

```http
GET /api/v1/activities
Authorization: Bearer {access_token}
X-Client-Type: mobile
```

### System Browser Alternative (RFC 8252 Recommended)

For maximum security, mobile apps should use the **system browser** instead of an
embedded WebView. This follows [RFC 8252 - OAuth 2.0 for Native Apps](https://tools.ietf.org/html/rfc8252).

#### Advantages over WebView

| WebView | System Browser |
| ------- | -------------- |
| Full page rendered in-app | OS-managed, isolated process |
| Cannot verify address bar URL | Address bar visible to user (phishing resistance) |
| Cookies shared with app | No app access to browser storage |
| App must extract session_id from URL | App receives session_id via deep-link |

#### System Browser Flow

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│  Mobile App │     │ Endurain Backend│     │System Browser│    │     IdP     │
└──────┬──────┘     └────────┬────────┘     └──────┬──────┘     └──────┬──────┘
       │                     │                     │                   │
       │ 1. Generate PKCE    │                     │                   │
       │    verifier+challenge                     │                   │
       │                     │                     │                   │
       │ 2. Open system browser to:                │                   │
       │    /public/idp/login/{slug}               │                   │
       │    ?code_challenge=X                      │                   │
       │    &redirect={custom_scheme}://callback   │                   │
       │────────────────────────────────────────────────────────────────────>
       │                     │                     │                   │
       │                     │ 3. Validate redirect │                  │
       │                     │    Store in DB       │                  │
       │                     │──────────────────────>                  │
       │                     │     Redirect to IdP                     │
       │                     │────────────────────────────────────────>│
       │                     │                     │                   │
       │                     │                     │  User logs in     │
       │                     │                     │<─────────────────>│
       │                     │  code + state       │                   │
       │                     │<────────────────────────────────────────│
       │                     │                     │                   │
       │                     │ 4. Redirect to frontend:                │
       │                     │    /login?sso=success&session_id=UUID   │
       │                     │    &redirect={custom_scheme}://callback │
       │                     │    &external_redirect=true              │
       │                     │────────────────────────────────────────>│
       │                     │                     │                   │
       │                     │  5. Frontend detects external_redirect  │
       │                     │     Forwards to custom scheme:          │
       │                     │     {custom_scheme}://callback          │
       │                     │     ?session_id=UUID                    │
       │ Deep-link received  │                     │                   │
       │<────────────────────────────────────────────                  │
       │                     │                     │                   │
       │ 6. POST token exchange with own verifier  │                   │
       │────────────────────>│                     │                   │
       │    JWT tokens       │                     │                   │
       │<────────────────────│                     │                   │
```

#### Step-by-Step: System Browser Flow

**Step 1:** Mobile app generates PKCE pair (same as WebView — see [Step 1](#step-1-generate-pkce-code-verifier-and-challenge)).

**Step 2:** First call the initiate endpoint with the custom scheme redirect target, then open the returned redirect target in the system browser.

```http
GET /api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect={custom_scheme}://callback
X-Client-Type: mobile
```

!!! note "Custom Scheme Auto-Detection"
    When using a custom URI scheme redirect (e.g., `gadgetbridge://callback`), the backend automatically detects this as a mobile flow and sets the client type to `mobile`. This means the `X-Client-Type: mobile` header is optional for custom scheme redirects. However, including it is still recommended for clarity and consistency.

    If your mobile platform cannot attach custom headers when directly opening a browser URL, you can still use the direct URL without the header and rely on the custom scheme for auto-detection:
    ```http
    https://your-endurain-instance.com/api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect={custom_scheme}://callback
    ```

**Direct Initiate URL (reference):**

```http
https://your-endurain-instance.com/api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect={custom_scheme}://callback
```

The `{custom_scheme}` (e.g., `endurain,gadgetbridge`) must be configured by the Endurain
administrator via `ALLOWED_REDIRECT_SCHEMES` (see [Configuration](#configuration)).

**Step 3:** User completes SSO. The system browser is redirected to:

```
{custom_scheme}://callback?session_id={uuid}
```

In the current web flow, the backend first redirects to the Endurain frontend with `external_redirect=true`; the frontend then forwards the `session_id` to the configured custom scheme.

**Step 4:** The OS invokes the app's deep-link/intent handler with the above URL.
Extract the `session_id`.

**Step 5:** Perform token exchange using the app's **own** `code_verifier`:

```http
POST /api/v1/public/idp/session/{session_id}/tokens
Content-Type: application/json
X-Client-Type: mobile

{
  "code_verifier": "<the verifier generated in step 1>"
}
```

**Step 6:** Store and use tokens (see [Step 5](#step-5-store-tokens-securely) and [Step 6](#step-6-use-tokens-for-api-requests)).

#### Redirect URL Validation Rules

| Redirect value | Allowed | Notes |
| -------------- | ------- | ----- |
| `/dashboard` | ✅ | Relative paths always allowed |
| `/settings?tab=devices` | ✅ | Query strings OK in relative paths |
| `gadgetbridge://callback` | ✅ | If `gadgetbridge` in `ALLOWED_REDIRECT_SCHEMES`; automatically detected as mobile client type |
| `myapp://callback` | ❌ | If `myapp` not configured — 400 returned |
| `https://evil.com` | ❌ | External HTTP URLs always rejected |
| `http://localhost` | ❌ | External HTTP URLs always rejected |
| `/../etc/passwd` | ❌ | Path traversal rejected |
| `//evil.com` | ❌ | Protocol-relative URLs rejected |

### Security Features

| Feature | Description |
| ------- | ----------- |
| **PKCE S256** | SHA256 challenge prevents code interception |
| **One-time exchange** | Tokens can only be exchanged once per session |
| **10-minute expiry** | OAuth state expires after 10 minutes |
| **Rate limiting** | 10 token exchange requests per minute |
| **Session linking** | Session is cryptographically bound to OAuth state |

## Configuration

### Environment Variables

The following environment variables control authentication behavior:

#### Token Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `SECRET_KEY` | Secret key for JWT signing (min 32 characters recommended) | - | Yes |
| `ALGORITHM` | JWT signing algorithm | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes | `15` | No |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime in days | `7` | No |

#### Session Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `SESSION_IDLE_TIMEOUT_ENABLED` | Enable session idle timeout | `false` | No |
| `SESSION_IDLE_TIMEOUT_HOURS` | Hours of inactivity before session expires | `1` | No |
| `SESSION_ABSOLUTE_TIMEOUT_HOURS` | Maximum session lifetime in hours | `24` | No |

#### Security Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `ENVIRONMENT` | Controls refresh cookie security for login, refresh, and OAuth/SSO token exchange. `production` and `demo` set the `Secure` flag on the refresh cookie and the OAuth/SSO session cookie, which requires Endurain to be served over HTTPS in those environments for login, session refresh, and SSO to work. | `production` | No |
| `ALLOWED_REDIRECT_SCHEMES` | Comma-separated custom URI schemes allowed as SSO redirect targets (e.g., `endurain,gadgetbridge`). Defaults to `endurain` when unset. If set, the provided list is used as-is (it does not merge with the default). External `http`/`https` redirects are always rejected. | `endurain` | No |
| `SSRF_ALLOWED_HOSTS` | SSRF allowlist for admin-configured outbound calls (currently OIDC discovery and JWKS fetch only). Comma-separated list of exact hostnames (case-insensitive) and/or explicit IP CIDR ranges. Supports self-hosted identity providers on private networks. Examples: `auth.internal.example.com` or `auth.internal.example.com,10.10.0.0/24,fd00::/64`. Wildcards are rejected. IPv4 prefix must be ≥ /8, IPv6 ≥ /32. Every allowlisted outbound call is logged at INFO level for audit. | `` | No |

#### Rate Limiting and Shared State

Rate-limit counters and all auth-security state (login/step-up lockout, pending
MFA login state, MFA setup secrets, Garmin MFA codes, websocket tickets) share
one backend selected by `DEPLOYMENT_PROFILE`.

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `RATE_LIMIT_ENABLED` | Enable or disable API rate limiting. Set to `false` to disable for development or testing. | `true` | No |
| `DEPLOYMENT_PROFILE` | Deployment shape selecting the backend for all shared state. `local` (default) uses in-process memory; `distributed` requires Redis. A `distributed` or multi-worker deployment wired to memory is rejected at startup. | `local` | No |
| `WEB_WORKERS` | Number of web-server worker processes. When `> 1`, shared state (Redis) is required even under the `local` profile. | `1` | No |
| `STATE_URI` | Explicit override for the shared ephemeral-state backend. Takes precedence over `REDIS_URL`. `memory://` or `redis://…`. | *(profile default)* | No |
| `REDIS_URL` | Shared Redis DSN backing every Redis capability with no explicit URI (including `STATE_URI`). Required for `distributed` or `WEB_WORKERS > 1`. | *(unset)* | No |
| `ALLOW_API_KEY_QUERY_PARAM` | Allow API keys via the `?api_key=` query parameter. Disabled by default because query-string credentials appear in server access logs, reverse-proxy logs, and browser history. Enable only for integrations that cannot set custom request headers. The `X-API-Key` header is always preferred. | `false` | No |

### Cookie Configuration

For web clients, the refresh token cookie is configured with:

| Attribute | Value | Purpose |
|-----------|-------|---------|
| **HttpOnly** | `true` | Prevents JavaScript access (XSS protection) |
| **Secure** | `true` when `ENVIRONMENT=production` or `demo`; applies consistently to login, refresh, and OAuth/SSO token exchange | Only sent over HTTPS |
| **SameSite** | `Strict` | Prevents CSRF attacks |
| **Path** | `/api/v1/auth` | Sent only to auth endpoints that need the refresh token |
| **Expires** | 7 days (default) | Matches refresh token lifetime |

## Security Scopes

Endurain uses OAuth-style scopes to control API access. Each scope controls access to specific resource groups:

### Available Scopes

| Scope | Description | Access Level |
| ----- | ----------- | ------------ |
| `profile` | User profile information | Read/Write |
| `users:read` | Read user data | Read-only |
| `users:write` | Modify user data | Write |
| `gears:read` | Read gear/equipment data | Read-only |
| `gears:write` | Modify gear/equipment data | Write |
| `activities:read` | Read activity data | Read-only |
| `activities:write` | Create/modify activities | Write |
| `activities:upload` | Upload activity files (.gpx, .tcx, .fit, .gz) | Write (JWT or API key on upload endpoint) |
| `health:read` | Read health metrics (weight, sleep, steps) | Read-only |
| `health:write` | Record health metrics | Write |
| `health_targets:read` | Read health targets | Read-only |
| `health_targets:write` | Modify health targets | Write |
| `notifications:read` | Read notifications | Read-only |
| `notifications:write` | Modify notifications | Write |
| `sessions:read` | View active sessions | Read-only |
| `sessions:write` | Manage sessions | Write |
| `server_settings:read` | View server configuration | Read-only |
| `server_settings:write` | Modify server settings | Write (Admin) |
| `identity_providers:read` | View OAuth providers | Read-only |
| `identity_providers:write` | Configure OAuth providers | Write (Admin) |

### Scope Usage
Scopes are automatically assigned based on user permissions and are embedded in JWT tokens. API endpoints validate required scopes before processing requests.

## Common Error Responses

### HTTP Status Codes

| Status Code | Description | Common Causes |
| ----------- | ----------- | ------------- |
| `400 Bad Request` | Invalid request format | Missing required fields, invalid JSON, no pending MFA login |
| `401 Unauthorized` | Authentication failed | Invalid credentials, expired token, invalid MFA code |
| `403 Forbidden` | Access denied | Invalid client type, insufficient permissions, missing required scope |
| `404 Not Found` | Resource not found | Invalid session ID, user not found, endpoint doesn't exist |
| `429 Too Many Requests` | Rate limit exceeded | Too many login attempts, OAuth requests exceeded limit |
| `500 Internal Server Error` | Server error | Database connection issues, configuration errors |

### Example Error Responses

**Invalid Client Type:**

```json
{
  "detail": "Invalid client type"
}
```

**Expired Token:**

```json
{
  "detail": "Token is expired."
}
```

**Invalid Credentials:**

```json
{
  "detail": "Unable to authenticate with provided credentials"
}
```

**Rate Limit Exceeded:**

```json
{
  "detail": "Too many requests. Please try again later."
}
```

**Missing Required Scope:**

```json
{
  "detail": "Unauthorized Access - Missing permissions: {'activities:write'}"
}
```

## Best Practices

### For Web Client Applications

1. **Store access and CSRF tokens in memory** - Never persist in localStorage or sessionStorage
2. **Implement automatic token refresh** - Refresh before access token expires (e.g., at 80% of lifetime)
3. **Handle concurrent refresh requests** - Use a refresh lock pattern to prevent race conditions
4. **Always include required headers:**
    - `Authorization: Bearer {access_token}` for all authenticated requests
    - `X-Client-Type: web` for all requests
    - `X-CSRF-Token: {csrf_token}` for protected POST/PUT/DELETE/PATCH requests, except `/auth/refresh` bootstrap. Protected web writes require the header; `/auth/refresh` also validates the token value when supplied and bound to the session
5. **Handle page reload gracefully** - Call `/auth/refresh` on app initialization to restore in-memory tokens
6. **Clear tokens on logout** - The httpOnly cookie is cleared by the backend

### For Mobile Client Applications

1. **Store tokens securely**:
    - **iOS**: Keychain Services
    - **Android**: EncryptedSharedPreferences or Android Keystore
2. **Use PKCE for OAuth/SSO** - Required for OAuth/SSO flows
3. **Include required headers:**
    - `Authorization: Bearer {access_token}` for all authenticated requests
    - `X-Client-Type: mobile` for all requests
4. **Handle token refresh proactively** - Refresh before expiration
5. **Implement secure token deletion** on logout

### For Security

1. **Never expose `SECRET_KEY`** in client code or version control
2. **Use strong, randomly generated secrets** (minimum 32 characters)
3. **Always use HTTPS** in production environments
4. **Enable MFA** for enhanced account security
5. **Monitor for token reuse** - Indicates potential token theft
6. **Enable session idle timeout** for sensitive applications
7. **Use appropriate scopes** - Request only necessary permissions

### For OAuth/SSO Integration

1. **Always use PKCE** - Required for OAuth/SSO login
2. **Validate state parameter** - Prevents CSRF attacks on OAuth flow
3. **Implement proper redirect URL validation** - Prevents open redirects
4. **Handle provider errors gracefully** with user-friendly messages
5. **Support account linking** - Allow users to connect multiple providers
6. **Respect token expiry** - OAuth state expires after 10 minutes

### For API Key Integrations

1. **Store the key securely** — use a secrets manager, environment variable, or encrypted config file. Never hardcode it in source code
2. **Use the `X-API-Key` header** rather than the `?api_key=` query parameter to avoid key exposure in logs. The query parameter is disabled by default and must be explicitly enabled with `ALLOW_API_KEY_QUERY_PARAM=true`
3. **Grant only supported scopes** — API keys currently accept only `activities:upload`
4. **Set an expiry date** when creating keys for temporary or one-off integrations
5. **Rotate keys periodically** — delete the old key and create a new one; update any dependent services before deleting
6. **Revoke immediately** if a key is suspected to be compromised — revocation takes effect instantly
7. **Monitor `last_used_at`** via the list endpoint to detect unused keys that can be cleaned up