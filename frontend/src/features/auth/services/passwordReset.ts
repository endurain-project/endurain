import { apiFetch } from '@/services/http'
import type { Schemas } from '@/types'

interface PasswordResetRequest {
  email: string
}

interface PasswordResetConfirm {
  token: string
  new_password: string
}

type PasswordResetResponse = Schemas['PasswordResetRead']

/**
 * Requests a password reset email.
 *
 * @param request - Password reset request payload.
 * @returns The backend response body.
 * @throws {HttpError} When email delivery is unavailable or the request fails.
 */
export function requestPasswordReset(request: PasswordResetRequest): Promise<unknown> {
  return apiFetch<unknown>('/password-reset/request', {
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
 * @returns The backend confirmation message.
 * @throws {HttpError} 400 when the token is invalid or expired.
 */
export function confirmPasswordReset(
  request: PasswordResetConfirm,
): Promise<PasswordResetResponse> {
  return apiFetch<PasswordResetResponse>('/password-reset/confirm', {
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
