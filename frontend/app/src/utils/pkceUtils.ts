/**
 * PKCE (Proof Key for Code Exchange) Utilities
 * RFC 7636 compliant implementation for OAuth 2.1
 *
 * Provides cryptographically secure PKCE code verifier and challenge generation
 * using the Web Crypto API (native browser implementation).
 */

/**
 * Generates a cryptographically random code verifier for PKCE.
 *
 * The code verifier is a high-entropy cryptographic random string using the
 * unreserved characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
 *
 * @returns {Promise<string>} Base64url-encoded random string (43-128 characters)
 *
 * @example
 * const verifier = await generateCodeVerifier()
 * // Returns: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
 */
export async function generateCodeVerifier(): Promise<string> {
  // Generate 32 random bytes (256 bits)
  // Results in 43 characters when base64url encoded (meets RFC 7636 minimum)
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  return base64URLEncode(array)
}

/**
 * Generates a code challenge from a code verifier using SHA-256.
 *
 * The code challenge is the base64url-encoded SHA-256 hash of the code verifier.
 * This is the S256 method required by RFC 7636.
 *
 * @param {string} verifier - The code verifier to hash
 * @returns {Promise<string>} Base64url-encoded SHA-256 hash of the verifier
 *
 * @example
 * const verifier = await generateCodeVerifier()
 * const challenge = await generateCodeChallenge(verifier)
 * // Returns: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  // Encode the verifier as UTF-8 bytes
  const encoder = new TextEncoder()
  const data = encoder.encode(verifier)

  // Compute SHA-256 hash
  const hash = await crypto.subtle.digest('SHA-256', data)

  // Encode the hash as base64url
  return base64URLEncode(new Uint8Array(hash))
}

/**
 * Encodes a byte array as base64url (RFC 4648 Section 5).
 *
 * Base64url encoding is base64 with URL-safe characters:
 * - Replace '+' with '-'
 * - Replace '/' with '_'
 * - Remove trailing '=' padding
 *
 * @param {Uint8Array} buffer - The byte array to encode
 * @returns {string} Base64url-encoded string
 *
 * @private
 */
function base64URLEncode(buffer: Uint8Array): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''

  // Convert byte array to binary string
  for (let i = 0; i < bytes.length; i++) {
    const byte = bytes[i]
    if (byte !== undefined) {
      binary += String.fromCharCode(byte)
    }
  }

  // Encode as base64 and convert to base64url
  return btoa(binary)
    .replace(/\+/g, '-') // Replace + with -
    .replace(/\//g, '_') // Replace / with _
    .replace(/=+$/, '') // Remove trailing padding
}

/**
 * Validates a code verifier format according to RFC 7636.
 *
 * A valid code verifier:
 * - Must be 43-128 characters long
 * - Must contain only unreserved characters: [A-Z] [a-z] [0-9] - . _ ~
 *
 * @param {string} verifier - The code verifier to validate
 * @returns {boolean} True if valid, false otherwise
 *
 * @example
 * validateCodeVerifier("abc123") // false (too short)
 * validateCodeVerifier("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") // true
 */
export function validateCodeVerifier(verifier: string): boolean {
  // Check length requirement (43-128 characters)
  if (verifier.length < 43 || verifier.length > 128) {
    return false
  }

  // Check character set (only unreserved characters allowed)
  const unreservedChars = /^[A-Za-z0-9\-._~]+$/
  return unreservedChars.test(verifier)
}

/**
 * Validates a code challenge format.
 *
 * A valid code challenge:
 * - Must be base64url encoded
 * - Must be 43 characters (SHA-256 hash encoded)
 *
 * @param {string} challenge - The code challenge to validate
 * @returns {boolean} True if valid, false otherwise
 *
 * @example
 * validateCodeChallenge("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM") // true
 */
export function validateCodeChallenge(challenge: string): boolean {
  // SHA-256 produces 32 bytes, which encodes to 43 base64url characters
  if (challenge.length !== 43) {
    return false
  }

  // Check base64url character set
  const base64urlChars = /^[A-Za-z0-9\-_]+$/
  return base64urlChars.test(challenge)
}
