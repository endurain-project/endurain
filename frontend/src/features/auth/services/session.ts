import type { AuthTokenResponse } from '@/types'
import type {
  LoginResponse,
  LogoutResponse,
  MfaLoginRequest,
  MfaVerifyResponse,
  PasswordChangeLoginRequest,
  PasswordChangeResponse,
} from '@/features/auth/types'

import { apiFetch } from '@/services/http'

/**
 * Authenticates with username/password using the backend's login form.
 *
 * @param username - Username supplied by the user.
 * @param password - Password supplied by the user.
 * @returns The answer, whose `next_step` says what comes next.
 * @throws {HttpError} When authentication fails or the account is locked.
 */
export function loginWithPassword(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)

  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body,
    auth: false,
    retryOnUnauthorized: false,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
    },
  })
}

/**
 * Verifies a pending MFA login and completes authentication.
 *
 * @param request - The login's challenge plus TOTP/backup code.
 * @returns The answer, whose `next_step` says what comes next.
 * @throws {HttpError} When the code is invalid or the pending login expired.
 */
export function verifyMfaLogin(request: MfaLoginRequest): Promise<MfaVerifyResponse> {
  return apiFetch<MfaVerifyResponse>('/auth/mfa/verify', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Chooses the new password that an administrator-set password requires and
 * completes the pending sign-in.
 *
 * @param request - The login's challenge plus the new password.
 * @returns The answer, whose `next_step` says what comes next.
 * @throws {HttpError} 401 when the challenge is unknown, expired or used; 422
 *   with a password problem type when the password is refused (the challenge
 *   stays usable).
 */
export function changePasswordAtLogin(
  request: PasswordChangeLoginRequest,
): Promise<PasswordChangeResponse> {
  return apiFetch<PasswordChangeResponse>('/auth/password-change', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Refreshes the web session using the backend's HTTP-only refresh cookie.
 *
 * @returns A fresh web auth token response.
 * @throws {HttpError} When the refresh cookie is absent, expired, or invalid.
 */
export function refreshSession(): Promise<AuthTokenResponse> {
  return apiFetch<AuthTokenResponse>('/auth/refresh', {
    method: 'POST',
    retryOnUnauthorized: false,
  })
}

/**
 * Logs out the current backend session and clears the refresh cookie. A missing, expired or revoked refresh
 * token is not an error: the answer is the same and the cookie is cleared.
 *
 * @returns The identity provider's end-session URL, or `null` when the session did not sign in through one.
 * @throws {HttpError} When the request is refused (a missing CSRF token) or the server fails.
 */
export function logoutSession(): Promise<LogoutResponse> {
  return apiFetch<LogoutResponse>('/auth/logout', {
    method: 'POST',
    retryOnUnauthorized: false,
  })
}
