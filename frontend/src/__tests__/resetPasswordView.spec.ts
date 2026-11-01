import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import ResetPasswordView from '@/features/auth/views/ResetPasswordView.vue'
import { HttpError } from '@/services/http'

const { confirmPasswordReset } = vi.hoisted(() => ({
  confirmPasswordReset: vi.fn<(request: unknown) => Promise<unknown>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { token: 'tok' } }),
  useRouter: () => ({ replace: vi.fn<() => Promise<void>>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/passwordReset', () => ({ confirmPasswordReset }))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ password_length_regular_users: 8 }),
    load: vi.fn<() => Promise<void>>(),
  }),
}))

/**
 * Submits the reset form with a password that passes the length check.
 *
 * @returns The mounted wrapper after the submit settled.
 */
async function submitFilled() {
  const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
  await wrapper.get('#new-password').setValue('long-enough-pass')
  await wrapper
    .get('input[autocomplete="new-password"]:not(#new-password)')
    .setValue('long-enough-pass')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

describe('ResetPasswordView weak password', () => {
  beforeEach(() => {
    confirmPasswordReset.mockReset()
  })

  it('shows the specific message for a password built from the account details', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-matches-account'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.text()).toContain(i18n.global.t('app.password.matchesAccount'))
  })

  it('keeps the generic weak-password message for any other 422', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.errorWeakPassword'))
  })

  it('shows the strength meter under the new password only once it is typed', async () => {
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    expect(wrapper.find('[data-strength-bar]').exists()).toBe(false)

    await wrapper.get('#new-password').setValue('long-enough-pass')
    await vi.waitFor(() => expect(wrapper.find('[data-strength-bar]').exists()).toBe(true))
  })
})
