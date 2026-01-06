/**
 * Validates an email address using RFC 5322 compliant regex.
 *
 * @param email - The email address to validate.
 * @returns `true` if the email is valid, `false` otherwise.
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
 * Checks if a string value is not empty after trimming whitespace.
 *
 * @param value - The string to check.
 * @returns `true` if the value is non-empty, `false` otherwise.
 */
export const isNotEmpty = (value: string): boolean => {
  return typeof value === 'string' && value.trim().length > 0
}

/**
 * Checks if a string meets a minimum length requirement.
 *
 * @param value - The string to check.
 * @param minLength - The minimum required length.
 * @returns `true` if the value meets the minimum length, `false` otherwise.
 */
export const hasMinLength = (value: string, minLength: number): boolean => {
  return typeof value === 'string' && value.length >= minLength
}

/**
 * Checks if a string does not exceed a maximum length.
 *
 * @param value - The string to check.
 * @param maxLength - The maximum allowed length.
 * @returns `true` if the value is within the maximum length, `false` otherwise.
 */
export const hasMaxLength = (value: string, maxLength: number): boolean => {
  return typeof value === 'string' && value.length <= maxLength
}

/**
 * Validates a multi-factor authentication code.
 *
 * @param code - The MFA code to validate.
 * @returns `true` if the code is valid (4-8 digits), `false` otherwise.
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
 * Sanitizes user input by trimming whitespace.
 *
 * @param input - The input string to sanitize.
 * @returns The trimmed string, or empty string if input is not a string.
 */
export const sanitizeInput = (input: string): string => {
  if (typeof input !== 'string') {
    return ''
  }
  return input.trim()
}

/**
 * Defines password validation requirements.
 *
 * @property minLength - Minimum password length.
 * @property requireUppercase - Whether uppercase letters are required.
 * @property requireLowercase - Whether lowercase letters are required.
 * @property requireDigit - Whether digits are required.
 * @property requireSpecialChar - Whether special characters are required.
 */
export interface PasswordRequirements {
  minLength: number
  requireUppercase: boolean
  requireLowercase: boolean
  requireDigit: boolean
  requireSpecialChar: boolean
}

/**
 * Describes password strength assessment results.
 *
 * @property isValid - Whether the password meets all requirements.
 * @property score - Numeric strength score.
 * @property failures - List of failed validation criteria.
 * @property strengthLevel - Overall strength level classification.
 */
export interface PasswordStrength {
  isValid: boolean
  score: number
  failures: string[]
  strengthLevel: 'weak' | 'fair' | 'good' | 'strong' | 'very-strong'
}

/**
 * Default password validation requirements for the application.
 */
export const DEFAULT_PASSWORD_REQUIREMENTS: PasswordRequirements = {
  minLength: 8,
  requireUppercase: true,
  requireLowercase: true,
  requireDigit: true,
  requireSpecialChar: true
}

/**
 * Validates a password against specified requirements.
 *
 * @param password - The password to validate.
 * @param requirements - The password requirements to check against.
 * @returns `true` if the password meets all requirements, `false` otherwise.
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
 * Checks if two password strings match exactly.
 *
 * @param password - The original password.
 * @param confirmPassword - The confirmation password.
 * @returns `true` if both passwords match, `false` otherwise.
 */
export const passwordsMatch = (password: string, confirmPassword: string): boolean => {
  return (
    typeof password === 'string' &&
    typeof confirmPassword === 'string' &&
    password === confirmPassword
  )
}

/**
 * Builds password requirements based on password policy type and minimum length.
 * Translates server password policy settings into validation requirements.
 *
 * @param passwordType - The password policy type ('strict', 'length_only').
 * @param minLength - The minimum password length.
 * @returns Password requirements object configured for the specified policy.
 */
export const buildPasswordRequirements = (
  passwordType: string,
  minLength: number
): PasswordRequirements => {
  switch (passwordType) {
    case 'strict':
      return {
        minLength,
        requireUppercase: true,
        requireLowercase: true,
        requireDigit: true,
        requireSpecialChar: true
      }
    case 'length_only':
      return {
        minLength,
        requireUppercase: false,
        requireLowercase: false,
        requireDigit: false,
        requireSpecialChar: false
      }
    default:
      return DEFAULT_PASSWORD_REQUIREMENTS
  }
}
