# Configuration, scopes and best practices

## Configuration

### Environment Variables

The following environment variables control authentication behavior:

#### Token Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `SECRET_KEY` | Secret key for JWT signing (min 32 characters and at least 10 distinct characters required). Access tokens and refresh tokens are signed with separate keys derived from it. Several keys separated by commas rotate it: the first signs, every key verifies | - | Yes |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Deprecated in v0.21: set in Settings > Server > Sessions, removed in v0.22. Access token lifetime in minutes | `15` | No |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Deprecated in v0.21: set in Settings > Server > Sessions, removed in v0.22. Refresh token lifetime in days | `7` | No |

#### Session Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `SESSION_IDLE_TIMEOUT_ENABLED` | Deprecated in v0.21: set in Settings > Server > Sessions, removed in v0.22. Enable session idle timeout | `false` | No |
| `SESSION_IDLE_TIMEOUT_HOURS` | Deprecated in v0.21: set in Settings > Server > Sessions, removed in v0.22. Hours of inactivity before session expires | `1` | No |
| `SESSION_ABSOLUTE_TIMEOUT_HOURS` | Deprecated in v0.21: set in Settings > Server > Sessions, removed in v0.22. Maximum session lifetime in hours. Used only when the variable is set; otherwise the server setting keeps its own default of 720 hours (30 days) | `720` (server setting) | No |

#### Security Configuration

