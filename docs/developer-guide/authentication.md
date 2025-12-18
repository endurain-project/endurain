# Handling authentication

Endurain supports integration with other apps through a comprehensive OAuth 2.1 compliant authentication system that includes standard username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration, and JWT-based session management with refresh token rotation.

## API Requirements

- **Client Type Header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** Every request must include an `Authorization: Bearer <access token>` header with a valid access token.
- **CSRF Protection (Web Only):** State-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`) from web clients must include an `X-CSRF-Token` header.

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
- **CSRF Protection:** Refresh token in httpOnly cookie + CSRF token header prevents CSRF attacks
- **Session Persistence:** Page reload triggers `/auth/refresh` with httpOnly cookie to restore tokens
- **Multi-tab Support:** httpOnly cookie shared across browser tabs

### Token Delivery by Client Type

- **For web apps:** 
    - Access token and CSRF token returned in JSON response body (stored in-memory)
    - Refresh token set as httpOnly cookie (`endurain_refresh_token`)
    - On page reload, call `/auth/refresh` to restore in-memory tokens

- **For mobile apps:** 
    - All tokens (access, refresh, CSRF) returned in JSON response body
    - Store tokens in secure platform storage (iOS Keychain, Android EncryptedSharedPreferences)

## Authentication Flows

### Standard Login Flow (Username/Password)

1. Client sends credentials to `/auth/login` endpoint
2. Backend validates credentials and checks for account lockout
3. If MFA is enabled, backend returns MFA-required response
4. If MFA is disabled or verified, backend generates tokens
5. Tokens are delivered based on client type:
    - **Web:** Access token + CSRF token in response body, refresh token as httpOnly cookie
    - **Mobile:** All tokens in response body

### OAuth/SSO Flow

1. Client requests list of enabled providers from `/public/idp`
2. Client initiates OAuth by redirecting to `/public/idp/login/{idp_slug}` with PKCE challenge
3. User authenticates with the OAuth provider
4. Provider redirects back to `/public/idp/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links user account and generates session tokens based on client type:
    - **Web clients:** Redirected to app with tokens set automatically
    - **Mobile clients:** Exchange session for tokens via PKCE token exchange endpoint `/public/idp/session/{session_id}/tokens`

### Token Refresh Flow

The token refresh flow implements OAuth 2.1 compliant refresh token rotation:

1. When access token expires, client calls `POST /auth/refresh`:
    - **Web clients:** Include `X-CSRF-Token` header with current CSRF token
    - **Mobile clients:** Include refresh token in request
2. Backend validates refresh token and session, checks for token reuse
    - **If token reuse detected:** Entire token family is invalidated (security breach response)
3. New tokens are generated (access, refresh, CSRF) with refresh token rotation
4. Old refresh token is stored for reuse detection (grace period: 30 seconds)
5. Response includes new tokens; web clients receive new httpOnly cookie

**Token Refresh Request (Web):**

```http
POST /api/v1/auth/refresh
X-Client-Type: web
X-CSRF-Token: {current_csrf_token}
Cookie: endurain_refresh_token={refresh_token}
```

**Token Refresh Response:**

```json
{
  "session_id": "uuid",
  "access_token": "eyJ...",
  "csrf_token": "new_csrf_token",
  "token_type": "bearer",
  "expires_in": 1734567890
}
```

### Refresh Token Rotation & Reuse Detection

Endurain implements automatic refresh token rotation with reuse detection to prevent token theft:

| Security Feature | Description |
|------------------|-------------|
| **Automatic Rotation** | New refresh token issued on every `/auth/refresh` call |
| **Token Family Tracking** | All tokens in a session share a `token_family_id` |
| **Reuse Detection** | Old tokens are stored and monitored for reuse |
| **Grace Period** | 30-second window allows for network retry scenarios |
| **Family Invalidation** | If reuse detected, ALL tokens in family are invalidated |
| **Rotation Count** | Tracks number of rotations for audit purposes |

## API Endpoints 

The API is reachable under `/api/v1`. Below are the authentication-related endpoints. Complete API documentation is available on the backend docs (`http://localhost:98/api/v1/docs` or `http://ip_address:98/api/v1/docs` or `https://domain/api/v1/docs`):

### Core Authentication Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` | `FORM` with the fields `username` and `password`. HTTPS highly recommended | 3 requests/min per IP |
| **Refresh Token** | `/auth/refresh` | Cookie: `endurain_refresh_token`, Header: `X-CSRF-Token` (web only) | - |
| **Verify MFA** | `/auth/mfa/verify` | JSON `{'username': <username>, 'mfa_code': '123456'}` | 5 requests/min per IP |
| **Logout** | `/auth/logout` | Header: `Authorization: Bearer <Access Token>` | - |

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/public/idp` | None (public endpoint) | - |
| **Initiate OAuth Login** | `/public/idp/login/{idp_slug}` | Query params: `redirect`, `code_challenge`, `code_challenge_method` | 10 requests/min per IP |
| **OAuth Callback** | `/public/idp/callback/{idp_slug}` | Query params: `code=<code>`, `state=<state>` | 10 requests/min per IP |
| **Token Exchange (PKCE)** | `/public/idp/session/{session_id}/tokens` | JSON: `{"code_verifier": "<verifier>"}` | 10 requests/min per IP |
| **Link IdP to Account** | `/profile/idp/{idp_id}/link` | Requires authenticated session | 10 requests/min per IP |

### Session Management Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Get User Sessions** | `/sessions/user/{user_id}` | Header: `Authorization: Bearer <Access Token>` |
| **Delete Session** | `/sessions/{session_id}/user/{user_id}` | Header: `Authorization: Bearer <Access Token>` |

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `/activities/create/upload` | .gpx, .tcx, .gz or .fit file |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

## Progressive Account Lockout

Endurain implements progressive brute-force protection to prevent credential stuffing attacks:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 20 failures | 24 hours |

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
Complete the login by providing the MFA code to `/auth/mfa/verify`:

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

**Response (successful verification):**

- **Web clients**: Access token and CSRF token in response body, refresh token as httpOnly cookie

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "csrf_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 1734567890
}
```

