# Account security

## Step-up Authentication

Certain sensitive account operations require the user to re-prove possession of their credentials even when they already hold a valid access token. This is called **step-up verification**.

### Operations That Require Step-up

| Operation | Endpoint |
| --------- | -------- |
| Change own password | `POST /profile/password/change` |
| Change own email | `POST /profile/email/change` |
| Enable MFA | `POST /profile/mfa/enable` |
| Disable MFA | `POST /profile/mfa/disable` |
| Regenerate MFA backup codes | `POST /profile/mfa/backup-codes` |
| Create API key | `POST /profile/api-keys` |
| Generate IdP link token | `POST /profile/identity-providers/{idp_id}/link/token` |
| Remove IdP link | `POST /profile/identity-providers/{idp_id}/unlink` |
| Delete own account | `POST /profile/delete-account` |

### Step-up Request Body

All step-up operations accept the following fields in their JSON request body (alongside any operation-specific fields):

| Field | Required | Description |
| ----- | -------- | ----------- |
| `current_password` | Conditionally | Required for accounts with a local password |
| `idp_reauth` | Conditionally | Required for accounts without a local password: `{"ticket": "...", "code_verifier": "..."}`, proof of a fresh sign-in with a linked identity provider. See [Step-up for accounts without a password](#step-up-for-accounts-without-a-password) |
| `mfa_code` | Conditionally | Required when MFA is enabled on the account. Accepts TOTP codes or backup codes |

**Example:**

```json
{
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

Account deletion and email change use the same fields. Password change (`POST /profile/password/change`) needs a local password and is answered `403` for an account without one; an administrator sets the first password through `POST /users/{user_id}/password/change`, which refuses the administrator's own account.

### Step-up for accounts without a password

An account without a local password cannot prove a password, and MFA alone does not pass step-up for it. It must prove a fresh sign-in with an identity provider linked to the account. This covers API key creation, IdP link token, IdP unlink, email change, account deletion, MFA enable, MFA disable and backup-code regeneration.

1. The sensitive request arrives without `idp_reauth`. The API answers `401` with problem type `urn:endurain:error:idp-reauth-required` and `WWW-Authenticate: Bearer error="insufficient_user_authentication", max_age="60"` ([RFC 9470](https://datatracker.ietf.org/doc/html/rfc9470)). A missing proof is not counted as a failed attempt.
2. The client generates a PKCE verifier and starts the sign-in with `POST /profile/identity-providers/{idp_id}/step-up`:

    ```json
    {
      "code_challenge": "<S256 challenge>",
      "action": "api_key_create",
      "redirect": "/settings?tab=security"
    }
    ```

    `action` is one of `api_key_create`, `idp_link`, `idp_unlink`, `email_change`, `account_delete`, `mfa_enable`, `mfa_disable`, `mfa_backup_codes`. `redirect` must be a relative path; other values, including custom schemes, are refused. The response is `{"authorization_url": "..."}` and sets the HttpOnly, `SameSite=Lax` cookie `endurain_idp_binding`, scoped to the callback path, which ties the flow to that browser.
3. The browser opens `authorization_url`. Endurain asks the provider for a new sign-in (`prompt=login`, `max_age=60`, PKCE). The callback verifies the ID token (signature, `iss`, `aud`, `azp`, `exp`/`iat` with 60 seconds of leeway, `nonce`) and requires `auth_time` to be no earlier than 60 seconds before the step-up started. The userinfo endpoint is not used, and the provider account must be the one linked to the user.
4. The callback redirects to `redirect` with the result in the URL fragment: `#step_up_ticket=<ticket>` on success, or `#step_up_error=failed` or `#step_up_error=not_fresh`. `not_fresh` means the provider did not make the user sign in again.
5. The client repeats the sensitive request with `idp_reauth`:

    ```json
    {
      "idp_reauth": { "ticket": "<ticket>", "code_verifier": "<PKCE verifier>" },
      "mfa_code": "123456"
    }
    ```

    `mfa_code` is also required when MFA is enabled. The ticket is single use, valid for 300 seconds, and bound to the user, the session, the action and the PKCE verifier. A wrong MFA code does not consume it.

Native and mobile clients cannot use this flow because the redirect must be a relative path, so they cannot step up an account without a password; the user does it in the web UI. Providers without an issuer URL (OAuth2 only) cannot do step-up. See [Single Sign-On](../features/single-sign-on.md#confirming-sensitive-changes-without-a-password).

### Step-up Lockout Policy

Failed step-up verifications are tracked per-user with progressive lockout, independent of login lockout counters:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 15 failures | 2 hours |

The lockout check happens **before** any password or MFA comparison, so the number of guesses is bounded even when an attacker has a valid access token.

**Lockout Response (HTTP 429):**

```json
{
  "detail": "Too many failed step-up attempts. Try again later."
}
```

The response also includes a `Retry-After` header indicating how many seconds remain before the lockout expires.

The counter resets automatically on a successful step-up verification.

## Email Change

`POST /profile/email/change` (step-up required) does not replace the account's address. It creates a pending change and answers `200` with the profile and its `ETag`: `pending_email` is set while the change awaits confirmation, and `email` already holds the new address when the server applied it at once (no outgoing mail). A later request replaces an earlier one. Entering the current address cancels the pending change. The request answers `409` when another account already uses the address. The address switches when the link emailed to the new address is confirmed through `POST /sign-up/confirm` (valid 24 hours). Confirmation answers `409` when another account has taken the address in the meantime, and then nothing changes. Until the change is confirmed, sign-in and password reset keep using the current address.

| What | URL | Method | Description |
| ---- | --- | ------ | ----------- |
| **Resend Confirmation** | `/profile/email/change/resend` | POST | Sends the confirmation for the pending address, at most once an hour. Requires scope `profile`, no step-up. Answers `204` whether or not an email was sent |
| **Cancel Pending Change** | `/profile/email/change` | DELETE | Cancels the pending change, so its confirmation link stops working. Requires scope `profile`, no step-up. Answers `204` |

The profile (`GET /profile`) and the admin user reads (`GET /users/{user_id}`) include `pending_email`, the address awaiting confirmation, and `pending_email_expires_at`, when its link expires. Both are `null` when no change is pending.

## Progressive Account Lockout

Endurain implements progressive brute-force protection to prevent credential stuffing attacks. Password login failures use this policy:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 20 failures | 24 hours |

MFA verification failures use a separate policy:

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 5 failures | 5 minutes |
| 10 failures | 30 minutes |
| 15 failures | 2 hours |

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

**Response (when MFA is enabled):** HTTP 200 OK for web and mobile clients. `mfa_challenge` names this login; send it with the code in step 2.

```json
{
  "mfa_required": true,
  "username": "example",
  "mfa_challenge": "<opaque challenge>",
  "message": "MFA verification required"
}
```

### Step 2: MFA Verification
Complete the login by providing the MFA code (TOTP or backup code) to `/auth/mfa/verify`:

**Request:**
```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
X-Client-Type: web|mobile

{
  "mfa_challenge": "<mfa_challenge from the login response>",
  "mfa_code": "123456"
}
```

!!! note "A TOTP code works once"
    The server accepts each authenticator code a single time. Submitting the same code again, on this endpoint or on any other that asks for an MFA code, fails like an invalid code until the next 30-second code appears.

!!! tip "Backup Code Format"
    Users can also use a backup code instead of a TOTP code. Backup codes are in `XXXX-XXXX` format (e.g., `A3K9-7BDF`). See [MFA Backup Codes](#mfa-backup-codes) for details.

**Response (successful verification):**

- **Web clients**: Access token and CSRF token in response body, refresh token as httpOnly cookie

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "csrf_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

- **Mobile clients**: All tokens returned in response body

```json
{
  "session_id": "unique_session_id",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token_expires_in": 604800
}
```

### Error Handling

The bodies below show only the `detail` member. Every error is an RFC 9457 problem document with more members (`type`, `title`, `status`, `request_id`); see [Errors, concurrency and rate limits](errors-and-limits.md).

- **No pending MFA login**: HTTP 400 Bad Request

```json
{
  "detail": "No pending MFA login found for this username"
}
```

- **Invalid MFA code**: HTTP 400 Bad Request

```json
{
  "detail": "Invalid MFA code, backup code or backup code already used."
}
```

- **Account locked out (too many failures)**: HTTP 429 Too Many Requests

```json
{
  "detail": "Too many failed MFA attempts. Account locked for 300 seconds."
}
```

### Important Notes
- The pending MFA login session is temporary and expires after 5 minutes
- After successful MFA verification, the pending login is automatically cleaned up
- The user must still be active at the time of MFA verification
- If no MFA is enabled for the user, the standard single-step authentication flow applies

## MFA Backup Codes

Backup codes provide a recovery mechanism when users lose access to their authenticator app. When MFA is enabled, users receive 10 one-time backup codes that can be used instead of TOTP codes.

### Backup Code Format

- Format: `XXXX-XXXX` (8 alphanumeric characters with hyphen)
- Example: `A3K9-7BDF`
- Characters: Uppercase letters and digits (excluding ambiguous: 0, O, 1, I)
- One-time use: Each code can only be used once

### When Backup Codes Are Generated

1. **Automatically on MFA Enable**: When a user enables MFA, 10 backup codes are generated and returned in the response
2. **Manual Regeneration**: Users can regenerate all backup codes via `POST /profile/mfa/backup-codes` (invalidates all previous codes). This endpoint requires step-up verification and MFA must already be enabled on the account.

### API Endpoints

| What | URL | Method | Description |
| ---- | --- | ------ | ----------- |
| **Get Backup Code Status** | `/profile/mfa/backup-codes/status` | GET | Returns count of unused/used codes |
| **Regenerate Backup Codes** | `/profile/mfa/backup-codes` | POST | Generates new codes (invalidates old). Requires step-up JSON body: `current_password` for local-password accounts, `idp_reauth` for accounts without one, and `mfa_code` when MFA is enabled |

### Regenerate Backup Codes Request

```http
POST /api/v1/profile/mfa/backup-codes
Authorization: Bearer {access_token}
X-Client-Type: web
X-CSRF-Token: {csrf_token}
Content-Type: application/json

{
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

Accounts without a local password send `idp_reauth` instead of `current_password`. If MFA is enabled, `mfa_code` is required.

### Backup Code Status Response

```json
{
  "has_codes": true,
  "total": 10,
  "unused": 8,
  "used": 2,
  "created_at": "2025-12-21T10:30:00Z"
}
```

### Regenerate Backup Codes Response

```json
{
  "codes": [
    "A3K9-7BDF",
    "X2M5-9NPQ",
    "..."
  ],
  "created_at": "2025-12-21T10:30:00Z"
}
```

### Using Backup Codes for Login

Backup codes can be used in the MFA verification step instead of TOTP codes:

```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
X-Client-Type: web|mobile

{
  "mfa_challenge": "<mfa_challenge from the login response>",
  "mfa_code": "A3K9-7BDF"
}
```

!!! warning "Important"
    - Backup codes are shown only once when generated - users must save them securely
    - Each backup code can only be used once
    - Regenerating codes invalidates ALL previous backup codes
    - Store backup codes in a secure location separate from your authenticator device

