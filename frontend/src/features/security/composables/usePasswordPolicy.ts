import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'

import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import { HttpError } from '@/services/http'
import { isValidPassword, resolvePasswordMinLength } from '@/utils/validation'

/** Problem types the server answers (HTTP 422) for a password it refuses. */
const PASSWORD_TOO_SHORT_TYPE = 'urn:endurain:error:password-too-short'
const PASSWORD_TOO_COMMON_TYPE = 'urn:endurain:error:password-too-common'
const PASSWORD_MATCHES_ACCOUNT_TYPE = 'urn:endurain:error:password-matches-account'

/**
 * The server's password policy for an account tier, as every password form
 * shows and checks it.
 *
 * @param accessType - The access type of the account the password is for
 *   (`'admin'` or `'regular'`), which selects the minimum length.
 * @returns A hint describing the policy, its `minLength`, `isValid` to test a password, and
 *   `validate`, a `useForm` validator returning the shared error message, and
 *   `policyError`, which words a refusal by the server.
 */
export function usePasswordPolicy(accessType: MaybeRefOrGetter<string>) {
  const { t } = useI18n()
  const { serverSettings } = usePublicServerSettings()

  const minLength = computed(() =>
    resolvePasswordMinLength(
      serverSettings.value.password_length_regular_users,
      serverSettings.value.password_length_admin_users,
      toValue(accessType),
    ),
  )

  const hint = computed(() => t('app.password.hintLength', { min: minLength.value }))

  /**
   * Tells whether a password meets the policy.
   *
   * @param password - Raw password input.
   * @returns `true` when it meets every requirement.
   */
  function isValid(password: string): boolean {
    return isValidPassword(password, minLength.value)
  }

  /**
   * Validates a password for `useForm`.
   *
   * @param password - Raw password input.
   * @returns The shared error message, or `null` when the password is valid.
   */
  function validate(password: string): string | null {
    return isValid(password) ? null : t('app.password.invalid')
  }

  /**
   * Words the server's refusal of a password.
   *
   * @param error - A caught error from a request that sets a password.
   * @returns The translated reason, or `null` when the error is not one of the
   *   password refusals, so the caller keeps its own handling.
   */
  function policyError(error: unknown): string | null {
    if (!(error instanceof HttpError) || error.status !== 422) {
      return null
    }
    switch (error.type) {
      case PASSWORD_TOO_SHORT_TYPE:
        return t('app.password.tooShort', { min: minLength.value })
      case PASSWORD_TOO_COMMON_TYPE:
        return t('app.password.tooCommon')
      case PASSWORD_MATCHES_ACCOUNT_TYPE:
        return t('app.password.matchesAccount')
      default:
        return null
    }
  }

  return { hint, minLength, isValid, validate, policyError }
}

/**
 * Compares a password with its confirmation. A blank confirmation is neither
 * a match nor a mismatch, so no error shows before the user types it.
 *
 * @param password - The new password.
 * @param confirmation - The repeated password.
 * @returns `matches` when the confirmation is filled in and equal, and `error`,
 *   the shared mismatch message while a filled-in confirmation differs.
 */
export function usePasswordConfirmation(
  password: MaybeRefOrGetter<string>,
  confirmation: MaybeRefOrGetter<string>,
) {
  const { t } = useI18n()

  const matches = computed(() => {
    const confirmed = toValue(confirmation)
    return confirmed.length > 0 && confirmed === toValue(password)
  })
  const error = computed(() => {
    const confirmed = toValue(confirmation)
    return confirmed.length > 0 && confirmed !== toValue(password)
      ? t('app.password.mismatch')
      : undefined
  })

  return { matches, error }
}
