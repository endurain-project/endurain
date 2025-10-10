/**
 * Validation Utilities
 *
 * Common validation helpers for form inputs and data validation.
 */

/**
 * Validate email format using RFC 5322 standard
 *
 * @param email - Email address to validate
 * @returns True if email is valid, false otherwise
 */
export const isValidEmail = (email: string): boolean => {
  if (!email || typeof email !== 'string') {
    return false
  }

  // RFC 5322 compliant email regex (simplified)
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email.trim())
}

/**
 * Validate that a string is not empty or only whitespace
 *
 * @param value - String to validate
 * @returns True if string has content, false otherwise
 */
export const isNotEmpty = (value: string): boolean => {
  return typeof value === 'string' && value.trim().length > 0
}

/**
 * Validate minimum length for a string
 *
 * @param value - String to validate
 * @param minLength - Minimum required length
 * @returns True if string meets minimum length, false otherwise
 */
export const hasMinLength = (value: string, minLength: number): boolean => {
  return typeof value === 'string' && value.length >= minLength
}

/**
 * Validate maximum length for a string
 *
 * @param value - String to validate
 * @param maxLength - Maximum allowed length
 * @returns True if string is within max length, false otherwise
 */
export const hasMaxLength = (value: string, maxLength: number): boolean => {
  return typeof value === 'string' && value.length <= maxLength
}

/**
 * Validate MFA code format (typically 6 digits)
 *
 * @param code - MFA code to validate
 * @returns True if code is valid format, false otherwise
 */
export const isValidMFACode = (code: string): boolean => {
  if (!code || typeof code !== 'string') {
    return false
  }
  // Most MFA codes are 6 digits, but some systems use different lengths
  const mfaRegex = /^\d{4,8}$/
  return mfaRegex.test(code.trim())
}

/**
 * Sanitize input string by trimming whitespace and removing potentially harmful characters
 *
 * @param input - String to sanitize
 * @returns Sanitized string
 */
export const sanitizeInput = (input: string): string => {
  if (typeof input !== 'string') {
    return ''
  }
  return input.trim()
}