- **Mobile clients**: All tokens returned in response body

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "csrf_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 1734567890
}
```

### Error Handling
- **No pending MFA login**: HTTP 400 Bad Request

```json
{
  "detail": "No pending MFA login found for this username"
}
```

- **Invalid MFA code**: HTTP 401 Unauthorized

```json
{
  "detail": "Invalid MFA code"
}
```

### Important Notes
- The pending MFA login session is temporary and will expire if not completed within a reasonable time
- After successful MFA verification, the pending login is automatically cleaned up
- The user must still be active at the time of MFA verification
- If no MFA is enabled for the user, the standard single-step authentication flow applies

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
2. Navigate to `/profile/idp/{idp_id}/link`
3. Authenticate with the identity provider
4. Provider is linked to the existing account

### OAuth Token Response
When authenticating via OAuth, the response format matches the standard authentication:

- **Web clients**: Tokens set as HTTP-only cookies, redirected to app
- **Mobile clients**: Must use PKCE flow (see [Mobile SSO with PKCE](#mobile-sso-with-pkce) below)

!!! info "Mobile OAuth/SSO"
    Mobile apps must use the PKCE flow for OAuth/SSO authentication. This provides enhanced security and a cleaner separation between the WebView and native app.

## Mobile SSO with PKCE

### Overview
PKCE (Proof Key for Code Exchange, RFC 7636) is required for mobile OAuth/SSO authentication. It provides enhanced security by eliminating the need to extract tokens from WebView cookies, preventing authorization code interception attacks, and enabling a cleaner separation between the WebView and native app.

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
- Characters: `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`
- Cryptographically random

**Code Challenge Computation:**

```
code_challenge = BASE64URL(SHA256(code_verifier))
```

#### Step 2: Initiate OAuth with PKCE Challenge

Open a WebView with the SSO URL including PKCE parameters:

**URL to Load:**

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
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "csrf_token": "abc123def456...",
  "expires_in": 900,
  "token_type": "Bearer"
}
```

**Error Responses:**

| Status | Error | Description |
| ------ | ----- | ----------- |
| 400 | Invalid code_verifier | Verifier doesn't match the challenge |
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
X-CSRF-Token: {csrf_token}
```

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
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins (JSON array) | `[]` | No |
| `FRONTEND_PROTOCOL` | Protocol for cookie security (`http` or `https`) | `http` | No |

### Cookie Configuration

For web clients, the refresh token cookie is configured with:

| Attribute | Value | Purpose |
|-----------|-------|---------|
| **HttpOnly** | `true` | Prevents JavaScript access (XSS protection) |
| **Secure** | `true` (in production) | Only sent over HTTPS |
| **SameSite** | `Strict` | Prevents CSRF attacks |
| **Path** | `/` | Application-wide access |
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
| `health:read` | Read health metrics (weight, sleep, steps) | Read-only |
| `health:write` | Record health metrics | Write |
| `health_targets:read` | Read health targets | Read-only |
| `health_targets:write` | Modify health targets | Write |
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
  "detail": "Invalid client type. Must be 'web' or 'mobile'"
}
```

**Expired Token:**

```json
{
  "detail": "Token has expired"
}
```

**Invalid Credentials:**

```json
{
  "detail": "Incorrect username or password"
}
```

**Rate Limit Exceeded:**

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

**Missing Required Scope:**

```json
{
  "detail": "Insufficient permissions. Required scope: activities:write"
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
    - `X-CSRF-Token: {csrf_token}` for POST/PUT/DELETE/PATCH requests
5. **Handle page reload gracefully** - Call `/auth/refresh` on app initialization to restore in-memory tokens
6. **Clear tokens on logout** - The httpOnly cookie is cleared by the backend

### For Mobile Client Applications

1. **Store tokens securely**:
    - **iOS**: Keychain Services
    - **Android**: EncryptedSharedPreferences or Android Keystore
2. **Use PKCE for OAuth/SSO** - Required for mobile OAuth flows
3. **Include required headers:**
    - `Authorization: Bearer {access_token}` for all authenticated requests
    - `X-Client-Type: mobile` for all requests
    - `X-CSRF-Token: {csrf_token}` for state-changing requests
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

1. **Always use PKCE** - Required for mobile, recommended for web
2. **Validate state parameter** - Prevents CSRF attacks on OAuth flow
3. **Implement proper redirect URL validation** - Prevents open redirects
4. **Handle provider errors gracefully** with user-friendly messages
5. **Support account linking** - Allow users to connect multiple providers
6. **Respect token expiry** - OAuth state expires after 10 minutes