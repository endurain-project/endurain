# Account security

## Step-up Authentication

Certain sensitive account operations require the user to re-prove possession of their credentials even when they already hold a valid access token. This is called **step-up verification**.

### Operations That Require Step-up

| Operation | Endpoint |
| --------- | -------- |
| Change own password | `POST /profile/password/change` |
| Change own email | `POST /profile/email/change` |
| Enable MFA | `POST /profile/mfa/enable` (`409` when MFA is already enabled or no setup is in progress) |
| Disable MFA | `POST /profile/mfa/disable` (answers `204`; `409` when MFA is not enabled) |
| Regenerate MFA backup codes | `POST /profile/mfa/backup-codes` |
| Create API key | `POST /profile/api-keys` |
| Start IdP link | `POST /profile/identity-providers/{idp_id}/link` |
| Remove IdP link | `POST /profile/identity-providers/{idp_id}/unlink` |
| Delete own account | `POST /profile/delete-account` |
| Export own profile data | `POST /profile/export` |
| Set another user's password (administrators) | `POST /users/{user_id}/password/change` |
| Reset another user's MFA (administrators) | `POST /users/{user_id}/mfa/reset` |
| Require another user to change their password at the next sign-in (administrators) | `POST /users/{user_id}/password/require-change` |
| Change another user's email, access type or active flag (administrators) | `PATCH /users/{user_id}`, in its `step_up` object |
| Delete another user's account (administrators) | `POST /users/{user_id}/delete` |
| Unlink another user's identity provider (administrators) | `POST /users/{user_id}/identity-providers/{idp_id}/unlink` |
| Create an administrator account (administrators) | `POST /users`, in its `step_up` object |
| Add or edit an identity provider (administrators) | `POST /identity-providers` and `PATCH /identity-providers/{idp_id}`, in their `step_up` object |
| End another user's sessions (administrators) | `POST /users/{user_id}/sessions/{session_id}/revoke` and `POST /users/{user_id}/sessions/revoke` |
| Edit the mail server settings (administrators) | `PUT /server-settings/email/settings`, in its `step_up` object |

The administrator operations verify the **administrator's own** credentials, never the target user's, so a stolen access token alone cannot set a password, hand over, lock out or delete an account, create an administrator, add or edit an identity provider (a rogue provider can claim accounts) or point outgoing mail at another server (which exposes every password-reset link). `PATCH /users/{user_id}` needs step-up only when the edit changes the email, the access type or the active flag; it carries the fields in a `step_up` object next to the user fields, and an edit of anything else needs none. `POST /users` needs it only when `access_type` is `admin`; creating a regular user needs none. `POST /identity-providers` and `PATCH /identity-providers/{idp_id}` always need a `step_up` object, which is required in their body and is never a provider field; `PATCH` keeps its `If-Match`. Both answer `409` with `urn:endurain:error:issuer-in-use` when the `issuer_url` is already used by another provider (a trailing slash is ignored; a null `issuer_url` never conflicts), and `PATCH` also answers `409` with `urn:endurain:error:issuer-locked` when it would change, set or clear the `issuer_url` of a provider that users are linked to (a change of only the trailing slash is allowed). A slug already in use is a plain `409` with `urn:endurain:error:conflict`. `PUT /server-settings/email/settings` always needs a `step_up` object too, required in its body and never a mail setting; it keeps its `If-Match`. `POST /users/{user_id}/sessions/{session_id}/revoke` and `POST /users/{user_id}/sessions/revoke` (which keeps the optional `exclude_session_id` query parameter) take only the `{ "step_up": { ... } }` body and answer `204`. `POST /users/{user_id}/mfa/reset` and `POST /users/{user_id}/password/require-change` take the same `{ "step_up": { ... } }` body and answer `204`; both refuse the administrator's own account (`403`), end all of the user's sessions and notify the user. The MFA reset removes the user's MFA secret and backup codes and answers `409` when the user has no MFA. The password-change requirement keeps the user's current password and answers `409` when the user has no local password. A step-up that does not verify creates, changes or ends nothing. Approving a user needs no step-up; it answers `409` when sign-up requires email verification and the user's email is not verified.

