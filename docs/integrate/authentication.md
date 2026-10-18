# Handling authentication

Endurain supports integration with other apps through a comprehensive OAuth 2.1 compliant authentication system that includes standard username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration, and JWT-based session management with refresh token rotation.

## API Requirements

- **Client Type Header:** Most protected JWT requests must include an `X-Client-Type` header with either `web` or `mobile` as the value. Authentication, public, browser-redirect, API-key, and activity-upload unified-auth flows follow the endpoint-specific requirements below.
- **OAuth/PKCE Client Type Binding:** For `/public/idp/login/{idp_slug}` and password PKCE login, the backend records a `client_type` on the PKCE/OAuth state. During `/public/idp/session/{session_id}/tokens`, that stored value controls the response shape. The token-exchange `X-Client-Type` header is optional, but if provided it must match the stored value; otherwise the exchange returns `400` with `client_type does not match the OAuth state`.
- **Authorization:** Most protected JWT requests must include an `Authorization: Bearer <access token>` header with a valid access token. Login, MFA verification, OAuth initiation/callback/token exchange, password reset, sign-up, and activity uploads authenticated with an API key are exceptions.
- **CSRF Protection (Web Only):** State-changing protected web requests (`POST`, `PUT`, `DELETE`, `PATCH`) must include an `X-CSRF-Token` header. This custom header requirement prevents simple cross-site form submissions and is combined with short-lived in-memory access tokens, `SameSite=Strict` refresh cookies, and CORS controls. `/auth/refresh` supports a bootstrap refresh without this header after page reload; if the header is provided and the session has a stored CSRF binding, the token value must be valid.

!!! note "API Key Authentication"
    Certain endpoints support API key authentication as an alternative to Bearer + `X-Client-Type` headers. API key requests do not require the `X-Client-Type` header or a CSRF token. See [API Key Authentication](api-keys.md) for details.

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
    - **Mobile with PKCE:** Session ID for secure token exchange (see [Mobile Password Login with PKCE](oauth-sso-pkce.md#mobile-password-login-with-pkce) below)

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

See [API Key Authentication](api-keys.md) for the complete reference.

## API Endpoints 

The API is reachable under `/api/v1`. Below are the authentication-related endpoints. The complete interactive API documentation (OpenAPI) is served at `/api/v1/docs` (Swagger UI) and `/api/v1/redoc`, for example `http://localhost:8080/api/v1/docs`. It is only available when the `ENVIRONMENT` variable is set to `development` or `demo`; in `production` it is disabled.

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

<!-- generated:api-key-endpoints -->

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `/activities/create/upload` | .gpx, .tcx, .gz or .fit file. Accepts JWT **or** API key (`X-API-Key` header, or `?api_key=` query param only when `ALLOW_API_KEY_QUERY_PARAM=true`) with `activities:upload` scope. This unified-auth endpoint does not require `X-Client-Type` |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

