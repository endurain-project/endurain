# OAuth/SSO and PKCE

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
Identity providers are configured by an administrator with these parameters:

- `name`, `slug` and `provider_type` (`oidc` by default)
- `client_id` and `client_secret`: OAuth client identifier and secret
- `issuer_url`: the OIDC issuer. Endurain reads `{issuer_url}/.well-known/openid-configuration` and requires its `issuer` to match. An `oidc` provider needs it: sign-in verifies the ID token against the issuer and the signing keys (`jwks_uri`) the discovery document publishes, and a provider without them is refused. Step-up re-authentication also needs it
- `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`: optional. A blank endpoint is discovered from the issuer; a value set here takes precedence
- `scopes`: `openid profile email` by default

The callback URL is not a setting. Endurain always uses `{frontend host}/api/v1/public/idp/callback/{idp_slug}`, so register exactly that URL as the redirect URI at the provider.

### SSO failures
The callback always ends in a redirect, never a JSON error, once its state is accepted. When a login fails, the browser lands on the Endurain frontend at `/login?error=<code>`: `sso_email_missing` when the provider did not share an email address for a new account, and `sso_failed` for every other failure (the provider refused the code or answered with an error, or the account could not be created). A failed link returns to the page that started it (`/settings/security` by default) with `idp_link=error`. A failed step-up returns to its `redirect` with `#step_up_error=failed|not_fresh` in the fragment. An unknown, expired, reused or wrong-provider `state` is refused before that with `400`.

### Linking Accounts
Users can link their Endurain account to an OAuth provider:

