import type { AuthTokenResponse, Schemas } from '@/types'

import { clearAuthTokens, getAccessToken, getCsrfToken, setAuthTokens } from './authTokens'
import { emitMfaEnrolmentRequired } from './mfaEnrolment'
import { getApiBaseUrl } from './runtime'
import { emitSessionExpired } from './sessionExpiry'

/** API base URL resolved from `/env.js`, then `VITE_API_URL`, then same-origin. */
export const API_BASE_URL = getApiBaseUrl()

const STATE_CHANGING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

const REFRESH_PATH = '/auth/refresh'

/** Problem type of a 401 caused by the bearer token itself (missing, expired, malformed, session ended). */
const INVALID_TOKEN_PROBLEM = 'urn:endurain:error:invalid-token'

/** Problem type of a 403 saying the server requires MFA of this account, which has none yet. */
const MFA_ENROLMENT_REQUIRED_PROBLEM = 'urn:endurain:error:mfa-enrolment-required'

/**
 * Default per-request timeout. Caps a hung backend so requests fail fast
 * instead of leaving the UI (and TanStack Query) waiting forever. Override or
 * disable (`0`) per call via {@link ApiFetchOptions.timeoutMs}.
 */
const DEFAULT_TIMEOUT_MS = 30_000

type ResponseType = 'json' | 'text' | 'blob' | 'void'

export interface ApiFetchOptions extends RequestInit {
  auth?: boolean
  responseType?: ResponseType
  retryOnUnauthorized?: boolean
  /** Request timeout in ms; `0` disables it. Defaults to {@link DEFAULT_TIMEOUT_MS}. */
  timeoutMs?: number
}

/** Error thrown for non-2xx API responses, carrying the HTTP status. */
export class HttpError extends Error {
  /**
   * @param status - The HTTP status code of the failed response.
   * @param statusText - The HTTP status text.
   * @param detail - Backend-provided error detail, when available.
   * @param type - RFC 9457 problem type URN, e.g. `urn:endurain:error:conflict`.
   *   This is the member to branch on; `status` alone cannot distinguish two
   *   different 409s.
   * @param requestId - The backend's `X-Request-ID` for this failure. Quoting it
   *   in a bug report resolves to the exact server log line.
   * @param errors - Per-field validation failures of a 422 response; empty otherwise.
   * @param retryAfterSeconds - Seconds the server asked the client to wait (`Retry-After`, as
   *   sent with a 429 or 503); `null` when absent or unusable.
   * @param jobId - The running job a `409` conflict names (`job_id`), so a client can follow it;
   *   `null` when the response names none.
   */
  constructor(
    readonly status: number,
    statusText: string,
    readonly detail: unknown = null,
    readonly type: string | null = null,
    readonly requestId: string | null = null,
    readonly errors: readonly Schemas['FieldError'][] = [],
    readonly retryAfterSeconds: number | null = null,
    readonly jobId: string | null = null,
  ) {
    super(getErrorMessage(status, statusText, detail))
    this.name = 'HttpError'
  }
}

/** An RFC 9457 problem document, as returned by every API error path. */
interface ProblemDocument {
  type?: unknown
  detail?: unknown
  request_id?: unknown
  errors?: unknown
  job_id?: unknown
}

/** The parsed pieces of a failed response the client keeps. */
interface ParsedError {
  detail: unknown
  type: string | null
  requestId: string | null
  errors: Schemas['FieldError'][]
  jobId: string | null
}

/**
 * Converts backend error details into a compact error message.
 *
 * @param status - HTTP status code.
 * @param statusText - HTTP status text.
 * @param detail - Backend error detail.
 * @returns A safe diagnostic message for logs and developer tooling.
 */
function getErrorMessage(status: number, statusText: string, detail: unknown): string {
  if (typeof detail === 'string' && detail.length > 0) {
    return `HTTP ${status} ${detail}`
  }
  return `HTTP ${status} ${statusText}`
}

