# Handling authentication

Endurain supports integration with other apps through an authentication system that includes username/password authentication, Multi-Factor Authentication (MFA), OAuth/SSO integration with PKCE (S256), and JWT-based session management with refresh token rotation and reuse detection. `/auth/login` is a username/password grant, which OAuth 2.1 does not include, so Endurain does not claim to be OAuth 2.1 compliant.

## API Requirements

- **Client Type Header:** `POST /auth/login`, `/auth/mfa/verify`, `/auth/password-change`, `/auth/sessions/{session_id}/tokens`, `/auth/refresh` and `/auth/logout` require an `X-Client-Type` header with `web` or `mobile`; a missing or unknown value is `422`. It is an ordinary header parameter in the OpenAPI document, not a security scheme. Protected routes authenticate first and do not read it: a call without a valid token is `401` with `WWW-Authenticate` whatever the header says. The other flows follow the endpoint-specific requirements below.
- **Where the routes live:** the routes that obtain, renew or end a session (`/auth/login`, `/auth/mfa/verify`, `/auth/password-change`, `/auth/sessions/{session_id}/tokens`, `/auth/refresh`, `/auth/logout`) are under `/auth`. Every other route a visitor can call without signing in is under `/public` (see [Public endpoints](public-endpoints.md)).
- **PKCE on password sign-in:** a mobile client sends `code_challenge` and `code_challenge_method` (`S256`) as form fields of `POST /auth/login`; both are required. A web client sends neither: the field is refused. A missing, refused or malformed field is `422`, and it is checked before the password. The MFA step and the password-change step carry no PKCE values; the sign-in keeps the ones the password step sent.
- **OAuth/PKCE Client Type Binding:** For `/public/idp/login/{idp_slug}` and a mobile password sign-in, the backend records a `client_type` on the PKCE/OAuth state. `POST /auth/sessions/{session_id}/tokens` requires `X-Client-Type`, and it must match the stored value, which controls the response shape. A different value is refused with the same `400` as a wrong `code_verifier`, so a session one kind of client started cannot be redeemed by the other.
- **Authorization:** Most protected JWT requests must include an `Authorization: Bearer <access token>` header with a valid access token. Login, MFA verification, the password-change step, OAuth initiation/callback/token exchange, password reset, sign-up, and activity uploads authenticated with an API key are exceptions.
- **CSRF Protection (Web Only):** State-changing protected web requests (`POST`, `PUT`, `DELETE`, `PATCH`) must include an `X-CSRF-Token` header. The server checks only that the header is present, and only for requests that send `X-Client-Type: web`, so it is a defence in depth rather than the CSRF defence. A custom header makes a cross-origin browser request preflighted, so CORS decides whether it is sent. The protection that matters is that protected routes read the access token from the `Authorization` header, which a browser never sends on its own, and that the refresh cookie is `SameSite=Strict` and limited to `/api/v1/auth`. `/auth/refresh` supports a bootstrap refresh without this header after page reload; if the header is provided and the session has a stored CSRF binding, the token value must be valid.

!!! note "API Key Authentication"
    Certain endpoints support API key authentication as an alternative to Bearer + `X-Client-Type` headers. API key requests do not require the `X-Client-Type` header or a CSRF token. See [API Key Authentication](api-keys.md) for details.

## Token Handling

### Token Lifecycle

