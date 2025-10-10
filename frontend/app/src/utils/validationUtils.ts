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

// ============================================================================
// Password Validation
// ============================================================================

/**
 * Password validation requirements interface
 * @interface PasswordRequirements
 */
export interface PasswordRequirements {
  /** Minimum password length */
  minLength: number
  /** Requires at least one uppercase letter */
  requireUppercase: boolean
  /** Requires at least one lowercase letter */
  requireLowercase: boolean
  /** Requires at least one digit */
  requireDigit: boolean
  /** Requires at least one special character */
  requireSpecialChar: boolean
}

/**
 * Password strength analysis result
 * @interface PasswordStrength
 */
export interface PasswordStrength {
  /** Whether password meets all requirements */
  isValid: boolean
  /** Overall strength score (0-100) */
  score: number
  /** Specific requirement failures */
  failures: string[]
  /** Descriptive strength level */
  strengthLevel: 'weak' | 'fair' | 'good' | 'strong' | 'very-strong'
}

/**
 * Default password requirements matching backend validation
 * Requirements: min 8 chars, 1 uppercase, 1 digit, 1 special character
 */
export const DEFAULT_PASSWORD_REQUIREMENTS: PasswordRequirements = {
  minLength: 8,
  requireUppercase: true,
  requireLowercase: false, // Not explicitly required but usually present
  requireDigit: true,
  requireSpecialChar: true
}

/**
 * Validate password against standard requirements
 * Default requirements: min 8 chars, 1 uppercase, 1 digit, 1 special character
 *
 * @param password - Password to validate
 * @param requirements - Optional custom requirements (defaults to standard)
 * @returns True if password meets requirements, false otherwise
 *
 * @example
 * ```typescript
 * isValidPassword('MyPass123!') // true
 * isValidPassword('weakpass') // false - no uppercase, digit, or special char
 * ```
 */
export const isValidPassword = (
  password: string,
  requirements: PasswordRequirements = DEFAULT_PASSWORD_REQUIREMENTS
): boolean => {
  if (!password || typeof password !== 'string') {
    return false
  }

  // Check minimum length
  if (password.length < requirements.minLength) {
    return false
  }

  // Check uppercase requirement
  if (requirements.requireUppercase && !/[A-Z]/.test(password)) {
    return false
  }

  // Check lowercase requirement
  if (requirements.requireLowercase && !/[a-z]/.test(password)) {
    return false
  }

  // Check digit requirement
  if (requirements.requireDigit && !/\d/.test(password)) {
    return false
  }

  // Check special character requirement
  // Matches the same special chars as backend: !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~
  if (requirements.requireSpecialChar && !/[ !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(password)) {
    return false
  }

  return true
}

/**
 * Validate that two passwords match (for confirmation fields)
 *
 * @param password - Original password
 * @param confirmPassword - Confirmation password
 * @returns True if passwords match, false otherwise
 *
 * @example
 * ```typescript
 * passwordsMatch('MyPass123!', 'MyPass123!') // true
 * passwordsMatch('MyPass123!', 'DifferentPass') // false
 * ```
 */
export const passwordsMatch = (password: string, confirmPassword: string): boolean => {
  return (
    typeof password === 'string' &&
    typeof confirmPassword === 'string' &&
    password === confirmPassword
  )
}
