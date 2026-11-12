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

- `name`, `slug` and `provider_type`. The slug is 1 to 50 lowercase letters, numbers and hyphens, and cannot be `login`, `callback`, `icon` or `backchannel-logout`, the words the public routes use (refused with `422`). `provider_type` is `oidc` (the default) or `oauth2`; any other value, including `saml`, is refused with `422`. An `oauth2` provider whose `scopes` include `openid` (the default scopes do) must return an ID token that verifies, nonce included, like an `oidc` one
- `client_id` and `client_secret`: OAuth client identifier and secret
- `issuer_url`: the OIDC issuer. Endurain reads `{issuer_url}/.well-known/openid-configuration` and requires its `issuer` to match. An `oidc` provider needs it, and creating one without it is refused with `422`; an edit that would leave one without it is refused with `400`. Sign-in verifies the ID token against the issuer and the signing keys the discovery document publishes (`jwks_uri` in that document), and a provider without them is refused. Step-up re-authentication also needs it
- `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`: optional. A blank endpoint is discovered from the issuer; a value set here takes precedence
- `scopes`: `openid profile email` by default. An `oidc` provider must include `openid`; creating one without it is refused with `422`, and an edit that would remove it is refused with `400`. An edit is checked against the stored values of the fields it does not send, and one that leaves `provider_type`, `issuer_url` and `scopes` equal to the stored values, whether it omits them or sends them back unchanged, is not checked, so a provider saved before this rule can still be renamed or disabled
- `auto_create_users` (`true` by default), `link_by_email` (`false` by default), `sync_user_info` (`true` by default) and `sync_email` (`false` by default). `link_by_email` lets an unlinked sign-in join the local account that has the provider's verified email; when it is `false` that sign-in is refused. `sync_user_info` syncs the mapped name and not the email; `sync_email` syncs the email the provider verified, which marks it verified, voids unused password-reset tokens, is audited and notifies the previous address
- `enabled`: setting it from `true` to `false` ends, in the same transaction as the edit, every session the provider signed in, for all users; the `auth.identity_provider.update` audit row carries the number as `sessions_ended`. Setting it back to `true` does not restore them. If ending the sessions fails, the provider stays enabled

!!! warning "Breaking change"
    The `jwks_uri` field is removed from the identity provider request and response bodies and from the database. Signing keys always come from the provider's discovery document, so a body that still sends `jwks_uri` is refused with `422`. Creating an `oidc` provider without an `issuer_url` or without the `openid` scope is refused too.

The callback URL is not a setting. Endurain always uses `{frontend host}/api/v1/public/idp/callback/{idp_slug}`, so register exactly that URL as the redirect URI at the provider.

### SSO failures
The callback always ends in a redirect, never a JSON error, once its state is accepted. When a login fails, the browser lands on the Endurain frontend at `/login?error=<code>`, or, when the sign-in started with a native-app `redirect`, on that address with `error=<code>` in its query (the same codes): `sso_email_missing` when the provider did not share an email address for a new account, `sso_email_unverified` when the server requires a verified address for a new account and the provider did not verify it, `sso_auto_create_disabled` when no account matches and the server or the provider does not allow creating one, `sso_link_by_email_disabled` when an account has the provider's email and the provider does not link by email, `sso_approval_pending` when the account waits for an administrator's approval, `sso_account_disabled` when the account is otherwise inactive (deactivated or queued for deletion), and `sso_failed` for every other failure (the provider refused the code or answered with an error, or the account could not be created). A failed link returns to the page that started it (`/settings/security` by default) with `idp_link=error`. A failed step-up returns to its `redirect` with `#step_up_error=failed|not_fresh` in the fragment. An unknown, expired, reused or wrong-provider `state`, or a login finished in a browser other than the one that started it, is refused before that with `400`. That refusal, and a provider that does not exist or is disabled, happens before the native `redirect` is known, so it is a plain error response in the browser and never reaches the app.

### Linking Accounts
Users can link their Endurain account to an OAuth provider:

