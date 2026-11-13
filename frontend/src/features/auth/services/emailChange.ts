import type { EmailChangeCancel, EmailChangeCancelResult } from '@/features/auth/types'

import { apiFetch } from '@/services/http'

/**
 * Reports an email change as not made by the account's owner, with the token of the link emailed to the account.
 * The server cancels a pending change, or puts the previous address back after a confirmed one when it is still free,
 * ends every session of the account and revokes its API keys.
 *
 * @param request - The token from the emailed link.
 * @returns Whether the change had been confirmed and whether the previous address was restored.
 * @throws {HttpError} 400 when the link is malformed, expired, already used or replaced by a later change,
 *   429 when rate limited.
 */
export async function cancelEmailChange(
  request: EmailChangeCancel,
): Promise<EmailChangeCancelResult> {
  return apiFetch<EmailChangeCancelResult>('/public/email-change/cancel', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}
