# Multi-Factor Authentication (MFA) Implementation

This document describes the MFA implementation added to Endurain for enhanced security.

## Overview

The MFA implementation uses TOTP (Time-based One-Time Password) standard, compatible with popular authenticator apps like:
- Google Authenticator
- Authy
- Microsoft Authenticator
- 1Password
- And other RFC 6238 compliant apps

## Backend Implementation

### Database Changes
- Added `mfa_enabled` (INTEGER) field to users table - tracks if MFA is enabled (0/1)
- Added `mfa_secret` (VARCHAR(64)) field to users table - stores encrypted TOTP secret

### API Endpoints

#### MFA Management
- `GET /api/v1/mfa/status` - Get user's MFA status
- `POST /api/v1/mfa/setup` - Generate QR code and secret for setup
- `POST /api/v1/mfa/enable` - Enable MFA after verifying setup code
- `POST /api/v1/mfa/disable` - Disable MFA with verification

#### Authentication
- `POST /api/v1/token` - Modified to support MFA-aware login
- `POST /api/v1/mfa/verify` - Complete login with MFA verification

### Security Features
- Secrets encrypted at rest using existing Fernet encryption
- Temporary storage for setup and login flows (memory-based)
- TOTP verification with 1-window tolerance for clock skew
- Automatic cleanup of temporary data on success/failure

## Frontend Implementation

### Settings Interface
- Added MFA section to Security settings
- Setup modal with QR code display and manual secret entry
- Disable confirmation modal with code verification
- Status display showing current MFA state

### Login Flow
- Progressive disclosure: MFA field only appears when needed
- Seamless two-step authentication
- Clear error messages for invalid codes
- Loading states and user feedback

### Components Modified
- `SettingsSecurityZone.vue` - Added MFA management
- `LoginView.vue` - Added MFA verification step
- Created `mfaService.js` - API interaction service

## User Experience

### Enabling MFA
1. User clicks "Enable MFA" in security settings
2. Backend generates secret and QR code
3. User scans QR code or manually enters secret in authenticator app
4. User enters verification code to confirm setup
5. MFA is enabled and secret is stored encrypted

### Login with MFA
1. User enters username and password
2. If MFA is enabled, login form shows MFA code field
3. User enters 6-digit code from authenticator app
4. System verifies code and completes login

### Disabling MFA
1. User clicks "Disable MFA" in security settings
2. User enters current MFA code to confirm
3. MFA is disabled and secret is removed

## Technical Details

### Dependencies Added
- `pyotp` - TOTP implementation
- `qrcode[pil]` - QR code generation with PIL support

### Key Files Created/Modified

#### Backend
- `users/user/mfa_utils.py` - Core MFA functionality
- `users/user/mfa_router.py` - API endpoints
- `users/user/models.py` - Database schema
- `users/user/schema.py` - Pydantic models
- `users/user/crud.py` - Database operations
- `session/router.py` - Modified login flow
- `session/schema.py` - Login schemas

#### Frontend
- `services/mfaService.js` - API service
- `components/Settings/SettingsSecurityZone.vue` - Settings UI
- `views/LoginView.vue` - Login UI
- Translation files updated

### Configuration
- No additional configuration required
- Uses existing Fernet encryption key for secret storage
- Compatible with existing authentication system

## Security Considerations

1. **Secret Storage**: TOTP secrets are encrypted at rest using the application's Fernet key
2. **Temporary Storage**: Setup and login flows use memory-based storage that's automatically cleaned up
3. **Time Tolerance**: TOTP verification allows 1 window tolerance (±30 seconds) for clock skew
4. **Backup Codes**: Not implemented in this version (potential future enhancement)
5. **Rate Limiting**: Uses existing API rate limiting (if configured)

## Future Enhancements

Potential improvements that could be added:
1. Backup recovery codes
2. Multiple TOTP devices per user
3. SMS/Email fallback options
4. Admin-enforced MFA policies
5. MFA usage analytics and logging

## Migration

The database migration `add_mfa_support_fields.py` adds the required fields with sensible defaults:
- `mfa_enabled` defaults to 0 (disabled)
- `mfa_secret` defaults to NULL

Existing users are unaffected and can opt-in to MFA when ready.