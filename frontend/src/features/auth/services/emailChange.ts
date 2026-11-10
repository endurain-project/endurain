import type { EmailChangeCancel } from '@/features/auth/types'

import { apiFetch } from '@/services/http'

/**
 * Reports a requested email change as not made by the account's owner, with the token of the link emailed to the
 * current address. The server cancels the change, ends every session of the account and revokes its API keys.
 *
 * @param request - The token from the emailed link.
 * @throws {HttpError} 400 when the link is malformed, expired or from before a security change of the account,
 *   429 when rate limited.
 */
export async function cancelEmailChange(request: EmailChangeCancel): Promise<void> {
  await apiFetch<void>('/public/email-change/cancel', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
    responseType: 'void',
  })
}
