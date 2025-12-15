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
1. Client sends credentials to `/token` endpoint
2. Backend validates credentials
3. If MFA is enabled, backend requests MFA code
4. If MFA is disabled or verified, backend generates tokens
5. Tokens are delivered based on client type (cookies for web, JSON for mobile)

### OAuth/SSO Flow
1. Client requests list of enabled providers from `/identity-providers`
2. Client initiates OAuth by redirecting to `/identity-providers/login/{idp_slug}`
3. User authenticates with the OAuth provider
4. Provider redirects back to `/identity-providers/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links user account and generates session tokens
7. User is redirected to the app with active session

### Token Refresh Flow
1. When access token expires, client sends refresh token to `/refresh`
2. Backend validates refresh token and session
3. New access token is generated and returned
4. Refresh token may be rotated based on configuration

## API Endpoints 
The API is reachable under `/api/v1`. Below are the authentication-related endpoints. Complete API documentation is available on the backend docs (`http://localhost:98/api/v1/docs` or `http://ip_address:98/api/v1/docs` or `https://domain/api/v1/docs`):

### Core Authentication Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/token` |  `FORM` with the fields `username` and `password`. This will be sent in clear text, use of HTTPS is highly recommended | 5 requests/min per IP |
| **Refresh Token** | `/refresh` | header `Authorization Bearer: <Refresh Token>`  | - |
| **Verify MFA** | `/mfa/verify` | JSON `{'username': <username>, 'mfa_code': '123456'}` | - |
| **Logout** | `/logout` | header `Authorization Bearer: <Access Token>` | - |

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/identity-providers` | None (public endpoint) | - |
| **Initiate OAuth Login** | `/identity-providers/login/{idp_slug}` | Query param: `redirect=<path>` (optional) | 10 requests/min per IP |
| **OAuth Callback** | `/identity-providers/callback/{idp_slug}` | Query params: `code=<code>`, `state=<state>` | Configurable |
| **Link IdP to Account** | `/identity-providers/login/{idp_slug}?link=true` | Requires authenticated session | 10 requests/min per IP |

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `/activities/create/upload` | .gpx, .tcx, .gz or .fit file |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

## MFA Authentication Flow

When Multi-Factor Authentication (MFA) is enabled for a user, the authentication process requires two steps:

### Step 1: Initial Login Request
Make a standard login request to `/token`:

**Request:**
```http
POST /api/v1/token
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
Complete the login by providing the MFA code to `/mfa/verify`:

**Request:**
```http
POST /api/v1/mfa/verify
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
  "expires_in": 900,
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
- `redirect_uri`: Callback URL (typically `/api/v1/identity-providers/callback/{idp_slug}`)

### Linking Accounts
Users can link their Endurain account to an OAuth provider:

1. User must be authenticated with a valid session
2. Navigate to `/identity-providers/login/{idp_slug}?link=true`
3. Authenticate with the identity provider
4. Provider is linked to the existing account

### OAuth Token Response
When authenticating via OAuth, the response format matches the standard authentication:

- **Web clients**: Tokens set as HTTP-only cookies, redirected to app
- **Mobile clients**: Tokens returned in JSON format

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