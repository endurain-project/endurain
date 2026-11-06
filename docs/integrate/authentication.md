# Handling authentication

Endurain supports integration with other apps through an authentication system that includes username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration with PKCE (S256), and JWT-based session management with refresh token rotation and reuse detection. `/auth/login` is a username/password grant, which OAuth 2.1 does not include, so Endurain does not claim to be OAuth 2.1 compliant.

## API Requirements

- **Client Type Header:** `POST /auth/login`, `/auth/mfa/verify`, `/auth/refresh` and `/auth/logout` require an `X-Client-Type` header with `web` or `mobile`; a missing or unknown value is `422`. It is an ordinary header parameter in the OpenAPI document, not a security scheme. Protected routes authenticate first and do not read it: a call without a valid token is `401` with `WWW-Authenticate` whatever the header says. The other flows follow the endpoint-specific requirements below.
- **OAuth/PKCE Client Type Binding:** For `/public/idp/login/{idp_slug}` and password PKCE login, the backend records a `client_type` on the PKCE/OAuth state. During `/public/idp/session/{session_id}/tokens`, that stored value controls the response shape. The token-exchange `X-Client-Type` header is optional, but if provided it must match the stored value; otherwise the exchange returns `400` with `client_type does not match the OAuth state`.
- **Authorization:** Most protected JWT requests must include an `Authorization: Bearer <access token>` header with a valid access token. Login, MFA verification, OAuth initiation/callback/token exchange, password reset, sign-up, and activity uploads authenticated with an API key are exceptions.
- **CSRF Protection (Web Only):** State-changing protected web requests (`POST`, `PUT`, `DELETE`, `PATCH`) must include an `X-CSRF-Token` header. The server checks only that the header is present, and only for requests that send `X-Client-Type: web`, so it is a defence in depth rather than the CSRF defence. A custom header makes a cross-origin browser request preflighted, so CORS decides whether it is sent. The protection that matters is that protected routes read the access token from the `Authorization` header, which a browser never sends on its own, and that the refresh cookie is `SameSite=Strict` and limited to `/api/v1/auth`. `/auth/refresh` supports a bootstrap refresh without this header after page reload; if the header is provided and the session has a stored CSRF binding, the token value must be valid.

!!! note "API Key Authentication"
    Certain endpoints support API key authentication as an alternative to Bearer + `X-Client-Type` headers. API key requests do not require the `X-Client-Type` header or a CSRF token. See [API Key Authentication](api-keys.md) for details.

## Token Handling

### Token Lifecycle

