/**
 * Formats a typed second-factor code the way the API expects it: whitespace removed, upper case,
 * and an 8-character backup code split as `XXXX-XXXX`. A 6-digit authenticator code is unchanged.
 *
 * @param raw - The code as typed.
 * @returns The code to send.
 */
export function normalizeMfaCode(raw: string): string {
  const compact = raw.replace(/\s+/g, '').toUpperCase()
  const backup = /^([A-Z0-9]{4})-?([A-Z0-9]{4})$/.exec(compact)
  return backup ? `${backup[1]}-${backup[2]}` : compact
}
