/**
 * Decouples the HTTP layer from the router and the auth store, as `sessionExpiry` does: a refusal that says the
 * server requires MFA of this account sends the user to enrol, without the low-level fetch code importing either
 * (which would create an import cycle). One handler, registered once during bootstrap.
 */
type MfaEnrolmentRequiredHandler = () => void

let handler: MfaEnrolmentRequiredHandler | null = null

/**
 * Registers the handler invoked when the server refuses a request because the account must enrol MFA. Call once
 * during bootstrap; pass `null` to clear (e.g. in tests).
 *
 * @param next - The handler to install, or `null` to remove it.
 */
export function onMfaEnrolmentRequired(next: MfaEnrolmentRequiredHandler | null): void {
  handler = next
}

/**
 * Signals that the server requires MFA of the signed-in account, which has not enrolled one.
 * No-op when no handler is registered.
 */
export function emitMfaEnrolmentRequired(): void {
  handler?.()
}
