/**
 * HTTP Status Codes and Error Handling Utilities
 *
 * Centralized constants and utilities for HTTP status codes and error handling
 * across the Endurain application.
 */

/**
 * Common HTTP status codes used throughout the application
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
 * Type for HTTP status code values
 */
export type HttpStatusCode = (typeof HTTP_STATUS)[keyof typeof HTTP_STATUS]

/**
 * Common query parameter constant for boolean 'true' values
 */
export const QUERY_PARAM_TRUE = 'true' as const

/**
 * Extract status code from error response or error string
 *
 * @param error - Error object that may contain a response with status code
 * @returns The extracted status code or null if not found
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
  if (errorString.includes('401')) return HTTP_STATUS.UNAUTHORIZED
  if (errorString.includes('403')) return HTTP_STATUS.FORBIDDEN
  if (errorString.includes('404')) return HTTP_STATUS.NOT_FOUND
  if (errorString.includes('409')) return HTTP_STATUS.CONFLICT
  if (errorString.includes('500')) return HTTP_STATUS.INTERNAL_SERVER_ERROR
  if (errorString.includes('503')) return HTTP_STATUS.SERVICE_UNAVAILABLE

  return null
}

/**
 * Check if status code is a client error (4xx)
 */
export const isClientError = (statusCode: number): boolean => {
  return statusCode >= 400 && statusCode < 500
}

/**
 * Check if status code is a server error (5xx)
 */
export const isServerError = (statusCode: number): boolean => {
  return statusCode >= 500 && statusCode < 600
}

/**
 * Check if status code is successful (2xx)
 */
export const isSuccessStatus = (statusCode: number): boolean => {
  return statusCode >= 200 && statusCode < 300
}
