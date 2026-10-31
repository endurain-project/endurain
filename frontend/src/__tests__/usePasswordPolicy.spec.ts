import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'

const serverSettings = ref({
  password_type: 'strict',
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

  it('describes the strict or the length-only policy with the tier length', () => {
    const policy = withSetup(() => usePasswordPolicy('admin'))
    expect(policy.hint.value).toBe(i18n.global.t('app.password.hintStrict', { min: 12 }))

    serverSettings.value = { ...serverSettings.value, password_type: 'length_only' }
    expect(policy.hint.value).toBe(i18n.global.t('app.password.hintLength', { min: 12 }))
    expect(policy.isValid('abcdefghijkl')).toBe(true)
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
