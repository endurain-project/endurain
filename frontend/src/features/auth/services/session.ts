import type { AuthTokenResponse } from '@/types'
import type { LoginResponse, MfaLoginRequest } from '@/features/auth/types'

import { apiFetch } from '@/services/http'

/**
 * Authenticates with username/password using the backend's OAuth2 form contract.
 *
 * @param username - Username supplied by the user.
 * @param password - Password supplied by the user.
 * @returns A token response, or an MFA-required response.
 * @throws {HttpError} When authentication fails or the account is locked.
 */
export function loginWithPassword(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams()
  body.set('grant_type', 'password')
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
 * @param request - Pending username plus TOTP/backup code.
 * @returns A web auth token response.
 * @throws {HttpError} When the code is invalid or the pending login expired.
 */
export function verifyMfaLogin(request: MfaLoginRequest): Promise<AuthTokenResponse> {
  return apiFetch<AuthTokenResponse>('/auth/mfa/verify', {
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
 * Logs out the current backend session and clears the refresh cookie.
 *
 * @throws {HttpError} When the refresh session cannot be validated.
 */
export async function logoutSession(): Promise<void> {
  await apiFetch<void>('/auth/logout', {
    method: 'POST',
    retryOnUnauthorized: false,
  })
}