/**
 * Parses a non-2xx response body into its problem-document parts.
 *
 * Tolerates a non-conforming body (a plain string, or `{detail}` without the
 * other members) so a proxy or gateway error page does not become an unhandled
 * parse failure.
 *
 * @param response - Failed response.
 * @returns The problem type, detail and request id, as far as they are present.
 */
async function parseError(response: Response): Promise<ParsedError> {
  const empty: ParsedError = { detail: null, type: null, requestId: null, errors: [], jobId: null }
  const text = await response.text()
  if (!text) {
    return empty
  }
  try {
    const parsed = JSON.parse(text) as ProblemDocument
    return {
      detail: parsed.detail ?? parsed,
      type: typeof parsed.type === 'string' ? parsed.type : null,
      requestId: typeof parsed.request_id === 'string' ? parsed.request_id : null,
      errors: Array.isArray(parsed.errors) ? (parsed.errors as Schemas['FieldError'][]) : [],
      jobId: typeof parsed.job_id === 'string' ? parsed.job_id : null,
    }
  } catch {
    return { ...empty, detail: text }
  }
}

/**
 * Reads a `Retry-After` header, sent either as delta-seconds or as an HTTP date.
 *
 * @param value - The header value, or `null` when absent.
 * @returns Whole seconds to wait, or `null` when the header is absent, malformed or already past.
 */
function parseRetryAfter(value: string | null): number | null {
  if (value === null) {
    return null
  }
  const trimmed = value.trim()
  const seconds = /^\d+$/.test(trimmed)
    ? Number(trimmed)
    : (Date.parse(trimmed) - Date.now()) / 1000
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null
}

/**
 * Builds request headers shared by every API call.
 *
 * @param path - Path relative to {@link API_BASE_URL}.
 * @param init - Fetch options supplied by the caller.
 * @returns A normalized mutable `Headers` instance.
 */
