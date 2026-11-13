import { HttpError } from '@/services/http'

/** Prefix every API problem type URN shares. */
const PROBLEM_PREFIX = 'urn:endurain:error:'

/**
 * Whether an error is an API problem of one of the given kinds. Branch on this rather than on the
 * status, because one status carries several different problems.
 *
 * @param error - The error a request rejected with.
 * @param codes - Problem codes without the URN prefix, e.g. `conflict` or `rate-limited`.
 * @returns True for an `HttpError` whose `type` is one of the codes.
 */
export function isProblem(error: unknown, ...codes: string[]): error is HttpError {
  return (
    error instanceof HttpError &&
    error.type !== null &&
    codes.some((code) => error.type === `${PROBLEM_PREFIX}${code}`)
  )
}

/**
 * Builds the "try again in N seconds" text for a throttled (429) or unavailable (503) response
 * that told the client how long to wait.
 *
 * @param error - The error a request rejected with.
 * @param t - The translate function.
 * @returns The wait text, or null when the error carries no wait so the caller keeps its own text.
 */
export function retryWaitMessage(
  error: unknown,
  t: (key: string, params: { seconds: number }) => string,
): string | null {
  if (!(error instanceof HttpError) || error.retryAfterSeconds === null) {
    return null
  }
  const seconds = error.retryAfterSeconds
  if (isProblem(error, 'rate-limited', 'too-many-requests')) {
    return t('app.retryAfter.tooManyAttempts', { seconds })
  }
  if (isProblem(error, 'service-unavailable')) {
    return t('app.retryAfter.unavailable', { seconds })
  }
  return null
}
