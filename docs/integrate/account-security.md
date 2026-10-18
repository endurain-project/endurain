# Account security

## Step-up Authentication

Certain sensitive account operations require the user to re-prove possession of their credentials even when they already hold a valid access token. This is called **step-up verification**.

### Operations That Require Step-up

| Operation | Endpoint |
| --------- | -------- |
| Change own password | `PUT /profile/password` |
| Enable MFA | `PUT /profile/mfa/enable` |
| Disable MFA | `PUT /profile/mfa/disable` |
| Regenerate MFA backup codes | `POST /profile/mfa/backup-codes` |
| Create API key | `POST /profile/api_keys` |
| Generate IdP link token | `POST /profile/idp/{idp_id}/link/token` |
| Remove IdP link | `POST /profile/idp/{idp_id}/unlink` |

### Step-up Request Body

All step-up operations accept the following fields in their JSON request body (alongside any operation-specific fields):

| Field | Required | Description |
| ----- | -------- | ----------- |
| `current_password` | Conditionally | Required for accounts with a local password. Omit for SSO-only accounts (no local credential exists) |
| `mfa_code` | Conditionally | Required when MFA is enabled on the account. Accepts TOTP codes or backup codes |

**Example:**

```json
{
  "current_password": "current-password",
  "mfa_code": "123456"
}
```

SSO-only accounts (no local password) may omit `current_password`. The password factor is skipped because there is nothing to verify against. If MFA is enabled, the `mfa_code` is still required regardless of account type.

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
Complete the login by providing the MFA code (TOTP or backup code) to `/auth/mfa/verify`:

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
| **Regenerate Backup Codes** | `/profile/mfa/backup-codes` | POST | Generates new codes (invalidates old). Requires step-up JSON body: `current_password` for local-password accounts and `mfa_code` when MFA is enabled |

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

For SSO-only accounts, `current_password` may be omitted because there is no local password to verify. If MFA is enabled, `mfa_code` is required.

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
  "username": "user@example.com",
  "mfa_code": "A3K9-7BDF"
}
```

!!! warning "Important"
    - Backup codes are shown only once when generated - users must save them securely
    - Each backup code can only be used once
    - Regenerating codes invalidates ALL previous backup codes
    - Store backup codes in a secure location separate from your authenticator device