function buildHeaders(path: string, init: ApiFetchOptions): Headers {
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  headers.set('X-Client-Type', 'web')

  if (
    init.body &&
    !headers.has('Content-Type') &&
    !(init.body instanceof FormData) &&
    !(init.body instanceof URLSearchParams)
  ) {
    headers.set('Content-Type', 'application/json')
  }

  if (init.auth !== false) {
    const accessToken = getAccessToken()
    const csrfToken = getCsrfToken()
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`)
    }
    // The refresh is authorised by the HttpOnly SameSite=Strict cookie and the backend accepts it
    // without the header. Another tab may have rotated the CSRF token, so a stale one would fail it.
    if (csrfToken && STATE_CHANGING_METHODS.has(method) && path !== REFRESH_PATH) {
      headers.set('X-CSRF-Token', csrfToken)
    }
  }

  return headers
}

/**
 * Builds the abort signal for a request, composing the caller's signal (e.g.
 * TanStack Query cancellation) with a timeout so a hung backend never leaves
 * the request pending forever.
 *
 * @param init - Fetch options supplied by the caller.
 * @returns A combined signal, or `undefined` when no timeout or signal applies.
 */
function buildSignal(init: ApiFetchOptions): AbortSignal | undefined {
  const timeoutMs = init.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const timeoutSignal = timeoutMs > 0 ? AbortSignal.timeout(timeoutMs) : undefined

  if (init.signal && timeoutSignal) {
    return AbortSignal.any([init.signal, timeoutSignal])
  }
  return init.signal ?? timeoutSignal
}

let refreshPromise: Promise<AuthTokenResponse> | null = null

/**
 * Refreshes in-memory auth tokens using the HTTP-only refresh cookie.
 *
 * Concurrent callers share one in-flight refresh. Only a refusal of the refresh
 * session (HTTP 401 or 403) clears the tokens and signals session expiry. Any
 * other failure, such as a network error, a timeout, or a 429 or 5xx response,
 * is re-thrown unchanged and leaves the tokens in place, so a transient outage
 * does not log the user out.
 *
 * @returns The refreshed auth token response.
 * @throws {unknown} The refresh failure. An {@link HttpError} for a non-2xx response,
 *   or the fetch rejection (TypeError, timeout or abort DOMException) otherwise.
 */
async function refreshAuthTokens(): Promise<AuthTokenResponse> {
  refreshPromise ??= rawApiFetch<AuthTokenResponse>(REFRESH_PATH, {
    method: 'POST',
    retryOnUnauthorized: false,
  })
    .then((response) => {
      setAuthTokens(response.access_token, response.csrf_token)
      return response
    })
    .catch((error: unknown) => {
      const sessionRefused =
        error instanceof HttpError && (error.status === 401 || error.status === 403)
      if (sessionRefused) {
        clearAuthTokens()
        emitSessionExpired()
      }
      throw error
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

/**
 * Performs one request without retry handling.
 *
 * @typeParam T - Expected response body.
 * @param path - Path relative to {@link API_BASE_URL}.
 * @param init - Fetch options.
 * @returns The parsed response body.
 * @throws {HttpError} When the response status is not 2xx.
 */
async function rawApiFetch<T>(path: string, init: ApiFetchOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: buildHeaders(path, init),
    signal: buildSignal(init),
  })

  if (!response.ok) {
    const parsed = await parseError(response)
    if (parsed.type === MFA_ENROLMENT_REQUIRED_PROBLEM) {
      emitMfaEnrolmentRequired()
    }
    throw new HttpError(
      response.status,
      response.statusText,
      parsed.detail,
      parsed.type,
      parsed.requestId,
      parsed.errors,
      parseRetryAfter(response.headers.get('Retry-After')),
      parsed.jobId,
    )
  }

  if (init.responseType === 'void' || response.status === 204) {
    return undefined as T
  }
  if (init.responseType === 'blob') {
    return (await response.blob()) as T
  }
  if (init.responseType === 'text') {
    return (await response.text()) as T
  }

  const text = await response.text()
  if (!text) {
    return undefined as T
  }
  try {
    return JSON.parse(text) as T
  } catch {
    // A 2xx response that isn't JSON (e.g. an SPA/proxy HTML fallback served for
    // a missing endpoint) — surface a clear error instead of a raw SyntaxError.
    throw new HttpError(response.status, 'Invalid JSON response')
  }
}

/**
 * Performs a JSON request against the API.
 *
 * Sends and receives JSON, includes credentials so the backend's HTTP-only
 * auth cookies travel with the request, and throws {@link HttpError} on
 * non-2xx responses.
 *
 * A 401 whose problem type is `urn:endurain:error:invalid-token` (the bearer token itself is
 * missing, expired, malformed or its session ended) refreshes the tokens once and replays the
 * request. Any other 401, such as a wrong step-up password, is thrown as-is. Opt out with
 * `auth: false` or `retryOnUnauthorized: false`; `/auth/refresh` never retries.
 *
 * A 403 whose problem type is `urn:endurain:error:mfa-enrolment-required` (the server requires MFA of this
 * account, which has none) signals the handler registered with `onMfaEnrolmentRequired`, then is thrown as-is.
 *
 * @typeParam T - Expected shape of the parsed JSON response.
 * @param path - Path relative to {@link API_BASE_URL} (e.g. `/config`).
 * @param init - Standard `fetch` options plus auth/retry options.
 * @returns The parsed JSON response body.
 * @throws {HttpError} When the response status is not 2xx.
 */
export async function apiFetch<T>(path: string, init: ApiFetchOptions = {}): Promise<T> {
  try {
    return await rawApiFetch<T>(path, init)
  } catch (error) {
    const shouldRetry =
      error instanceof HttpError &&
      error.type === INVALID_TOKEN_PROBLEM &&
      init.auth !== false &&
      init.retryOnUnauthorized !== false &&
      path !== REFRESH_PATH

    if (!shouldRetry) {
      throw error
    }

    await refreshAuthTokens()
    return rawApiFetch<T>(path, init)
  }
}
