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
administrator via `ALLOWED_REDIRECT_SCHEMES` (see [Configuration](auth-reference.md#configuration)).

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