1. User must be authenticated with a valid session
2. Start the link with `POST /profile/identity-providers/{idp_id}/link`. The body carries a `step_up` object: local-password accounts must include `step_up.current_password`; accounts without one must include `step_up.idp_reauth` ([step-up](account-security.md#step-up-for-accounts-without-a-password)); accounts with MFA enabled must also include `step_up.mfa_code`. An optional `redirect` is where to return to: a relative frontend path, or a native address listed in `ALLOWED_REDIRECT_URIS`. An optional `revoke_other_sessions` (default `true`) ends the account's other sessions when the link completes, keeping the session that started it; send `false` to keep them. The session that started the link and the choice are stored with the link's OAuth state, because the callback runs without the caller's session. The response carries `authorization_url` and sets the `endurain_idp_binding` cookie that binds the link to this browser, so send the request with credentials.
3. Navigate the browser to `authorization_url`
4. Authenticate with the identity provider
5. Provider is linked to the existing account, and the other sessions end unless the start request sent `revoke_other_sessions: false`; the ended sessions are audited as `auth.session.revoke`. The callback refuses, and links nothing, when the account was deactivated, the session that started the link ended, or a security change (a password or MFA change, a sign-out everywhere) came after the start; the browser returns with `idp_link=error` and the refusal is audited as `auth.identity_link.link` with the reason `user_inactive`, `session_ended` or `security_changed`

!!! warning "Breaking change"
    The one-time link-token route (`.../link/token`) and the unauthenticated browser `GET` of the link route that took `link_token` are removed. No credential travels in a URL any more; the flow starts from the authenticated `POST` above.

### Step-up re-authentication
An account without a local password proves a sensitive change by signing in again with a linked provider. `POST /profile/identity-providers/{idp_id}/step-up` takes `code_challenge`, `action` and a relative `redirect`, and returns an `authorization_url`. The authorize request carries `prompt=login`, `max_age=60` and PKCE, and the callback requires an ID token whose `auth_time` is recent. It returns to `redirect` with `#step_up_ticket=...` or `#step_up_error=failed|not_fresh` in the fragment. The flow is in [Account security](account-security.md#step-up-for-accounts-without-a-password). It needs a provider with an issuer URL and does not work for native clients.

ID tokens are checked for `azp` and allow 60 seconds of clock leeway.

### Signing out of the provider

Ending an SSO session at Endurain does not sign the user out of the identity provider, so the provider's next "Sign in" would sign them straight back in. Endurain keeps the ID token the provider issued at each SSO sign-in, encrypted, and `POST /auth/logout` answers `idp_logout_url`, the provider's `end_session_endpoint` (from its discovery document) with `id_token_hint`, `client_id` and, for a web client, `post_logout_redirect_uri` set to `<ENDURAIN_HOST>/login`. A web client navigates the browser to it; a mobile client may open it in the system browser. The URL is `null` when the provider has no `end_session_endpoint` or the session did not sign in through a provider. See [Logout](authentication.md#logout).

### Provider-initiated sign-out

The reverse direction is the provider's to start. When the provider supports [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html) and the administrator registered `<ENDURAIN_HOST>/api/v1/public/idp/{slug}/backchannel-logout` there, signing out at the provider posts a signed logout token to that URL and Endurain ends the sessions it names: those signed in under its `sid` (only the named user's when it also names a `sub`), or, with only a `sub`, every session the user signed in to through that provider. A client learns of it the way it learns of any ended session: its next request or refresh is `401`. A client never calls this endpoint itself. See [Signing out at the provider](../features/single-sign-on.md#signing-out-at-the-provider).

### OAuth Token Response
When authenticating via OAuth, the response format matches the standard authentication:

- **Web clients**: Redirected to the frontend with a `session_id`; the frontend exchanges the session and receives the access token + CSRF token in the response body, while the refresh token is set as an httpOnly cookie
- **Mobile clients**: Redirected or deep-linked with a `session_id`; the app exchanges the session and receives access + refresh tokens in the response body

The session belongs to the client type recorded when the sign-in started. Its tokens carry it as `client_id`, and `/auth/refresh` refuses a refresh that declares a different `X-Client-Type` (see [Token Refresh Flow](authentication.md#token-refresh-flow)).

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

username=username&password=userpassword&code_challenge={challenge}&code_challenge_method=S256
```

**Form Fields:**

| Field | Required | Description |
| ----- | -------- | ----------- |
| `username` | Yes | The account username (case-insensitive). An email address is not accepted: it is refused like a wrong password and counts toward the failed-login lockout |
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
| 400 | `invalid-input` (Invalid code_verifier) | Verifier doesn't match the challenge, or `X-Client-Type` differs from the client type that started the sign-in (the same answer for both) |
| 404 | Session not found | Invalid session_id, or the tokens were already exchanged |
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
| **PKCE S256** | A `session_id` that leaks on its own (a log or a proxy, for example) cannot be exchanged without the verifier. The sign-in returns the `session_id` in the same HTTPS response that accepted the challenge, so there is no redirect to intercept, and whoever knows the password chooses the challenge: PKCE does not stop an attacker who has the password |
| **One-time exchange** | Tokens can only be exchanged once per session |
| **10-minute exchange window** | The PKCE/OAuth state expires after 10 minutes; the pending session cannot be exchanged after that window |
| **Rate limiting** | 10 token exchange requests per minute |
| **Session binding** | The pending session is tied to the PKCE challenge of its sign-in; the exchange checks no IP address, device or app identity |
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
- Characters accepted by Endurain: `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`, the unreserved characters of RFC 7636 section 4.1
- Cryptographically random

**Code Challenge Computation:**

```
code_challenge = BASE64URL(SHA256(code_verifier))
```

#### Step 2: Open the System Browser

Open the initiate URL in the system browser, with the app's redirect address as `redirect`:

```http
https://your-endurain-instance.com/api/v1/public/idp/login/{idp_slug}?code_challenge={challenge}&code_challenge_method=S256&redirect={custom_scheme}://callback
```

The route answers `307` to the identity provider and sets an httpOnly cookie (`endurain_idp_binding`, `__Host-endurain_idp_binding` in production and demo, `SameSite=Lax`, path `/`, valid for the 10 minutes the OAuth state lives) that binds the sign-in to this browser. The callback refuses a sign-in that finishes in another browser or without the cookie, with the same `400` as an unknown `state`, and audits it as `auth.session.login` with the reason `browser_mismatch`. Open the URL in a browser that keeps cookies and finish the whole flow in that same browser: the system browser, Custom Tabs or `ASWebAuthenticationSession`. A WebView that drops cookies, or a flow that moves from one browser to another, cannot finish. The provider's callback always goes to `ENDURAIN_HOST`, so the app must start the login on the `ENDURAIN_HOST` origin, not a LAN IP or another host name, and over `https` in production and demo, where the cookie is `Secure` and a browser drops it over plain `http`. Otherwise the callback is refused as an unknown `state`.

**Query Parameters:**

| Parameter | Required | Description |
| --------- | -------- | ----------- |
| `code_challenge` | Yes (PKCE) | Base64url-encoded SHA256 hash of code_verifier |
| `code_challenge_method` | Yes (PKCE) | Must be `S256` |
| `redirect` | Yes for mobile | The app's callback address, a custom-scheme URL such as `org.endurain.app://callback` or a claimed `https` address. The administrator must list it exactly (see [Redirect schemes](#redirect-schemes)) |

!!! note "What marks the flow as mobile"
    A browser cannot attach custom headers, so Endurain decides the client type from the `redirect` alone and never reads `X-Client-Type` on this route: a validated redirect with a scheme (custom scheme or claimed `https`) records the flow as `mobile`, and any other redirect, or none, records `web`.

#### Step 3: Receive the Deep Link

The user signs in with the identity provider in the system browser. On success the backend redirects to the Endurain frontend with `external_redirect=true`, and the frontend forwards the browser to:

```
{custom_scheme}://callback?session_id={uuid}
```

The OS invokes the app's deep-link or intent handler with that URL. Extract the `session_id`.

On failure the browser returns to the same `redirect` address with an `error` query parameter (`sso_failed`, `sso_email_missing`, `sso_email_unverified`, `sso_auto_create_disabled`, `sso_link_by_email_disabled`, `sso_approval_pending` or `sso_account_disabled`; see [SSO failures](#sso-failures)). The app must still handle the user closing the browser or a timeout. The state expires after 10 minutes.

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
| 400 | `invalid-input` (Invalid code_verifier) | Verifier doesn't match the challenge, or `X-Client-Type` differs from the value stored on the PKCE/OAuth state (the same answer for both) |
| 404 | Session not found | Invalid session_id, not a PKCE flow, or the tokens were already exchanged |
| 422 | Missing or unknown `X-Client-Type` | The header is required |
| 403 | `mfa-required` | The account has MFA enabled and the request had no `mfa_code`; see below |
| 400 | `invalid-mfa-code` | The `mfa_code` was wrong, expired or an already used backup code |
| 429 | Rate limit exceeded | Max 10 requests/minute per IP, or the account is locked out after too many wrong MFA codes |

**Accounts with MFA enabled:** signing in with an identity provider does not replace the account's own MFA. When the account has MFA enabled, the exchange is refused with `403` and the problem type `urn:endurain:error:mfa-required` until the request also carries `"mfa_code"` (a TOTP code or a backup code). The refusal does not use up the session: ask the user for a code and send the same request again with it. A later release may add members to this `403` (for example the factors on offer) and optional proof fields to the exchange body next to `mfa_code`; see [Compatibility between releases](compatibility.md#responses-gain-members). Ignore a member you do not know, and send only the fields described here. The verifier is checked first, so only the client that started the flow can try codes, and wrong codes count toward the same lockout as the password login.

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

The `redirect` address must be listed in `ALLOWED_REDIRECT_URIS` (see [Configuration](auth-reference.md#configuration)), a comma-separated list of exact addresses. It is the only redirect allow-list: `ALLOWED_REDIRECT_SCHEMES` is removed and Endurain refuses to start while it is set. Relative paths need no entry. The default is `com.endurain.endurain:/auth/sso/callback`; setting the variable replaces it, so keep it in the list, for example `ALLOWED_REDIRECT_URIS=com.endurain.endurain:/auth/sso/callback,nodomain.freeyourgadget.gadgetbridge://endurain/oauth/callback` to allow Gadgetbridge as well.

!!! warning "Breaking change for operators"
    The current Endurain mobile app still sends `endurain://auth/sso/callback`, which is no longer in the default. Until an app release uses the new address, add `endurain://auth/sso/callback` to `ALLOWED_REDIRECT_URIS` to keep SSO in the app working, for example `ALLOWED_REDIRECT_URIS=com.endurain.endurain:/auth/sso/callback,endurain://auth/sso/callback`. An operator who set `ALLOWED_REDIRECT_SCHEMES` must replace it with the exact addresses of the apps they allow.

As in RFC 3986, the scheme ends at the first `:` and the `//` after it is optional, so both `org.endurain.app:/oauth/callback` (the form RFC 8252 section 7.1 shows) and `org.endurain.app://oauth/callback` work. The scheme is matched case-insensitively and the rest of the address exactly. The app registers one fixed callback address and Endurain adds `session_id` to it, so a redirect with a different path, or with a query string or fragment the entry does not have, is refused with `400`.

An entry may also be an exact `https://host/path` address, an Android App Link or iOS Universal Link. Endurain treats it like a custom-scheme address: it is a native-app address, the flow is recorded as `mobile`, and `session_id` is added to it. An `https` entry needs a host, no user info (`user@`), a valid port, and no whitespace or backslash; otherwise startup fails. An `https` redirect that is not listed is refused, like any other unlisted address. `http` is never allowed, and neither are `javascript`, `data`, `file`, `vbscript` and `blob`; Endurain refuses to start if one is listed.

#### Choosing the redirect address

Any app on a device can register a custom scheme (RFC 8252 section 8.6), so an app that claims the scheme of a listed address also receives the `session_id` in the deep link. The PKCE verifier protects only a flow the legitimate app started. An app that starts the login itself, with its own verifier, and receives the `session_id` can exchange it for tokens. Endurain cannot tell the two apps apart.

- Prefer a claimed `https` address where the platform supports it. The operating system verifies the app against the domain, so another app cannot receive the link. The app side needs a hosted `/.well-known/assetlinks.json` (Android App Links) or `apple-app-site-association` file (iOS Universal Links) on the domain. A reliable `https` callback also needs the app to open the login with `ASWebAuthenticationSession` on iOS, or an Auth Tab or Custom Tab on Android. Endurain hosts neither file for you.
- If you use a custom scheme, use a reverse-DNS scheme based on a domain you control, such as `org.endurain.app`, as RFC 8252 section 7.1 recommends. This reduces accidental collisions only; it does not stop an app that registers the same scheme on purpose. A short word such as `endurain` or `gadgetbridge` is easier to collide with.
- Operators list only addresses of apps they trust with the whole account. An app listed in `ALLOWED_REDIRECT_URIS` receives tokens with every scope the signing-in user holds, administrator scopes included, because a redirect address selects the app, not a narrower set of scopes.

#### The app a session belongs to

When the SSO callback creates a session for a native-app `redirect`, the session records that address. `GET /profile/sessions` and the administrator's `GET /users/{user_id}/sessions` return it as `app_redirect_uri`, a read-only string that is `null` for a web session, for a mobile session signed in with a password or PKCE token exchange without SSO, and for a session created before it was recorded. A refresh keeps the value for the life of the session. No request accepts the field; the server sets it. The user and an administrator can use it to tell apart the sessions held by different apps.

#### Redirect URL Validation Rules

| Redirect value | Allowed | Notes |
| -------------- | ------- | ----- |
| `/dashboard` | ✅ | Relative paths always allowed |
| `/settings?tab=devices` | ✅ | Query strings OK in relative paths |
| `org.endurain.app:/callback` | ✅ | If it is listed in `ALLOWED_REDIRECT_URIS`; recorded as a mobile flow |
| `org.endurain.app://callback` | ✅ | If it is listed in `ALLOWED_REDIRECT_URIS`; recorded as a mobile flow |
| `https://app.example.com/endurain/callback` | ✅ | Only if that exact address is listed in `ALLOWED_REDIRECT_URIS`; recorded as a mobile flow |
| `myapp://callback` | ❌ | The address is not listed in `ALLOWED_REDIRECT_URIS` — 400 returned |
| `https://evil.com` | ❌ | An `https` address that is not listed is rejected |
| `http://localhost` | ❌ | `http` is always rejected |
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

