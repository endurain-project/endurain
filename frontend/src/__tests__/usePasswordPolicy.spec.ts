import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'

const serverSettings = ref({
  password_length_regular_users: 8,
  password_length_admin_users: 12,
})

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({ serverSettings }),
}))

/**
 * Runs a composable inside a mounted component, where `useI18n` works.
 *
 * @param setup - Calls the composable and returns its result.
 * @returns The composable's result.
 */
function withSetup<T>(setup: () => T): T {
  let result: T | undefined
  mount(
    defineComponent({
      setup() {
        result = setup()
        return () => h('div')
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return result as T
}

describe('usePasswordPolicy', () => {
  it('applies the length of the account tier', () => {
    const accessType = ref('regular')
    const policy = withSetup(() => usePasswordPolicy(accessType))
    expect(policy.isValid('Abcdef1!x')).toBe(true)

    accessType.value = 'admin'
    expect(policy.isValid('Abcdef1!x')).toBe(false)
    expect(policy.isValid('Abcdefgh12!x')).toBe(true)
  })

  it('describes the policy as a minimum length of the tier', () => {
    const policy = withSetup(() => usePasswordPolicy('admin'))
    expect(policy.hint.value).toBe(i18n.global.t('app.password.hintLength', { min: 12 }))
    expect(policy.minLength.value).toBe(12)
    expect(policy.isValid('abcdefghijkl')).toBe(true)
    expect(policy.isValid('abcdefghijk')).toBe(false)
  })

  it('validates with the shared message', () => {
    const policy = withSetup(() => usePasswordPolicy('regular'))
    expect(policy.validate('short')).toBe(i18n.global.t('app.password.invalid'))
    expect(policy.validate('long-enough')).toBeNull()
  })
})

describe('usePasswordConfirmation', () => {
  it('reports neither a match nor a mismatch until the confirmation is typed', () => {
    const password = ref('secret-pass')
    const confirmation = ref('')
    const result = withSetup(() => usePasswordConfirmation(password, confirmation))
    expect(result.matches.value).toBe(false)
    expect(result.error.value).toBeUndefined()

    confirmation.value = 'secret'
    expect(result.matches.value).toBe(false)
    expect(result.error.value).toBe(i18n.global.t('app.password.mismatch'))

    confirmation.value = 'secret-pass'
    expect(result.matches.value).toBe(true)
    expect(result.error.value).toBeUndefined()
  })
})

describe('usePasswordPolicy policyError', () => {
  const problem = (code: string, status = 422) =>
    new HttpError(status, 'Unprocessable', null, `urn:endurain:error:${code}`)

  it('names the minimum of the account tier for a password that is too short', () => {
    const policy = withSetup(() => usePasswordPolicy('admin'))
    expect(policy.policyError(problem('password-too-short'))).toBe(
      i18n.global.t('app.password.tooShort', { min: 12 }),
    )
    expect(i18n.global.t('app.password.tooShort', { min: 12 })).toContain('12')
  })

  it('maps a common password and a password built from the account details', () => {
    const policy = withSetup(() => usePasswordPolicy('regular'))
    expect(policy.policyError(problem('password-too-common'))).toBe(
      'This password is too common. Choose one that is harder to guess.',
    )
    expect(policy.policyError(problem('password-matches-account'))).toBe(
      "Don't use your username or email address as your password.",
    )
  })

  it('leaves every other error alone', () => {
    const policy = withSetup(() => usePasswordPolicy('regular'))
    expect(policy.policyError(problem('invalid-input'))).toBeNull()
    expect(policy.policyError(problem('password-too-common', 400))).toBeNull()
    expect(policy.policyError(new HttpError(422, 'Unprocessable'))).toBeNull()
    expect(policy.policyError(new Error('boom'))).toBeNull()
    expect(policy.policyError(undefined)).toBeNull()
  })
})
