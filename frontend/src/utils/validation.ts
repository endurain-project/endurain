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

/** Longest password the server accepts, whether it sets the password or presents it. */
export const PASSWORD_MAX_LENGTH = 256

/**
 * Returns whether a password is at least the minimum length and at most `PASSWORD_MAX_LENGTH`. Length is the
 * only rule the browser can check; the server also refuses common passwords and
 * ones built from the account's own details. Use it to gate the submit
 * affordance, not as a security boundary.
 *
 * @param password - Raw password input.
 * @param minLength - Minimum length of the account's access tier.
 * @returns `true` when the password has at least `minLength` characters,
 *   counted as the server counts them: Unicode code points of the NFC form,
 *   and at most `PASSWORD_MAX_LENGTH` code points as typed.
 */
export function isValidPassword(password: string, minLength: number): boolean {
  return (
    [...password.normalize('NFC')].length >= minLength &&
    [...password].length <= PASSWORD_MAX_LENGTH
  )
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

/** Canonical textual form of a UUID, any version, case-insensitive. */
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Returns whether the given value is a UUID in its canonical hyphenated form.
 * Use it to reject a malformed id taken from a route before requesting it.
 *
 * @param value - Raw id, such as a route parameter.
 * @returns `true` when the value matches {@link UUID_PATTERN}.
 */
export function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value)
}