| Variable | Description | Default | Required |
| -------- | ----------- | ------- | -------- |
| `ENVIRONMENT` | Controls refresh cookie security for login, refresh, and OAuth/SSO token exchange. `production` and `demo` set the `Secure` flag on the refresh cookie and the OAuth/SSO session cookie, which requires Endurain to be served over HTTPS in those environments for login, session refresh, and SSO to work. | `production` | No |
| `ALLOWED_REDIRECT_URIS` | Comma-separated exact redirect addresses allowed as SSO redirect targets (e.g., `com.endurain.endurain:/auth/sso/callback,nodomain.freeyourgadget.gadgetbridge://endurain/oauth/callback`). It is the only redirect allow-list: a redirect with a scheme must equal a listed address, and relative paths need no entry. The default is the callback of the Endurain mobile app; setting the variable replaces the default, so keep `com.endurain.endurain:/auth/sso/callback` in the list. The current Endurain mobile app still sends `endurain://auth/sso/callback`, so add it too until an app release uses the new address. The scheme is matched case-insensitively and the rest exactly, query string and fragment included. An `https` entry must be `https://host/path` (an Android App Link or iOS Universal Link) with a host, no user info and a valid port. Startup fails on an entry with `http`, `javascript`, `data`, `file`, `vbscript` or `blob`, with a control character, without a target, or with a malformed `https` address. An app listed here receives tokens with every scope the signing-in user holds, administrator scopes included, so list only apps you trust with the whole account. See [Redirect addresses](oauth-sso-pkce.md#redirect-schemes). | `com.endurain.endurain:/auth/sso/callback` | No |
| `ALLOWED_REDIRECT_SCHEMES` | Removed in v0.21. Endurain refuses to start while it is set. List the exact addresses in `ALLOWED_REDIRECT_URIS` instead. | - | No |
| `SSRF_ALLOWED_HOSTS` | SSRF allowlist for admin-configured outbound calls (identity provider discovery, signing keys, token, userinfo and revocation calls, and the sign-in redirect). A listed host may also use plain `http://` for these; any other identity provider URL must use `https://`. Also covers the reverse-geocoding host and the map tile server used for activity thumbnails. Comma-separated list of exact hostnames (case-insensitive) and/or explicit IP CIDR ranges. Supports self-hosted identity providers on private networks, including shared address space such as Tailscale (`100.64.0.0/10`). Examples: `auth.internal.example.com` or `auth.internal.example.com,10.10.0.0/24,fd00::/64`. Wildcards are rejected. IPv4 prefix must be ≥ /8, IPv6 ≥ /32. Every allowlisted outbound call is logged at INFO level for audit. | `` | No |

#### Rate Limiting and Shared State

Rate-limit counters and all auth-security state (login/step-up lockout, pending
MFA login and password-change state, MFA setup secrets, Garmin MFA codes, websocket tickets) share
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
| **SameSite** | `Strict` | The browser does not send the cookie on cross-site requests, which is the main CSRF defence for it |
| **Path** | `/` | Required by the `__Host-` name prefix of a deployed environment, together with `Secure` and no `Domain` attribute |
| **Expires** | 7 days (default) | Matches refresh token lifetime, or the time left before the absolute session timeout when that comes first |

## Security Scopes

Endurain uses OAuth-style scopes to control API access. Each scope controls access to specific resource groups:

### Available Scopes

A scope name is `resource:action` in lowercase kebab-case (`health-targets:read`), plus the bare `account`. The catalogue only grows: from v0.21.0 on, a scope's name and meaning do not change.

<!-- generated:scopes -->

### Scope Usage
Scopes are assigned from the user's role and embedded in the `scope` claim of the JWT access token, a space-separated string. An endpoint checks its required scopes against the scopes the token carries, limited to the scopes the user's role holds when the request arrives: a token cannot name a scope its role lacks, and a demotion takes effect on the next request. A missing scope is `403` with `WWW-Authenticate: Bearer error="insufficient_scope"`. Tokens issued by a login carry every scope of the role. `account` covers the account's own data; `account:export` covers profile export and import, `account:security` covers the password, email, MFA, API keys, sessions, identity provider links and account deletion, and `account:integrations` covers linking and unlinking Garmin Connect and Strava (`POST` and `DELETE /garmin/link`, `POST /garmin/mfa`, `POST` and `DELETE /strava/link`, `POST /strava/state`, `PUT /strava/client`). Every user holds all four.

## Error responses

All errors, including authentication and authorization failures, use one problem-document shape. See [Errors, concurrency and rate limits](errors-and-limits.md).

## Best Practices

### For Web Client Applications

1. **Store access and CSRF tokens in memory** - Never persist in localStorage or sessionStorage
2. **Implement automatic token refresh** - Refresh before access token expires (e.g., at 80% of lifetime)
3. **Handle concurrent refresh requests** - Use a refresh lock pattern to prevent race conditions
4. **Always include required headers:**
    - `Authorization: Bearer {access_token}` for all authenticated requests
    - `X-Client-Type: web` on the session routes under `/auth` (required) and on every `POST`, `PUT`, `PATCH` and `DELETE` (the CSRF middleware reads it); not on `/public` routes
    - `X-CSRF-Token: {csrf_token}` for protected POST/PUT/DELETE/PATCH requests, except `/auth/refresh` bootstrap. Protected web writes require the header, though the server checks only that it is present; `/auth/refresh` also validates the token value when supplied and bound to the session
5. **Handle page reload gracefully** - Call `/auth/refresh` on app initialization to restore in-memory tokens
6. **Clear tokens on logout** - The httpOnly cookie is cleared by the backend, on every logout answer, even when the refresh token was already dead. When `POST /auth/logout` answers an `https:` `idp_logout_url`, navigate the browser to it to end the identity provider session too

### For Mobile Client Applications

1. **Store tokens securely**:
    - **iOS**: Keychain Services
    - **Android**: EncryptedSharedPreferences or Android Keystore
2. **Use PKCE for OAuth/SSO** - Required for OAuth/SSO flows
3. **Include required headers:**
    - `Authorization: Bearer {access_token}` for all authenticated requests
    - `X-Client-Type: mobile` on the session routes under `/auth` (required); it is optional elsewhere and not sent on `/public` routes
    - The refresh token goes in the JSON body (`{"refresh_token": "..."}`) of `/auth/refresh` and `/auth/logout`, never in the `Authorization` header
4. **Handle token refresh proactively** - Refresh before expiration
5. **Implement secure token deletion** on logout, and open an `idp_logout_url` the logout answer carries in the system browser if the provider session should end too

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
3. **Grant only the scopes the integration needs** — a key can hold the scopes over the account's own data listed in [API keys](api-keys.md#scopes), never the account's security, export, provider links or an administrator scope
4. **Set an expiry date** when creating keys for temporary or one-off integrations
5. **Rotate keys periodically** — delete the old key and create a new one; update any dependent services before deleting
6. **Revoke immediately** if a key is suspected to be compromised — revocation takes effect instantly
7. **Monitor `last_used_at`** via the list endpoint to detect unused keys that can be cleaned up