1. User must be authenticated with a valid session
2. Start the link with `POST /profile/identity-providers/{idp_id}/link`. The body carries a `step_up` object: local-password accounts must include `step_up.current_password`; accounts without one must include `step_up.idp_reauth` ([step-up](account-security.md#step-up-for-accounts-without-a-password)); accounts with MFA enabled must also include `step_up.mfa_code`. An optional `redirect` is the relative frontend path to return to. The response carries `authorization_url` and sets the `endurain_idp_binding` cookie that binds the link to this browser, so send the request with credentials.
3. Navigate the browser to `authorization_url`
4. Authenticate with the identity provider
5. Provider is linked to the existing account

!!! warning "Breaking change"
    The one-time link-token route (`.../link/token`) and the unauthenticated browser `GET` of the link route that took `link_token` are removed. No credential travels in a URL any more; the flow starts from the authenticated `POST` above.

### Step-up re-authentication
An account without a local password proves a sensitive change by signing in again with a linked provider. `POST /profile/identity-providers/{idp_id}/step-up` takes `code_challenge`, `action` and a relative `redirect`, and returns an `authorization_url`. The authorize request carries `prompt=login`, `max_age=60` and PKCE, and the callback requires an ID token whose `auth_time` is recent. It returns to `redirect` with `#step_up_ticket=...` or `#step_up_error=failed|not_fresh` in the fragment. The flow is in [Account security](account-security.md#step-up-for-accounts-without-a-password). It needs a provider with an issuer URL and does not work for native clients.

ID tokens are checked for `azp` and allow 60 seconds of clock leeway.

### Signing out of the provider

Ending an SSO session at Endurain does not sign the user out of the identity provider, so the provider's next "Sign in" would sign them straight back in. Endurain keeps the ID token the provider issued at each SSO sign-in, encrypted, and `POST /auth/logout` answers `idp_logout_url`, the provider's `end_session_endpoint` (from its discovery document) with `id_token_hint`, `client_id` and, for a web client, `post_logout_redirect_uri` set to `<ENDURAIN_HOST>/login`. A web client navigates the browser to it; a mobile client may open it in the system browser. The URL is `null` when the provider has no `end_session_endpoint` or the session did not sign in through a provider. See [Logout](authentication.md#logout).

### OAuth Token Response
When authenticating via OAuth, the response format matches the standard authentication:

- **Web clients**: Redirected to the frontend with a `session_id`; the frontend exchanges the session and receives the access token + CSRF token in the response body, while the refresh token is set as an httpOnly cookie
- **Mobile clients**: Redirected or deep-linked with a `session_id`; the app exchanges the session and receives access + refresh tokens in the response body

!!! info "Mobile OAuth/SSO"
  OAuth/SSO login requires PKCE for all clients. Mobile apps must use the system browser (`ASWebAuthenticationSession` or Custom Tabs), never an embedded WebView, so provider credentials stay outside the app process.

## Mobile Password Login with PKCE

### Overview

A mobile app signs in with a password through PKCE (Proof Key for Code Exchange, RFC 7636), so the tokens are never part of a login response. The flow mirrors the OAuth/SSO PKCE flow for local password authentication, and it is the only way a mobile client signs in with a password: `POST /auth/login` never answers a mobile client with tokens. A web client does not use PKCE: it gets its refresh token as an `HttpOnly` cookie, and `POST /auth/login` refuses `code_challenge` and `code_challenge_method` from it with `422`.

| Mobile password sign-in |
| ----------------------- |
| The login answers only a `session_id` |
| The app exchanges it with the PKCE verifier it kept |
| No token is in the login response |
| A stolen `session_id` is useless without the verifier |

### Step-by-Step PKCE Password Implementation

#### Step 1: Generate PKCE Code Verifier and Challenge

Before sending credentials, generate a cryptographically random code verifier and compute its SHA256 challenge (same as [Mobile SSO with PKCE](#step-1-generate-pkce-code-verifier-and-challenge)):

```
code_challenge = BASE64URL(SHA256(code_verifier))
```

#### Step 2: Send Login Request with PKCE Fields

Include the code challenge in the login form:

**Login Request:**

```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded
X-Client-Type: mobile

username=user@example.com&password=userpassword&code_challenge={challenge}&code_challenge_method=S256
```

**Form Fields:**

| Field | Required | Description |
| ----- | -------- | ----------- |
| `username` | Yes | Username or email |
| `password` | Yes | User's password |
| `code_challenge` | Yes (mobile) | Base64url-encoded SHA256 hash of code_verifier, 43 to 128 characters of `A-Z a-z 0-9 - _` |
| `code_challenge_method` | Yes (mobile) | Must be `S256` |

A missing, malformed or (for a web client) present PKCE field is `422` with the field named in `errors`, and the password is not checked.

**Successful Response (HTTP 200):**

A session_id to exchange for tokens:

```json
{
  "next_step": "exchange",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "<device id to send as X-Device-Id on later sign-ins>"
}
```

#### Step 3: Exchange Session for Tokens (PKCE Verification)

Use the code verifier to securely exchange the session for tokens:

**Token Exchange Request:**

```http
POST /api/v1/auth/sessions/{session_id}/tokens
Content-Type: application/json
X-Client-Type: mobile

{
  "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
}
```

**Successful Response (HTTP 200):**

```json
{
  "next_step": "tokens",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 900,
  "refresh_token_expires_in": 604800,
  "token_type": "bearer",
  "device_id": null
}
```

This is the mobile token body that `/auth/refresh` answers. Send the device id the app already holds as the `X-Device-Id` header on the exchange of an identity-provider sign-in. `device_id` in the response is the id the app must keep and send on later sign-ins; it is `null` for the exchange of a password sign-in, whose `session_id` response already carried it. See [Authentication](authentication.md#token-delivery-by-client-type).

**Error Responses:**

| Status | Error | Description |
| ------ | ----- | ----------- |
| 400 | Invalid code_verifier | Verifier doesn't match the challenge, or `X-Client-Type` differs from the client type that started the sign-in (the same answer for both) |
| 404 | Session not found | Invalid session_id |
| 409 | Tokens already exchanged | Replay attack prevention |
| 422 | Missing or unknown `X-Client-Type` | The header is required |
| 429 | Rate limit exceeded | Max 10 requests/minute per IP |

#### Step 4: Store Tokens Securely

Store the received tokens in secure platform storage:

- **iOS**: Keychain Services
- **Android**: EncryptedSharedPreferences or Android Keystore

#### Step 5: Use Tokens for API Requests

Use the tokens for authenticated API calls (same as [Mobile SSO with PKCE](#step-6-use-tokens-for-api-requests)).

### With MFA Enabled

If the user has MFA enabled, the flow includes an additional MFA verification step:

1. Client sends login with the PKCE fields
2. Backend returns `"next_step": "mfa"` with an `mfa_challenge` that names this login. The challenge records the client type and the PKCE challenge of the password step
3. Client collects MFA code from user
4. Client sends the `mfa_challenge` and the MFA code to `/auth/mfa/verify`. The request carries no PKCE values, and its `X-Client-Type` must be the one of the password step: a challenge presented by the other client type is refused exactly like an unknown one
5. Backend verifies MFA and returns `next_step: "exchange"` with a session_id. For an account whose password an administrator set, it returns `next_step: "password_change"` first; the PKCE values are kept with that step, so `/auth/password-change` takes no PKCE values and answers `exchange` too (see [Password change at sign-in](authentication.md#password-change-at-sign-in))
6. Client exchanges session_id for tokens using code_verifier

**MFA Verification:**

```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
X-Client-Type: mobile

{
  "mfa_challenge": "<mfa_challenge from the login response>",
  "mfa_code": "123456"
}
```

**Response (Session ID for Exchange):**

```json
{
  "next_step": "exchange",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_id": "<device id to send as X-Device-Id on later sign-ins>"
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
| **Client type binding** | The MFA step and the exchange refuse a client type other than the one that started the sign-in |

## Mobile SSO with PKCE

### Overview
PKCE (Proof Key for Code Exchange, RFC 7636) is required for OAuth/SSO authentication. Mobile apps must sign in through the **system browser** (`ASWebAuthenticationSession` on iOS, Custom Tabs on Android), as [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252) requires. Do not load the identity provider in an embedded WebView: the app could read the user's credentials, the user cannot check the address bar, and some providers (Google, for one) refuse it. The system browser returns the app a `session_id` through a deep link, and the app exchanges it for tokens with its PKCE verifier.

### Why Use PKCE?

| Without PKCE | PKCE Flow |
| ------------ | --------- |
| A stolen `session_id` could be exchanged by anyone | Only the client that holds the verifier can exchange it |
| Tokens would have to reach the app through the browser | Tokens are delivered by an API call from the app |
| Authorization codes can be intercepted by other apps | An intercepted code or `session_id` is useless without the verifier |

### Flow Overview

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Mobile App │     │ Endurain Backend│     │System Browser│     │     IdP     │
└──────┬──────┘     └────────┬────────┘     └──────┬───────┘     └──────┬──────┘
       │                     │                     │                    │
       │ 1. Generate PKCE    │                     │                    │
       │    verifier+challenge                     │                    │
       │                     │                     │                    │
       │ 2. Open system browser to:                │                    │
       │    /public/idp/login/{slug}               │                    │
       │    ?code_challenge=X                      │                    │
       │    &redirect={custom_scheme}://callback   │                    │
       │──────────────────────────────────────────>│                    │
       │                     │ 3. Validate redirect, store state        │
       │                     │<────────────────────│                    │
       │                     │     Redirect to IdP │                    │
       │                     │─────────────────────────────────────────>│
       │                     │                     │   User logs in     │
       │                     │                     │<──────────────────>│
       │                     │   code + state      │                    │
       │                     │<─────────────────────────────────────────│
       │                     │ 4. Redirect to frontend:                 │
       │                     │    /login?sso=success&session_id=UUID    │
       │                     │    &redirect={custom_scheme}://callback  │
       │                     │    &external_redirect=true               │
       │                     │────────────────────>│                    │
       │                     │                     │ 5. Frontend forwards to
       │                     │                     │    {custom_scheme}://callback
       │                     │                     │    ?session_id=UUID
       │ Deep link received  │                     │                    │
       │<──────────────────────────────────────────│                    │
       │ 6. POST token exchange with own verifier  │                    │
       │────────────────────>│                     │                    │
       │    JWT tokens       │                     │                    │
       │<────────────────────│                     │                    │
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

#### Step 2: Open the System Browser

Open the initiate URL in the system browser, with the app's custom scheme as `redirect`:

```http
https://your-endurain-instance.com/api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect={custom_scheme}://callback
```

**Query Parameters:**

| Parameter | Required | Description |
| --------- | -------- | ----------- |
| `code_challenge` | Yes (PKCE) | Base64url-encoded SHA256 hash of code_verifier |
| `code_challenge_method` | Yes (PKCE) | Must be `S256` |
| `redirect` | Yes for mobile | The app's custom-scheme URL, for example `org.endurain.app://callback`. The scheme must be allowed by the administrator (see [Redirect schemes](#redirect-schemes)) |

!!! note "What marks the flow as mobile"
    A browser cannot attach custom headers, so Endurain decides the client type from the `redirect`: a validated custom-scheme redirect always records the flow as `mobile`, whatever `X-Client-Type` says. Without a custom-scheme redirect the backend uses the `X-Client-Type` header (`web` or `mobile`) and falls back to `web` when it is absent or invalid. An app that sends the request itself may still include `X-Client-Type: mobile`.

#### Step 3: Receive the Deep Link

The user signs in with the identity provider in the system browser. On success the backend redirects to the Endurain frontend with `external_redirect=true`, and the frontend forwards the browser to:

```
{custom_scheme}://callback?session_id={uuid}
```

The OS invokes the app's deep-link or intent handler with that URL. Extract the `session_id`.

On failure the browser stays on the Endurain login page with an `error` query parameter (`sso_failed`, or `sso_email_missing` when the provider shared no email address for a new account). The app receives no deep link, so it must also handle the user closing the browser or a timeout. The state expires after 10 minutes.

#### Step 4: Exchange Session for Tokens (PKCE Verification)

After obtaining the `session_id`, exchange it for tokens using the code verifier:

**Token Exchange Request:**

```http
POST /api/v1/auth/sessions/{session_id}/tokens
Content-Type: application/json
X-Client-Type: mobile

{
  "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
}
```

**Successful Response (HTTP 200):**

```json
{
  "next_step": "tokens",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 900,
  "refresh_token_expires_in": 604800,
  "token_type": "bearer",
  "device_id": "q3k9...43 characters"
}
```

A web client gets the web token body instead (`csrf_token`, no `refresh_token`, the refresh token as a cookie), the same as `/auth/login` answers.

`device_id` is the id a mobile app keeps and sends as `X-Device-Id`; the exchange of an identity-provider sign-in sets it, and a password sign-in already returned it with its `session_id` (it is `null` in that exchange).

**Error Responses:**

| Status | Error | Description |
| ------ | ----- | ----------- |
| 400 | Invalid code_verifier | Verifier doesn't match the challenge, or `X-Client-Type` differs from the value stored on the PKCE/OAuth state (the same answer for both) |
| 404 | Session not found | Invalid session_id or not a PKCE flow |
| 422 | Missing or unknown `X-Client-Type` | The header is required |
| 403 | `mfa-required` | The account has MFA enabled and the request had no `mfa_code`; see below |
| 400 | Invalid MFA code | The `mfa_code` was wrong, expired or an already used backup code |
| 409 | Tokens already exchanged | Replay attack prevention |
| 429 | Rate limit exceeded | Max 10 requests/minute per IP, or the account is locked out after too many wrong MFA codes |

**Accounts with MFA enabled:** signing in with an identity provider does not replace the account's own MFA. When the account has MFA enabled, the exchange is refused with `403` and the problem type `urn:endurain:error:mfa-required` until the request also carries `"mfa_code"` (a TOTP code or a backup code). The refusal does not use up the session: ask the user for a code and send the same request again with it. The verifier is checked first, so only the client that started the flow can try codes, and wrong codes count toward the same lockout as the password login.

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

### Redirect schemes

The `redirect` scheme must be listed in `ALLOWED_REDIRECT_SCHEMES` (see [Configuration](auth-reference.md#configuration)). It is a comma-separated list, matched case-insensitively. The default is `endurain` only, and setting the variable replaces the default instead of adding to it. An operator who runs an app that uses another scheme must set it, for example `ALLOWED_REDIRECT_SCHEMES=org.endurain.app`, and restart Endurain. A redirect with a scheme that is not listed is refused with `400`.

App authors should register a reverse-DNS scheme based on a domain they control, such as `org.endurain.app`, as RFC 8252 section 7.1 recommends. A short word such as `endurain` or `gadgetbridge` can be claimed by any other app on the device, which could then receive the `session_id` (the PKCE verifier still stops it from getting tokens). `http`, `https`, `javascript`, `data`, `file`, `vbscript` and `blob` are never allowed, and Endurain refuses to start if one is listed.

#### Redirect URL Validation Rules

| Redirect value | Allowed | Notes |
| -------------- | ------- | ----- |
| `/dashboard` | ✅ | Relative paths always allowed |
| `/settings?tab=devices` | ✅ | Query strings OK in relative paths |
| `org.endurain.app://callback` | ✅ | If `org.endurain.app` is in `ALLOWED_REDIRECT_SCHEMES`; recorded as a mobile flow |
| `myapp://callback` | ❌ | If `myapp` is not configured — 400 returned |
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

