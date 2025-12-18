# Handling authentication

Endurain supports integration with other apps through a comprehensive authentication system that includes standard username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration, and JWT-based session management.

## API Requirements
- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** Every request must include an `Authorization: Bearer <access token>` header with a valid (new or refreshed) access token.

## Token Handling

### Token Lifecycle
- The backend generates an `access_token` valid for 15 minutes (default) and a `refresh_token` valid for 7 days (default). This follows the best practice of short-lived and long-lived tokens for authentication sessions.
- The `access_token` is used for authorization; The `refresh_token` is used to refresh the `access_token`.
- Token expiration times can be customized via environment variables (see Configuration section below).

### Client-Specific Token Delivery
- **For web apps**: The backend sends access/refresh tokens as HTTP-only cookies:
  - `endurain_access_token` (HttpOnly, Secure in production)
  - `endurain_refresh_token` (HttpOnly, Secure in production)
  - `endurain_csrf_token` (HttpOnly, for CSRF protection)
- **For mobile apps**: Tokens are included in the response body as JSON.

## Authentication Flows

### Standard Login Flow
1. Client sends credentials to `/auth/login` endpoint
2. Backend validates credentials
3. If MFA is enabled, backend requests MFA code
4. If MFA is disabled or verified, backend generates tokens
5. Tokens are delivered based on client type (cookies for web, JSON for mobile)

### OAuth/SSO Flow
1. Client requests list of enabled providers from `/public/idp`
2. Client initiates OAuth by redirecting to `/public/idp/login/{idp_slug}`
3. User authenticates with the OAuth provider
4. Provider redirects back to `/public/idp/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links user account and generates session tokens
7. User is redirected to the app with active session

### Token Refresh Flow
1. When access token expires, client sends refresh token to `/auth/refresh`
2. Backend validates refresh token and session
3. New access token is generated and returned
4. Refresh token may be rotated based on configuration

## API Endpoints 
The API is reachable under `/api/v1`. Below are the authentication-related endpoints. Complete API documentation is available on the backend docs (`http://localhost:98/api/v1/docs` or `http://ip_address:98/api/v1/docs` or `https://domain/api/v1/docs`):

### Core Authentication Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` |  `FORM` with the fields `username` and `password`. This will be sent in clear text, use of HTTPS is highly recommended | 5 requests/min per IP |
| **Refresh Token** | `/auth/refresh` | header `Authorization Bearer: <Refresh Token>`  | - |
| **Verify MFA** | `/auth/mfa/verify` | JSON `{'username': <username>, 'mfa_code': '123456'}` | - |
| **Logout** | `/auth/logout` | header `Authorization Bearer: <Access Token>` | - |

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/public/idp` | None (public endpoint) | - |
| **Initiate OAuth Login** | `/public/idp/login/{idp_slug}` | Query params: `redirect`, `code_challenge`, `code_challenge_method` | 10 requests/min per IP |
| **OAuth Callback** | `/public/idp/callback/{idp_slug}` | Query params: `code=<code>`, `state=<state>` | 10 requests/min per IP |
| **Token Exchange (PKCE)** | `/public/idp/session/{session_id}/tokens` | JSON: `{"code_verifier": "<verifier>"}` | 10 requests/min per IP |
| **Link IdP to Account** | `/profile/idp/{idp_id}/link` | Requires authenticated session | 10 requests/min per IP |

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `/activities/create/upload` | .gpx, .tcx, .gz or .fit file |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

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

- **Web clients**: Tokens are set as HTTP-only cookies

```json
{
  "session_id": "unique_session_id"
}
```

- **Mobile clients**: Tokens are returned in response body

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "session_id": "unique_session_id",
  "token_type": "Bearer",
  "expires_in": 900
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

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `SECRET_KEY` | Secret key for JWT signing | - | Yes |
| `ALGORITHM` | JWT signing algorithm | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes | `15` | No |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime in days | `7` | No |
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins | `[]` | No |

### Cookie Configuration
For web clients, cookies are configured with:

- **HttpOnly**: Prevents JavaScript access (security measure)
- **Secure**: Only sent over HTTPS in production
- **SameSite**: Protection against CSRF attacks
- **Domain**: Set to match your application domain
- **Path**: Set to `/` for application-wide access

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

### For Client Applications

1. **Always use HTTPS** in production to protect credentials and tokens
2. **Store tokens securely**:
   - Web: Use HTTP-only cookies (handled automatically)
   - Mobile: Use secure storage (Keychain on iOS, KeyStore on Android)
3. **Implement token refresh** before access token expires
4. **Handle rate limits** with exponential backoff
5. **Validate SSL certificates** to prevent man-in-the-middle attacks
6. **Clear tokens on logout** to prevent unauthorized access

### For Security

1. **Never expose `SECRET_KEY`** in client code or version control
2. **Use strong, randomly generated secrets** for production
3. **Enable MFA** for enhanced account security
4. **Monitor failed login attempts** for suspicious activity
5. **Rotate refresh tokens** periodically for long-lived sessions
6. **Use appropriate scopes** - request only the permissions needed

### For OAuth/SSO

1. **Validate state parameter** to prevent CSRF attacks
2. **Use PKCE** (Proof Key for Code Exchange) for mobile apps
3. **Implement proper redirect URL validation** to prevent open redirects
4. **Handle provider errors gracefully** with user-friendly messages
5. **Support account linking** to allow users to connect multiple providers