- The backend generates an `access_token` valid for 15 minutes (default) and a `refresh_token` valid for 7 days (default).
- The `access_token` is used for authorization; the `refresh_token` is used to obtain new access tokens.
- Both tokens are JWTs signed with HS256. The JOSE header carries `typ` (`at+jwt` for an access token, `rt+jwt` for a refresh token) and `kid`, the id of the signing key; the `scope` claim is a space-separated string of the scopes the token carries ([RFC 9068](https://datatracker.ietf.org/doc/html/rfc9068)). A client treats both tokens as opaque and does not read them.
- The two kinds cannot stand in for each other ([RFC 8725](https://datatracker.ietf.org/doc/html/rfc8725)): each is signed with a key of its own, derived from `SECRET_KEY` for that kind, and carries its own audience. Both have `iss` set to `ENDURAIN_HOST`. An access token's `aud` is `ENDURAIN_HOST`; a refresh token's `aud` is the URL of the refresh endpoint, `<ENDURAIN_HOST>/api/v1/auth/refresh` (`/auth/logout` accepts the same token). Both carry `client_id`, the client type (`web` or `mobile`) of the session they belong to.
- `iat`, `nbf` and `exp` are checked with 60 seconds of leeway, so a token issued by a replica whose clock is slightly ahead, or one that expired a moment ago, is still accepted. It does not lengthen a session: an access token is honoured only while its session exists, and a refresh token only against its session.
- Upgrading to v0.21 signs everyone out once: refresh tokens issued before it are signed with the old key, carry no `client_id` and are refused, and the sessions they belong to are ended. Web and mobile users sign in again.
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
| **Device id** | Web: httpOnly cookie (`endurain_device`, or `__Secure-endurain_device` in production and demo, path `/api/v1`, `SameSite=Strict`). Mobile: the app's own storage, sent as the `X-Device-Id` header | 400 days from the last sign-in | Recognises the browser or app, so a sign-in from a new one sends a [security notice](../features/accounts-and-sign-in.md#security-notifications), and a known one is not held by the [account lock](account-security.md#progressive-account-lockout). Not a credential; the server stores only its SHA-256 hash |

**Cookie names:** In `production` and `demo`, where the cookies carry `Secure`, their names carry the `__Secure-` prefix (`__Secure-endurain_refresh_token`, `__Secure-endurain_device`, `__Secure-endurain_idp_binding`), so a browser stores one only when it was set over HTTPS with `Secure`. Development serves plain HTTP and keeps the plain names. A web session that signed in under the old name has no refresh cookie under the new one, so after an upgrade every web user signs in again once. The device cookie is not carried over either, so the first sign-in after the upgrade counts as a new device and sends a new-device notice.

**Security Properties:**

- **XSS exposure:** Keeping the access token in memory keeps it out of storage that a browser extension or a later page can read, and it expires in minutes. It does not stop script running in the page: that script can call `POST /auth/refresh`, which the browser answers with the httpOnly cookie, and read the fresh access token from the response. The refresh route does not require the `X-CSRF-Token` header (a bootstrap refresh after a page reload sends none), and the CSP allows inline scripts (next point).
- **CSRF Protection:** Protected routes authenticate with the `Authorization` header, which a browser never sends on its own, and the refresh token is an httpOnly `SameSite=Strict` cookie limited to `/api/v1/auth`. The `X-CSRF-Token` header is a presence check on top of that, and `/auth/refresh` also validates its value when the client sends it and the session has a stored CSRF binding.
- **Content Security Policy:** HTML responses carry a CSP whose `script-src` and `style-src` include `'unsafe-inline'`, so the policy does not stop an injected inline script. This is an accepted risk. The defences that remain are never rendering user data with `v-html`, keeping the access token out of persistent storage, and the `SameSite=Strict`, path-limited refresh cookie. The policy carries `frame-ancestors 'none'`, and every response carries `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-site`. A JSON response carries `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. Error responses carry these headers too. A reverse proxy that sets its own `Content-Security-Policy` or cross-origin policies replaces them, so let Endurain's headers through.
- **Self-declared client type:** `X-Client-Type` is chosen by the caller, so it selects the response shape and whether the CSRF header is required but proves nothing about who is calling. This is an accepted risk: a caller that omits `web` only skips a presence check that is not the CSRF defence, and it still needs a valid access token. A session keeps the client type it was created for, so a web session's refresh token taken out of its cookie cannot be refreshed by declaring `mobile`.
- **Session Persistence:** Page reload triggers `/auth/refresh` with httpOnly cookie to restore tokens
- **Multi-tab Support:** httpOnly cookie shared across browser tabs

### Token Delivery by Client Type

- **For web apps:** 
    - Access token and CSRF token returned in JSON response body (stored in-memory)
    - Refresh token set as httpOnly cookie (`endurain_refresh_token`; `__Secure-endurain_refresh_token` in production and demo)
    - Password login, MFA verification, the password-change step and the SSO token exchange also set the `endurain_device` cookie (prefixed like the refresh cookie), which names the browser for new-device sign-in notices
    - On page reload, call `/auth/refresh` to restore in-memory tokens

- **For mobile apps:** 
  - Password login (with its PKCE challenge) and OAuth/SSO return a `session_id` first; the app exchanges that session with its PKCE verifier to receive access and refresh tokens. A mobile sign-in never answers tokens directly
    - Store tokens in secure platform storage (iOS Keychain, Android EncryptedSharedPreferences)
  - **Device id:** send `X-Device-Id` on `/auth/login`, `/auth/mfa/verify`, `/auth/password-change` and the `/auth/sessions/{session_id}/tokens` exchange, with the value the server returned earlier (43 characters of `A-Z a-z 0-9 - _`; a missing or malformed value counts as none). A sign-in from an id the account has not used before sends the user a new-device notice, except the account's first device. When the app sends no valid id, the server mints one and returns it as `device_id` in the response body: in the session body of a password login, an MFA verification or a password change, and in the token body of the exchange of an SSO sign-in. The field is `null` on `/auth/refresh` and in a web client's token exchange, and absent from a web client's login body (a browser keeps its id in the cookie). Store it in secure storage next to the tokens and send it on every later sign-in. It is not a credential, and responses that carry it are `Cache-Control: no-store`.

## Authentication Flows

### Standard Login Flow (Username/Password)

1. Client sends credentials to `/auth/login` endpoint
2. Backend validates credentials and checks for account lockout
3. Backend answers with a body whose `next_step` says what the client does next (see [Sign-in steps](#sign-in-steps))
4. The client follows the steps until it receives `tokens` or `exchange`
5. Tokens are delivered based on client type:
    - **Web:** Access token + CSRF token in response body, refresh token as httpOnly cookie
    - **Mobile:** A session ID, exchanged for the tokens in the response body (CSRF not included, not needed for mobile logic) with the PKCE verifier (see [Mobile Password Login with PKCE](oauth-sso-pkce.md#mobile-password-login-with-pkce))

#### Sign-in steps

Every answer of `POST /auth/login`, `POST /auth/mfa/verify` and `POST /auth/password-change` carries a required `next_step`. A client switches on it; the other members of the body depend on its value.

| `next_step` | Meaning | Body members | The client |
| ----------- | ------- | ------------ | ---------- |
| `mfa` | A second factor must be verified | `mfa_challenge` | Asks for the MFA code and sends it with the challenge to `POST /auth/mfa/verify`. The challenge lives 5 minutes, ends after 3 wrong codes (`400` each, then `401`), and is accepted only from the client network (an IPv4 address or an IPv6 /64) and client type of the password step; a dead challenge is `401` and the client restarts at `POST /auth/login` |
| `password_change` | An administrator set the account's password, so the user must choose a new one before a session exists | `password_change_challenge` | Asks for a new password and sends it with the challenge to `POST /auth/password-change` |
| `exchange` | A mobile client gets a session to exchange | `session_id`, `device_id` | Exchanges the session at `/auth/sessions/{session_id}/tokens` with its PKCE verifier |
| `tokens` | The client is signed in | `session_id`, `access_token`, `expires_in`, `refresh_token_expires_in`, `token_type`, and `csrf_token` (web) or `refresh_token` and `device_id` (mobile) | Stores the tokens |

`POST /auth/refresh` and `POST /auth/sessions/{session_id}/tokens` answer the `tokens` body too: the same two bodies, `token_type` is `bearer` in both, the web body has `csrf_token` and no `refresh_token`, and the mobile body has `refresh_token` and `device_id` and no `csrf_token`. `/auth/login` can answer `mfa`, `password_change`, `exchange` (mobile) or `tokens` (web). `/auth/mfa/verify` answers `password_change`, `exchange` (mobile) or `tokens` (web). `/auth/password-change` answers `exchange` (mobile) or `tokens` (web).

!!! warning "Treat an unknown `next_step` as \"update the app\""
    The set of steps can grow. A client that receives a `next_step` it does not know cannot continue the sign-in: it must stop, keep no partial state and tell the user that the app needs an update. Do not guess from the other members of the body.

#### Password change at sign-in

When an administrator sets a user's password, or creates the account with one, the administrator knows it, so the account must replace it at its next password sign-in. An administrator can also require the change without setting a password, through `POST /users/{user_id}/password/require-change`: the user keeps the current password until the next password sign-in, where the same `password_change` step applies. That route ends all of the user's sessions and answers `409` for an account that has no local password. `POST /auth/login` (and `POST /auth/mfa/verify` for an account with MFA, after the code is verified) then answers `password_change` instead of tokens and creates no session. The `password_change_challenge` is valid for 10 minutes, works once, and names the sign-in, its client type and its PKCE values.

```http
POST /api/v1/auth/password-change
Content-Type: application/json
X-Client-Type: web|mobile

{
  "password_change_challenge": "<password_change_challenge from the sign-in response>",
  "password": "the new password"
}
```

The new password must meet the account's password policy and differ from the current one. The answer is the one the sign-in would have given: `tokens` for a web client, or `exchange` for a mobile client. The new password, its audit entry and the session are one transaction, and unused password-reset links are voided.

| Status | Meaning |
| ------ | ------- |
| `401` | The challenge is unknown, expired or already used, was issued to the other client type, or the account no longer needs to change its password. One answer for all of these |
| `403` | The account is no longer active |
| `422` | The password does not meet the policy (the `type` names why, for example `urn:endurain:error:password-too-short`). The challenge stays valid, so the client can ask again |
| `429`, `503` | Rate limit, or the shared sign-in state is unavailable |

Sign-in through an identity provider (SSO) does not use the password, so it is not affected: an account whose password an administrator set can still sign in with its provider.

### OAuth/SSO Flow

1. Client requests list of enabled providers from `/public/idp`
2. Client initiates OAuth at `/public/idp/login/{idp_slug}` with a PKCE challenge. A custom-scheme `redirect` (an allowed scheme, for example `org.endurain.app://callback`) always records the flow as `mobile`, which is how a system browser, unable to send headers, starts a mobile flow. Otherwise the backend uses the `X-Client-Type` header and records `web` when it is absent or invalid.
3. User authenticates with the OAuth provider
4. Provider redirects back to `/public/idp/callback/{idp_slug}` with authorization code
5. Backend exchanges code for provider tokens and user info
6. Backend creates or links the user account, creates a session, and redirects the client with a `session_id`
7. The client exchanges the session for tokens via the PKCE token exchange endpoint `/auth/sessions/{session_id}/tokens`. The exchange response follows the stored client type; the `X-Client-Type` header is required and must match it, or the exchange is refused:
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
    - **Retry within the grace period:** an already rotated refresh token presented again within 10 seconds is answered with the same replacement refresh token only for the client that rotated it (same IPv4 address or IPv6 /64, and same `User-Agent`). From any other client it counts as reuse and ends the session
    - **Client type:** a session is refreshed only with the `X-Client-Type` it was created for. A web session's refresh token presented as `mobile`, or a mobile one as `web`, is refused like an invalid token
    - **Every refusal** (the session ended or expired, belongs to the other client type, the token is invalid, expired or reused, or the user was deleted or deactivated) is `401` with `urn:endurain:error:invalid-token`, and the response clears the web client's refresh cookie. Sign in again. A CSRF header that does not match is `403` and keeps the cookie.
3. New tokens are generated (access, refresh, CSRF) with refresh token rotation
4. Old refresh token is stored for reuse detection, with a fingerprint of the rotating client's network and `User-Agent` (grace period: 10 seconds; the record is kept for the refresh token lifetime)
5. Response includes new tokens; web clients receive new httpOnly cookie

**Token Refresh Request (Web):**

```http
POST /api/v1/auth/refresh
X-Client-Type: web
X-CSRF-Token: {current_csrf_token}
Cookie: __Secure-endurain_refresh_token={refresh_token}
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

`refresh_token_expires_in` is the number of seconds until the client must sign in again: the refresh token's remaining lifetime, or the time left before the session reaches the absolute session timeout when that comes first. The refresh cookie of a web client expires at the same time. Every response that carries it (a web login, MFA verification, refresh and the token exchange) follows this rule.

### Refresh Token Rotation & Reuse Detection

Endurain implements automatic refresh token rotation with reuse detection to prevent token theft:

| Security Feature | Description |
|------------------|-------------|
| **Automatic Rotation** | New refresh token issued on every `/auth/refresh` call |
| **Token Family Tracking** | All tokens in a session share a `token_family_id` |
| **Reuse Detection** | Old tokens are stored for the refresh token lifetime (`REFRESH_TOKEN_EXPIRE_DAYS`) and monitored for reuse |
| **Grace Period** | A retry within 10 seconds of a rotation is answered with the replacement token only for the client that rotated it (same IPv4 address or IPv6 /64, and same `User-Agent`). From any other client, or after 10 seconds, presenting the old token counts as reuse and ends the session |
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
| **Authorize** | `/auth/login` | Header: `X-Client-Type: web`; `FORM` with fields: `username`, `password`. `code_challenge` and `code_challenge_method` are refused (`422`). HTTPS highly recommended | 10 requests/min |
| **Refresh Token** | `/auth/refresh` | Header: `X-Client-Type: web`; Cookie: `__Secure-endurain_refresh_token` (`endurain_refresh_token` in development); optional Header: `X-CSRF-Token` (bootstrap logic) | 30 requests/min |
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: web`; JSON `{'mfa_challenge': <mfa_challenge from /auth/login>, 'mfa_code': '123456'}` | 10 requests/min |
| **Change Password** | `/auth/password-change` | Header: `X-Client-Type: web`; JSON `{'password_change_challenge': <password_change_challenge from /auth/login or /auth/mfa/verify>, 'password': '<new password>'}` | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: web`; Cookie: `__Secure-endurain_refresh_token` (`endurain_refresh_token` in development) | 30 requests/min |

### Core Authentication Endpoints (Mobile)

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Authorize** | `/auth/login` | Header: `X-Client-Type: mobile`; `FORM` with fields: `username`, `password`, `code_challenge`, `code_challenge_method` (`S256`); all four are required. HTTPS highly recommended | 10 requests/min |
| **Refresh Token** | `/auth/refresh` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |
| **Verify MFA** | `/auth/mfa/verify` | Header: `X-Client-Type: mobile`; JSON body: `{'mfa_challenge': <mfa_challenge from /auth/login>, 'mfa_code': '123456'}`. No PKCE values: the challenge of the password step is kept with the MFA challenge | 10 requests/min |
| **Change Password** | `/auth/password-change` | Header: `X-Client-Type: mobile`; JSON `{'password_change_challenge': <password_change_challenge from /auth/login or /auth/mfa/verify>, 'password': '<new password>'}`. The PKCE values of the sign-in are kept with the challenge | 10 requests/min |
| **Logout** | `/auth/logout` | Header: `X-Client-Type: mobile`; Header: `Authorization: Bearer <Refresh Token>` | 30 requests/min |

### Logout

`POST /auth/logout` ends the session named by the refresh token and answers `200` with `Cache-Control: no-store` and a JSON body:

```json
{ "idp_logout_url": "https://idp.example.com/logout?id_token_hint=...&client_id=...&post_logout_redirect_uri=https%3A%2F%2Fendurain.example.com%2Flogin" }
```

`idp_logout_url` is `null` unless the session signed in through an identity provider whose discovery document names an `end_session_endpoint` ([OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)). Then it is that endpoint with the query parameters `id_token_hint` (the ID token the provider issued at sign-in), `client_id` and, for a web client only, `post_logout_redirect_uri` (`<ENDURAIN_HOST>/login`), added to any query string the endpoint already has. The URL carries the ID token, so use it once and do not store or log it.

- **Web client:** the session is already ended and the refresh cookie cleared when the answer arrives. When `idp_logout_url` is an `https:` URL, navigate the browser to it so the provider ends its session and sends the user back to the login page; otherwise show the login page.
- **Mobile client:** the session is already ended. To also end the provider session, open `idp_logout_url` in the system browser (`ASWebAuthenticationSession` or Custom Tabs), as for sign-in. It has no `post_logout_redirect_uri`, so the provider shows its own signed-out page. A client that does not open it leaves the provider session in place.

The Endurain session is ended and committed before the provider is asked for its endpoint. If the provider cannot be reached for it, logout still succeeds with `idp_logout_url: null` and the provider session stays.

The reverse also holds: signing out at a provider that supports back-channel logout ends the Endurain sessions signed in through it, and the client's next request or refresh is `401`. See [Provider-initiated sign-out](oauth-sso-pkce.md#provider-initiated-sign-out).

### OAuth/SSO Endpoints

| What | Url | Expected Information | Rate Limit |
| ---- | --- | -------------------- | ---------- |
| **Get Enabled Providers** | `/public/idp` | None (public endpoint). Paged: optional `page_number` (default 1) and `num_records` (default 25, maximum 200); the response is `{items, total, page, num_records, next}` | - |
| **Initiate OAuth Login** | `/public/idp/login/{idp_slug}` | Header: `X-Client-Type` (`web` or `mobile`), optional when `redirect` is a custom scheme (that marks the flow as mobile). Query params: `redirect`, `code_challenge`, `code_challenge_method` | 10 requests/min per IP |
| **OAuth Callback** | `/public/idp/callback/{idp_slug}` | Query params: `state=<state>` and `code=<code>`, or `error=<provider error code>` when the provider refused. Always answers with a redirect to the frontend; a failed login lands on `/login?error=sso_failed` or a more specific code (`sso_email_missing`, `sso_email_unverified`, `sso_link_by_email_disabled`, `sso_approval_pending` or `sso_account_disabled`), see [SSO failures](oauth-sso-pkce.md#sso-failures) | 10 requests/min per IP |
| **Token Exchange (PKCE)** | `POST /auth/sessions/{session_id}/tokens` | Header: `X-Client-Type` (`web` or `mobile`), which must match the client type stored on the PKCE/OAuth state; JSON: `{"code_verifier": "<verifier>"}` (mobile password sign-in or SSO), plus `mfa_code` for an SSO session of an account with MFA. Answers the `tokens` body of the client type | 10 requests/min |
| **Start IdP Link** | `POST /profile/identity-providers/{idp_id}/link` | Requires authenticated session and a `step_up` object in the JSON body: `current_password` for local-password accounts, `idp_reauth` for accounts without one, and `mfa_code` when MFA is enabled; plus an optional `redirect` (relative frontend path). Returns `authorization_url` and sets the `endurain_idp_binding` cookie. The browser then navigates to `authorization_url`. `409` if already linked | 10 requests/min |
| **Start IdP Step-up** | `/profile/identity-providers/{idp_id}/step-up` | Requires authenticated session. JSON: `code_challenge`, `action`, `redirect` (relative path). Returns `authorization_url` and sets the `endurain_idp_binding` cookie. See [Account security](account-security.md#step-up-for-accounts-without-a-password) | 10 requests/min |

### Session Management Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Get Own Sessions** | `/profile/sessions` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `profile:security` scope. Paged like the admin list |
| **Delete Own Session** | `/profile/sessions/{session_id}` | Same headers and scope; web clients must also include `X-CSRF-Token` |
| **Delete Own Other Sessions** | `/profile/sessions` (`DELETE`) | Same headers and scope; ends every session except the current one |
| **Get User Sessions (admin)** | `/users/{user_id}/sessions` | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:read` scope. Paged: optional `page_number` (default 1) and `num_records` (default 25, maximum 200); the response is `{items, total, page, num_records, next}` |
| **Revoke Session (admin)** | `/users/{user_id}/sessions/{session_id}/revoke` (`POST`) | Headers: `Authorization: Bearer <Access Token>`, `X-Client-Type`; requires `sessions:write` scope; web clients must also include `X-CSRF-Token`. Body: the administrator's [step-up](account-security.md#step-up-request-body); answers `204` |
| **Revoke User Sessions (admin)** | `/users/{user_id}/sessions/revoke` (`POST`) | Same headers, scope and body; optional `exclude_session_id` query parameter keeps that session; ends every other session of the user; answers `204` |

### API Key Management Endpoints

Require JWT authentication with the standard `X-Client-Type` requirement; state-changing web requests must include `X-CSRF-Token`. API keys cannot manage other API keys.

<!-- generated:api-key-endpoints -->

### Example Resource Endpoints

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Activity Upload** | `POST /activities/upload` | .gpx, .tcx, .gz or .fit file. Accepts JWT **or** API key (`X-API-Key` header, or `?api_key=` query param only when `ALLOW_API_KEY_QUERY_PARAM=true`) with `activities:upload` scope. Answers `202` with an ingestion job. This unified-auth endpoint does not require `X-Client-Type` |
| **Ingestion Job** | `GET /activities/ingestion-jobs/{job_id}` | Poll the job returned by the upload. Accepts JWT or API key with the `activities:upload` scope |
| **Set Weight** | `/health/weight` | JSON `{'weight': <number>, 'created_at': 'yyyy-MM-dd'}` |