Removing an identity provider link, yourself or as an administrator, also ends every session of that user that signed in through the provider, the caller's own session included when it did. A client holding such a session gets `401` on its next request and refreshes no further. The link responses carry no `idp_access_token_expires_at` or `idp_refresh_token_updated_at`: Endurain keeps provider tokens per session, not per link.

### Scopes

The routes of this page that change the account's credentials or close it need the `profile:security` scope: password and email change, account deletion, MFA, API keys, sessions and identity provider links. Profile export and import need `profile:export`. Both are held by every user's tokens, as `profile` is, and a token can be issued with fewer scopes: a route checks the scopes the token carries, never more than the user's role holds. See [Security scopes](auth-reference.md#security-scopes).

### Step-up Request Body

Every step-up operation takes the credentials in a `step_up` object of its JSON request body, next to any operation-specific fields. A request that needs nothing else is `{ "step_up": { ... } }`. No other field of a request carries `current_password` or `idp_reauth`. The `step_up` object has these fields:

| Field | Required | Description |
| ----- | -------- | ----------- |
| `current_password` | Conditionally | Required for accounts with a local password |
| `idp_reauth` | Conditionally | Required for accounts without a local password: `{"ticket": "...", "code_verifier": "..."}`, proof of a fresh sign-in with a linked identity provider. See [Step-up for accounts without a password](#step-up-for-accounts-without-a-password) |
| `mfa_code` | Conditionally | Required when MFA is enabled on the account. Accepts TOTP codes or backup codes |

**Example:**

```json
{
  "step_up": {
    "current_password": "current-password",
    "mfa_code": "123456"
  }
}
```

Account deletion, profile export and identity provider unlink send exactly this body. The other operations add their own fields next to `step_up`: `password` and `revoke_other_sessions` for the password change, `email` and `revoke_other_sessions` for the email change, `totp_code` (the code of the authenticator being enrolled) and `revoke_other_sessions` for MFA enable, `revoke_other_sessions` for MFA disable and backup-code regeneration, `redirect` and `revoke_other_sessions` for an identity provider link, and `name`, `scopes` and `expires_at` for an API key. MFA disable sends the code in `step_up.mfa_code`. Password change (`POST /profile/password/change`) needs a local password and is answered `403` for an account without one; an administrator sets the first password through `POST /users/{user_id}/password/change`, which refuses the administrator's own account and takes the administrator's `step_up` next to `password`.

### Ending other sessions after a change of an authentication factor

Changing a factor ends the caller's other sessions, and keeps the session that made the change. `revoke_other_sessions` is a boolean that defaults to `true` on these operations: the password change, the email change, MFA enable, MFA disable, backup-code regeneration and the identity provider link. Send `false` to keep the other sessions. Unlinking a provider ends the sessions that signed in through it, whatever the body says.

The sessions end in the same transaction as the change. A request whose step-up is refused changes nothing and ends no session. The audit row of the change carries `sessions_revoked`, the number of sessions it ended (`0` when the client sent `false`); this applies to `auth.password.change`, `auth.mfa.enable`, `auth.mfa.disable` and `auth.backup_codes.generate`. A link completes in the provider callback, which ends the sessions then and records them as an `auth.session.revoke` row next to the link's own row.

### Step-up Refusal

A step-up that does not verify is `403` with `urn:endurain:error:step-up-failed` and the detail `Step-up verification failed`, with no `WWW-Authenticate` header. The answer is the same for a wrong password, a wrong or missing MFA code and a ticket that does not match, so it never confirms a correct password. It is not a dead token: do not refresh the tokens or sign the user out; show the credentials form again. A request that does not match the schema is `422`. The only `401` a step-up answers is `idp-reauth-required`, below. Failures count towards the lockout.

### Step-up for accounts without a password

An account without a local password cannot prove a password, and MFA alone does not pass step-up for it. It must prove a fresh sign-in with an identity provider linked to the account. This covers API key creation, IdP link, IdP unlink, email change, account deletion, profile export, MFA enable, MFA disable, backup-code regeneration and the administrator operations above, where it is the administrator's own account that has no password.

1. The sensitive request arrives without `idp_reauth`. The API answers `401` with problem type `urn:endurain:error:idp-reauth-required` and `WWW-Authenticate: Bearer error="insufficient_user_authentication", max_age="60"` ([RFC 9470](https://datatracker.ietf.org/doc/html/rfc9470)). A missing proof is not counted as a failed attempt.
2. The client generates a PKCE verifier and starts the sign-in with `POST /profile/identity-providers/{idp_id}/step-up`:

    ```json
    {
      "code_challenge": "<S256 challenge>",
      "action": "api_key_create",
      "redirect": "/settings?tab=security"
    }
    ```

    The start answers `409` with `urn:endurain:error:conflict` when the account has a local password, because it steps up with the password instead. `action` is one of `api_key_create`, `idp_link`, `idp_unlink`, `email_change`, `account_delete`, `profile_export`, `mfa_enable`, `mfa_disable`, `mfa_backup_codes`, `admin_credential_reset`, `admin_mfa_reset`, `admin_credential_change_require`, `admin_user_edit`, `admin_user_delete`, `admin_idp_unlink`, `admin_user_create`, `admin_idp_create`, `admin_idp_edit`, `admin_sessions_revoke`, `admin_mail_settings_edit`. A ticket pays only for the action it was started for, and stops paying once a security change of the account (a password or MFA change, a sign-out everywhere) comes after the step-up started; the callback then returns `#step_up_error=failed`, and a ticket redeemed after the change is refused like any other mismatched ticket. `redirect` must be a relative path; other values, including custom schemes, are refused. The response is `{"authorization_url": "..."}` and sets the HttpOnly, `SameSite=Lax` cookie `endurain_idp_binding`, scoped to the callback path, which ties the flow to that browser.
3. The browser opens `authorization_url`. Endurain asks the provider for a new sign-in (`prompt=login`, `max_age=60`, PKCE). The callback verifies the ID token (signature, `iss`, `aud`, `azp`, `exp`/`iat` with 60 seconds of leeway, `nonce`) and requires `auth_time` to be no earlier than 60 seconds before the step-up started. The userinfo endpoint is not used, and the provider account must be the one linked to the user.
4. The callback redirects to `redirect` with the result in the URL fragment: `#step_up_ticket=<ticket>` on success, or `#step_up_error=failed` or `#step_up_error=not_fresh`. `not_fresh` means the provider did not make the user sign in again.
5. The client repeats the sensitive request with `idp_reauth`:

    ```json
    {
      "step_up": {
        "idp_reauth": { "ticket": "<ticket>", "code_verifier": "<PKCE verifier>" },
        "mfa_code": "123456"
      }
    }
    ```

    `step_up.mfa_code` is also required when MFA is enabled. The ticket is single use, valid for 300 seconds, and bound to the user, the session, the action and the PKCE verifier. A wrong MFA code does not consume it.

Native and mobile clients cannot use this flow because the redirect must be a relative path, so they cannot step up an account without a password; the user does it in the web UI. Providers without an issuer URL (OAuth2 only) cannot do step-up. See [Single Sign-On](../features/single-sign-on.md#confirming-sensitive-changes-without-a-password).

### Step-up Lockout Policy

Failed step-up verifications are tracked per user and session with progressive lockout, independent of login lockout counters. A session that locks itself out does not lock the same user's other sessions, so someone holding only a stolen session cannot block the owner from sensitive changes:

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

A locked session can still end the user's other sessions, and the password can still be reset by email. Ending a session discards its counter.

## Email Change

`POST /profile/email/change` (step-up required) does not replace the account's address. It creates a pending change and answers `200` with the profile and its `ETag`: `pending_email` is set while the change awaits confirmation, and `email` already holds the new address when the server applied it at once (no outgoing mail). A later request replaces an earlier one. Entering the current address cancels the pending change. The answer does not depend on whether another account holds the address: a held address is answered, staged and read back exactly like a free one (`200`, the profile with `pending_email` set, the same `GET /profile` afterwards, the same `204` from the resend route), so the request cannot be used to find out which addresses are registered. No confirmation link is ever mailed for a held address; its holder is emailed a notice instead, at most once an hour (a request and a resend share that limit), and the change can never be confirmed. The one exception is a server that cannot send mail: a free address would change at once there, so a held address answers `409`. The address switches when the link emailed to the new address is confirmed through `POST /public/sign-up/confirm` (valid 24 hours). Confirmation answers `409` when another account has taken the address in the meantime, and then nothing changes. Until the change is confirmed, sign-in and password reset keep using the current address.

| What | URL | Method | Description |
| ---- | --- | ------ | ----------- |
| **Resend Confirmation** | `/profile/email/change/resend` | POST | Sends the confirmation for the pending address, at most once an hour. Requires scope `profile:security`, no step-up. Answers `204` whether or not an email was sent |
| **Cancel Pending Change** | `/profile/email/change` | DELETE | Cancels the pending change, so its confirmation link stops working. Requires scope `profile:security`, no step-up. Answers `204` |

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

MFA verification failures also count against the account across every address, on `/auth/mfa/verify` and on the SSO token exchange. After **100 wrong MFA codes in a row** for one account, MFA sign-in is locked for **30 days**:

- The count restarts on a successful MFA sign-in and expires after 30 days without a failure.
- A sign-in from a **known device** of the account (defined in the password lock below) is not refused by this lock. It still needs the right code and is still held by the tiered MFA lockout above, and its wrong codes still count.
- The lock and the count are cleared by a successful MFA sign-in, the user turning MFA off or setting it up again from a signed-in session, or an administrator resetting the user's MFA. A password reset or change does not clear them.
- When the 100th wrong code locks it, the owner gets one email and one in-app notification (`account_security_changed` with the change `mfa_locked`) and an `auth.lockout.apply` audit row with the counter `mfa_account`. The audit row holds no username.
- The refusal is the same `429`, with `Retry-After`, as the tiered MFA lockout.

Password login failures also count against the account across every address. After **100 failed sign-ins in a row** for one username the account is locked for **30 days**:

- The count restarts on a successful sign-in and expires after 30 days without a failure.
- A sign-in from a **known device** of the account is not refused by this lock. A device is known when the `endurain_device` cookie (web) or the `X-Device-Id` header (mobile) holds an id the account has signed in with before. Such a sign-in still needs the right password, MFA and the per-client lockout above, and its wrong passwords still count.
- The lock and the count are cleared by a successful sign-in, a completed password reset, the user changing their password, or an administrator setting it.
- When the 100th failure locks the account, its owner gets one email and one in-app notification (`account_security_changed` with the change `account_locked`) and an `auth.lockout.apply` audit row with the counter `login_account`. The audit row holds no username.
- A locked account and an unknown username are refused with the same `429` answer.

The per-client counters key an IPv6 address by its /64 network and an IPv4 address (or IPv4-mapped IPv6 address) as is.

**Features:**

- Failures count per username and client network (an IPv6 address by its /64), so one client cannot lock a user out for everyone; the account-wide locks below count failures from every address
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
  "next_step": "mfa",
  "mfa_challenge": "<opaque challenge>"
}
```

Every sign-in answer carries a `next_step`; see [Sign-in steps](authentication.md#sign-in-steps). A client that receives a `next_step` it does not know must stop and ask the user to update the app.

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

The challenge lives 5 minutes. The server accepts it only from the network of the password step (the same IPv4 address, or an address in the same IPv6 /64) and from the same client type, and it ends after 3 wrong codes or when the account's security changes before it is used (a password, MFA or email change, a sign-out everywhere, a deactivation). A wrong code on a live challenge is `400`. An unknown, expired, ended or mismatched challenge is `401`: start again at `POST /auth/login`.

!!! note "A TOTP code works once"
    The server accepts each authenticator code a single time. Submitting the same code again, on this endpoint or on any other that asks for an MFA code, fails like an invalid code until the next 30-second code appears.

!!! tip "Backup Code Format"
    Users can also use a backup code instead of a TOTP code. Backup codes are in `XXXX-XXXX` format (e.g., `A3K9-7BDF`). See [MFA Backup Codes](#mfa-backup-codes) for details.

**Response (successful verification):** `next_step` is `tokens`, or `exchange` for a mobile client that sent a PKCE challenge. When an administrator set the account's password the answer is `{"next_step": "password_change", "password_change_challenge": "..."}` and no session exists yet; see [Password change at sign-in](authentication.md#password-change-at-sign-in).

- **Web clients**: Access token and CSRF token in response body, refresh token as httpOnly cookie

```json
{
  "next_step": "tokens",
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
  "next_step": "tokens",
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

- **Invalid MFA code**: HTTP 400 Bad Request with `urn:endurain:error:invalid-mfa-code`. The same answer covers a wrong code and a used backup code on a challenge that is still live

```json
{
  "detail": "Invalid MFA code, backup code or backup code already used."
}
```

- **Dead `mfa_challenge`**: HTTP 401 Unauthorized with `WWW-Authenticate: Bearer`. The challenge is unknown, expired (5 minutes), ended after 3 wrong codes, or presented from another client network or client type. The answer is the same for each cause. Do not refresh or retry: send the user back to `POST /auth/login`

```json
{
  "detail": "Unable to authenticate with provided credentials"
}
```

- **Account locked out (too many failures)**: HTTP 429 Too Many Requests

```json
{
  "detail": "Too many failed MFA attempts. Account locked for 300 seconds."
}
```

### Important Notes
- The pending MFA login is temporary and expires after 5 minutes. It is accepted only from the client network and client type of the password step, and ends after 3 wrong codes
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

1. **Automatically on MFA Enable**: When a user enables MFA, 10 backup codes are generated and returned in the response, in the same `{"codes": [...], "created_at": "..."}` body as `POST /profile/mfa/backup-codes`
2. **Manual Regeneration**: Users can regenerate all backup codes via `POST /profile/mfa/backup-codes` (invalidates all previous codes). This endpoint requires step-up verification and MFA must already be enabled on the account (`409` when it is not).

### API Endpoints

| What | URL | Method | Description |
| ---- | --- | ------ | ----------- |
| **Get Backup Code Status** | `/profile/mfa/backup-codes/status` | GET | Returns count of unused/used codes |
| **Regenerate Backup Codes** | `/profile/mfa/backup-codes` | POST | Generates new codes (invalidates old). Requires a step-up JSON body, `{"step_up": {...}}`, and takes the optional `revoke_other_sessions` (default `true`): `current_password` for local-password accounts, `idp_reauth` for accounts without one, and `mfa_code` when MFA is enabled |

### Regenerate Backup Codes Request

```http
POST /api/v1/profile/mfa/backup-codes
Authorization: Bearer {access_token}
X-Client-Type: web
X-CSRF-Token: {csrf_token}
Content-Type: application/json

{
  "step_up": {
    "current_password": "current-password",
    "mfa_code": "123456"
  },
  "revoke_other_sessions": true
}
```

Accounts without a local password send `step_up.idp_reauth` instead of `step_up.current_password`. If MFA is enabled, `step_up.mfa_code` is required. `revoke_other_sessions` is optional and defaults to `true`: the user's other sessions end, and the current one stays.

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

## Responses that carry a secret

A response that carries a secret is sent with `Cache-Control: no-store` and `Pragma: no-cache`, so no browser or proxy cache keeps it. These are the token responses, `POST /profile/api-keys`, `POST /profile/mfa/setup`, `POST /profile/mfa/enable`, `POST /profile/mfa/backup-codes`, `POST /ws/ticket` and the profile export download, `GET /profile/export/download`.

## Profile export

`POST /profile/export` requires [step-up](#step-up-authentication) in its JSON body, so a stolen access token cannot take the account's data. It queues an export and answers `202`; a refused step-up answers `403` and queues nothing. `GET /profile/export` reports its state: `status` (`queued`, `running`, `completed` or `failed`), `failure`, `size_bytes` and `expires_at`. Once the export is `completed`, `expires_at` is the instant after which `GET /profile/export/download` stops working (two hours after completion). It is `null` for an export that is not completed, and `GET /profile/export` answers `null` once the state has expired. Request a new export then.
