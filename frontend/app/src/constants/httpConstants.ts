/**
 * Standard HTTP status codes used throughout the application.
 *
 * @remarks
 * Includes common success (2xx), client error (4xx), and server error (5xx) status codes.
 */
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  INTERNAL_SERVER_ERROR: 500,
  SERVICE_UNAVAILABLE: 503
} as const

/**
 * Type representing valid HTTP status code values from the `HTTP_STATUS` constant.
 */
export type HttpStatusCode = (typeof HTTP_STATUS)[keyof typeof HTTP_STATUS]

/**
 * Constant string value for boolean query parameters.
 *
 * @remarks
 * Use this for URL query parameters that represent `true` values.
 */
export const QUERY_PARAM_TRUE = 'true' as const

/**
 * Extracts the HTTP status code from an error object.
 *
 * @param error - The error object to extract the status code from.
 * @returns The HTTP status code if found, or `null` if not extractable.
 *
 * @remarks
 * First attempts to extract from `error.response.status`, then falls back to
 * pattern matching common status codes in the error string.
 */
export const extractStatusCode = (error: unknown): number | null => {
  // Try to get status from response object
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { status?: number } }).response
    if (response?.status) {
      return response.status
    }
  }

  // Fallback: try to extract from error string
  const errorString = error?.toString() || ''
  if (errorString.includes('400')) return HTTP_STATUS.BAD_REQUEST
  if (errorString.includes('401')) return HTTP_STATUS.UNAUTHORIZED
  if (errorString.includes('403')) return HTTP_STATUS.FORBIDDEN
  if (errorString.includes('404')) return HTTP_STATUS.NOT_FOUND
  if (errorString.includes('409')) return HTTP_STATUS.CONFLICT
  if (errorString.includes('500')) return HTTP_STATUS.INTERNAL_SERVER_ERROR
  if (errorString.includes('503')) return HTTP_STATUS.SERVICE_UNAVAILABLE

  return null
}

/**
 * Checks if the status code represents a client error (4xx).
 *
 * @param statusCode - The HTTP status code to check.
 * @returns `true` if the status code is between 400 and 499, `false` otherwise.
 */
export const isClientError = (statusCode: number): boolean => {
  return statusCode >= 400 && statusCode < 500
}

/**
 * Checks if the status code represents a server error (5xx).
 *
 * @param statusCode - The HTTP status code to check.
 * @returns `true` if the status code is between 500 and 599, `false` otherwise.
 */
export const isServerError = (statusCode: number): boolean => {
  return statusCode >= 500 && statusCode < 600
}

/**
 * Checks if the status code represents a successful response (2xx).
 *
 * @param statusCode - The HTTP status code to check.
 * @returns `true` if the status code is between 200 and 299, `false` otherwise.
 */
export const isSuccessStatus = (statusCode: number): boolean => {
  return statusCode >= 200 && statusCode < 300
}