- The backend generates an `access_token` valid for 15 minutes (default) and a `refresh_token` valid for 7 days (default).
- The `access_token` is used for authorization; the `refresh_token` is used to obtain new access tokens.
- A `csrf_token` is generated for CSRF protection on state-changing requests.
- Token and session lifetimes are set by an administrator in Settings > Server > Sessions (see [Configuration, scopes and best practices](auth-reference.md#configuration) for the deprecated environment variables).
- A session ends at the absolute session timeout whatever its activity: 720 hours (30 days) by default. An optional idle timeout (off by default, 1 hour when enabled) also ends a session after inactivity. Administrators change the access token, refresh token, idle and absolute settings in Settings > Server > Sessions. A client should read `refresh_token_expires_in` rather than assume a lifetime.

### Token storage model (hybrid approach)

Endurain splits web tokens between memory and an httpOnly cookie:

| Token | Storage Location | Lifetime | Security Purpose |
|-------|------------------|----------|------------------|
| **Access Token** | In-memory (JavaScript) | 15 minutes | Short-lived, never written to storage |
| **Refresh Token** | httpOnly cookie | 7 days | `SameSite=Strict`, sent only to `/api/v1/auth` |
| **CSRF Token** | In-memory (JavaScript) | Session | Sent as `X-CSRF-Token` on state-changing requests; its value is checked only by `/auth/refresh` |
| **Device id** | Web: httpOnly cookie (`endurain_device`, path `/api/v1`, `SameSite=Strict`). Mobile: the app's own storage, sent as the `X-Device-Id` header | 400 days from the last sign-in | Recognises the browser or app, so a sign-in from a new one sends a [security notice](../features/accounts-and-sign-in.md#security-notifications), and a known one is not held by the [account lock](account-security.md#progressive-account-lockout). Not a credential; the server stores only its SHA-256 hash |

**Security Properties:**

- **XSS exposure:** Keeping the access token in memory keeps it out of storage that a browser extension or a later page can read, and it expires in minutes. It does not stop script running in the page: that script can call `POST /auth/refresh`, which the browser answers with the httpOnly cookie, and read the fresh access token from the response. The refresh route does not require the `X-CSRF-Token` header (a bootstrap refresh after a page reload sends none), and the CSP allows inline scripts (next point).
- **CSRF Protection:** Protected routes authenticate with the `Authorization` header, which a browser never sends on its own, and the refresh token is an httpOnly `SameSite=Strict` cookie limited to `/api/v1/auth`. The `X-CSRF-Token` header is a presence check on top of that, and `/auth/refresh` also validates its value when the client sends it and the session has a stored CSRF binding.
- **Content Security Policy:** HTML responses carry a CSP whose `script-src` and `style-src` include `'unsafe-inline'`, so the policy does not stop an injected inline script. This is an accepted risk. The defences that remain are never rendering user data with `v-html`, keeping the access token out of persistent storage, and the `SameSite=Strict`, path-limited refresh cookie. The policy carries `frame-ancestors 'none'`, and every response carries `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-site`. A JSON response carries `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. Error responses carry these headers too. A reverse proxy that sets its own `Content-Security-Policy` or cross-origin policies replaces them, so let Endurain's headers through.
- **Self-declared client type:** `X-Client-Type` is chosen by the caller, so it selects the response shape and whether the CSRF header is required but proves nothing about who is calling. This is an accepted risk: a caller that omits `web` only skips a presence check that is not the CSRF defence, and it still needs a valid access token.
- **Session Persistence:** Page reload triggers `/auth/refresh` with httpOnly cookie to restore tokens
- **Multi-tab Support:** httpOnly cookie shared across browser tabs

### Token Delivery by Client Type

- **For web apps:** 
    - Access token and CSRF token returned in JSON response body (stored in-memory)
    - Refresh token set as httpOnly cookie (`endurain_refresh_token`)
    - Password login, MFA verification and the SSO token exchange also set the `endurain_device` cookie, which names the browser for new-device sign-in notices
    - On page reload, call `/auth/refresh` to restore in-memory tokens

- **For mobile apps:** 
  - Password login without PKCE returns access and refresh tokens in the JSON response body
  - Password login with PKCE and OAuth/SSO return a `session_id` first; the app exchanges that session with its PKCE verifier to receive access and refresh tokens
    - Store tokens in secure platform storage (iOS Keychain, Android EncryptedSharedPreferences)
  - **Device id:** send `X-Device-Id` on `/auth/login`, `/auth/mfa/verify` and the `/public/idp/session/{session_id}/tokens` exchange, with the value the server returned earlier (43 characters of `A-Z a-z 0-9 - _`; a missing or malformed value counts as none). A sign-in from an id the account has not used before sends the user a new-device notice, except the account's first device. When the app sends no valid id, the server mints one and returns it as `device_id` in the response body: in the token body of a password login without PKCE or an MFA verification, in the session body of a PKCE password login, and in the token exchange of an SSO sign-in. The field is `null` on `/auth/refresh` and in a web client's token exchange, and absent from a web client's login body (a browser keeps its id in the cookie). Store it in secure storage next to the tokens and send it on every later sign-in. It is not a credential, and responses that carry it are `Cache-Control: no-store`.

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
2. Client initiates OAuth at `/public/idp/login/{idp_slug}` with a PKCE challenge. A custom-scheme `redirect` (an allowed scheme, for example `org.endurain.app://callback`) always records the flow as `mobile`, which is how a system browser, unable to send headers, starts a mobile flow. Otherwise the backend uses the `X-Client-Type` header and records `web` when it is absent or invalid.
3. User authenticates with the OAuth provider
4. Provider redirects back to `/public/idp/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links the user account, creates a session, and redirects the client with a `session_id`
7. The client exchanges the session for tokens via the PKCE token exchange endpoint `/public/idp/session/{session_id}/tokens`. The exchange response follows the stored client type; an `X-Client-Type` header may be sent for clarity, but conflicting values are rejected:
  - **Web clients:** Access token + CSRF token in response body, refresh token as httpOnly cookie
  - **Mobile clients:** Access token + refresh token in response body

The session from step 6 lasts only as long as the sign-in's OAuth state (10 minutes), is not listed in the session lists and cannot be used until the exchange; the exchange gives it its normal lifetime. A session that is never exchanged is removed after those 10 minutes.

### Token Refresh Flow

The token refresh flow rotates the refresh token on every call:

1. When access token expires, client calls `POST /auth/refresh`:
    - **Web clients:** Include `X-CSRF-Token` header with the current CSRF token, except bootstrap refresh after page reload may omit it
    - **Mobile clients:** Include refresh token in request
2. Backend validates refresh token and session, checks for token reuse
    - **If token reuse detected:** Entire token family is invalidated (security breach response)
    - **Every refusal** (the session ended or expired, the token is invalid, expired or reused, or the user was deleted or deactivated) is `401` with `urn:endurain:error:invalid-token`, and the response clears the web client's refresh cookie. Sign in again. A CSRF header that does not match is `403` and keeps the cookie.
3. New tokens are generated (access, refresh, CSRF) with refresh token rotation
4. Old refresh token is stored for reuse detection (grace period: 10 seconds; the record is kept for the refresh token lifetime)
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

`refresh_token_expires_in` is the number of seconds until the client must sign in again: the refresh token's remaining lifetime, or the time left before the session reaches the absolute session timeout when that comes first. The refresh cookie of a web client expires at the same time. Every response that carries it (login, MFA verification, refresh and the SSO token exchange) follows this rule.

### Refresh Token Rotation & Reuse Detection

Endurain implements automatic refresh token rotation with reuse detection to prevent token theft:

| Security Feature | Description |
|------------------|-------------|
| **Automatic Rotation** | New refresh token issued on every `/auth/refresh` call |
| **Token Family Tracking** | All tokens in a session share a `token_family_id` |
| **Reuse Detection** | Old tokens are stored for the refresh token lifetime (`REFRESH_TOKEN_EXPIRE_DAYS`) and monitored for reuse |
| **Grace Period** | A retry within 10 seconds of a rotation is answered with the replacement token; after that, presenting the old token counts as reuse |
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
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: web`; JSON `{'mfa_challenge': <mfa_challenge from /auth/login>, 'mfa_code': '123456'}` | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: web`; Cookie: `endurain_refresh_token` | 30 requests/min |

### Core Authentication Endpoints (Mobile)

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` | Header: `X-Client-Type: mobile`; `FORM` with fields: `username`, `password`. Optional query params: `code_challenge`, `code_challenge_method` (mobile PKCE). HTTPS highly recommended | 10 requests/min |
| **Refresh Token** | `/auth/refresh` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: mobile`; JSON body: `{'mfa_challenge': <mfa_challenge from /auth/login>, 'mfa_code': '123456'}`. Optional query params: `code_challenge`, `code_challenge_method` (mobile PKCE) | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/public/idp` | None (public endpoint). Paged: optional `page_number` (default 1) and `num_records` (default 25, maximum 200); the response is `{items, total, page, num_records, next}` | - |
| **Initiate OAuth Login** | `/public/idp/login/{idp_slug}` | Header: `X-Client-Type` (`web` or `mobile`), optional when `redirect` is a custom scheme (that marks the flow as mobile). Query params: `redirect`, `code_challenge`, `code_challenge_method` | 10 requests/min per IP |
| **OAuth Callback** | `/public/idp/callback/{idp_slug}` | Query params: `state=<state>` and `code=<code>`, or `error=<provider error code>` when the provider refused. Always answers with a redirect to the frontend; a failed login lands on `/login?error=sso_failed` (or `sso_email_missing`), see [SSO failures](oauth-sso-pkce.md#sso-failures) | 10 requests/min per IP |
| **Token Exchange (PKCE)** | `/public/idp/session/{session_id}/tokens` | JSON: `{"code_verifier": "<verifier>"}` (password PKCE or SSO PKCE). Optional Header: `X-Client-Type`; if present, it must match the client type stored on the PKCE/OAuth state. | 10 requests/min |
| **Start IdP Link** | `POST /profile/identity-providers/{idp_id}/link` | Requires authenticated session and a step-up JSON body: `current_password` for local-password accounts, `idp_reauth` for accounts without one, and `mfa_code` when MFA is enabled; plus an optional `redirect` (relative frontend path). Returns `authorization_url` and sets the `endurain_idp_binding` cookie. The browser then navigates to `authorization_url`. `409` if already linked | 10 requests/min |
| **Start IdP Step-up** | `/profile/identity-providers/{idp_id}/step-up` | Requires authenticated session. JSON: `code_challenge`, `action`, `redirect` (relative path). Returns `authorization_url` and sets the `endurain_idp_binding` cookie. See [Account security](account-security.md#step-up-for-accounts-without-a-password) | 10 requests/min |

### Session Management Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Get Own Sessions** | `/profile/sessions` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `profile` scope. Paged like the admin list |
| **Delete Own Session** | `/profile/sessions/{session_id}` | Same headers and scope; web clients must also include `X-CSRF-Token` |
| **Delete Own Other Sessions** | `/profile/sessions` (`DELETE`) | Same headers and scope; ends every session except the current one |
| **Get User Sessions (admin)** | `/users/{user_id}/sessions` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:read` scope. Paged: optional `page_number` (default 1) and `num_records` (default 25, maximum 200); the response is `{items, total, page, num_records, next}` |
| **Delete Session (admin)** | `/users/{user_id}/sessions/{session_id}` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:write` scope; web clients must also include `X-CSRF-Token` |

### API Key Management Endpoints

Require JWT authentication with the standard `X-Client-Type` requirement; state-changing web requests must include `X-CSRF-Token`. API keys cannot manage other API keys.

<!-- generated:api-key-endpoints -->

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `POST /activities/upload` | .gpx, .tcx, .gz or .fit file. Accepts JWT **or** API key (`X-API-Key` header, or `?api_key=` query param only when `ALLOW_API_KEY_QUERY_PARAM=true`) with `activities:upload` scope. Answers `202` with an ingestion job. This unified-auth endpoint does not require `X-Client-Type` |
| **Ingestion Job** | `GET /activities/ingestion-jobs/{job_id}` | Poll the job returned by the upload. Accepts JWT or API key with the `activities:upload` scope |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

