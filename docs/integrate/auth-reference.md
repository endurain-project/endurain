# Configuration, scopes and best practices

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

<!-- generated:scopes -->

### Scope Usage
Scopes are automatically assigned based on user permissions and are embedded in JWT tokens. API endpoints validate required scopes before processing requests.

## Error responses

All errors, including authentication and authorization failures, use one problem-document shape. See [Errors, concurrency and rate limits](errors-and-limits.md).

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