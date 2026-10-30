import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'

import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import {
  buildPasswordRequirements,
  isValidPassword,
  resolvePasswordMinLength,
} from '@/utils/validation'

/**
 * The server's password policy for an account tier, as every password form
 * shows and checks it.
 *
 * @param accessType - The access type of the account the password is for
 *   (`'admin'` or `'regular'`), which selects the minimum length.
 * @returns A hint describing the policy, `isValid` to test a password, and
 *   `validate`, a `useForm` validator returning the shared error message.
 */
export function usePasswordPolicy(accessType: MaybeRefOrGetter<string>) {
  const { t } = useI18n()
  const { serverSettings } = usePublicServerSettings()

  const requirements = computed(() =>
    buildPasswordRequirements(
      serverSettings.value.password_type,
      resolvePasswordMinLength(
        serverSettings.value.password_length_regular_users,
        serverSettings.value.password_length_admin_users,
        toValue(accessType),
      ),
    ),
  )

  const hint = computed(() =>
    requirements.value.requireUppercase
      ? t('app.password.hintStrict', { min: requirements.value.minLength })
      : t('app.password.hintLength', { min: requirements.value.minLength }),
  )

  /**
   * Tells whether a password meets the policy.
   *
   * @param password - Raw password input.
   * @returns `true` when it meets every requirement.
   */
  function isValid(password: string): boolean {
    return isValidPassword(password, requirements.value)
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

  return { hint, isValid, validate }
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
