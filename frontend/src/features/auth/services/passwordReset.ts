import { apiFetch } from '@/services/http'
import type { Schemas } from '@/types'

interface PasswordResetRequest {
  email: string
}

interface PasswordResetConfirm {
  token: string
  new_password: string
}

/**
 * Requests a password reset email.
 *
 * @param request - Password reset request payload.
 * @throws {HttpError} When email delivery is unavailable or the request fails.
 */
export async function requestPasswordReset(request: PasswordResetRequest): Promise<void> {
  await apiFetch<void>('/password-reset/request', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Confirms a password reset, setting the new password for the token's account.
 *
 * @param request - Reset token and the chosen new password.
 * @throws {HttpError} 400 when the token is invalid or expired.
 */
export async function confirmPasswordReset(request: PasswordResetConfirm): Promise<void> {
  await apiFetch<void>('/password-reset/confirm', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Checks that a password reset token is still usable, without consuming it.
 *
 * @param token - The reset token from the emailed link.
 * @throws {HttpError} 400 when the token is invalid or expired.
 */
export async function validatePasswordResetToken(token: string): Promise<void> {
  await apiFetch<void>('/password-reset/validate', {
    method: 'POST',
    body: JSON.stringify({ token } satisfies Schemas['PasswordResetValidate']),
    auth: false,
    retryOnUnauthorized: false,
  })
}
