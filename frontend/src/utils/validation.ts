/**
 * Pragmatic email shape check: a non-empty local part, an `@`, and a dotted
 * domain. This is intentionally lenient — final validation is always the
 * backend's responsibility. Use it to gate UI affordances (e.g. enabling a
 * submit button), not as a security boundary.
 */
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * Returns whether the given value looks like a valid email address.
 *
 * @param value - Raw user input; surrounding whitespace is ignored.
 * @returns `true` when the trimmed value matches {@link EMAIL_PATTERN}.
 */
export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim())
}

/**
 * Returns whether a password is at least the minimum length. Length is the
 * only rule the browser can check; the server also refuses common passwords and
 * ones built from the account's own details. Use it to gate the submit
 * affordance, not as a security boundary.
 *
 * @param password - Raw password input.
 * @param minLength - Minimum length of the account's access tier.
 * @returns `true` when the password has at least `minLength` characters,
 *   counted as the server counts them: Unicode code points of the NFC form.
 */
export function isValidPassword(password: string, minLength: number): boolean {
  return [...password.normalize('NFC')].length >= minLength
}

/**
 * Picks the minimum password length for an account's access tier, mirroring
 * the backend's `resolve_password_min_length` (`auth/credentials/service.py`) so
 * client-side hints/validation match what the server will actually enforce.
 *
 * @param regularLength - Minimum length configured for regular users.
 * @param adminLength - Minimum length configured for admin users.
 * @param accessType - The account's access type (`'admin'` or anything else).
 * @returns The minimum length that applies to `accessType`.
 */
export function resolvePasswordMinLength(
  regularLength: number,
  adminLength: number,
  accessType: string,
): number {
  return accessType === 'admin' ? adminLength : regularLength
}
