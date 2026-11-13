import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import ResetPasswordView from '@/features/auth/views/ResetPasswordView.vue'
import { HttpError } from '@/services/http'

const { confirmPasswordReset, validatePasswordResetToken, route } = vi.hoisted(() => ({
  validatePasswordResetToken: vi.fn<(token: string) => Promise<void>>(),
  confirmPasswordReset: vi.fn<(request: unknown) => Promise<unknown>>(),
  route: { path: '/reset-password', query: {} as Record<string, unknown> },
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: vi.fn<() => Promise<void>>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/passwordReset', () => ({
  confirmPasswordReset,
  validatePasswordResetToken,
}))
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
  await flushPromises()
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
    validatePasswordResetToken.mockReset()
    validatePasswordResetToken.mockResolvedValue(undefined)
    route.query = { token: 'tok' }
    sessionStorage.clear()
  })

  it('shows the specific message for a password built from the account details', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-matches-account'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.text()).toContain(i18n.global.t('app.password.matchesAccount'))
  })

  it('shows the specific message for the current password', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-unchanged'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.text()).toContain(i18n.global.t('app.password.unchanged'))
  })

  it('keeps the generic weak-password message for any other 422', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:validation-failed'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.errorWeakPassword'))
  })

  it('shows the strength meter under the new password only once it is typed', async () => {
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.find('[data-strength-bar]').exists()).toBe(false)

    await wrapper.get('#new-password').setValue('long-enough-pass')
    await vi.waitFor(() => expect(wrapper.find('[data-strength-bar]').exists()).toBe(true))
  })
})

describe('ResetPasswordView token across a reload', () => {
  beforeEach(() => {
    confirmPasswordReset.mockReset()
    validatePasswordResetToken.mockReset()
    validatePasswordResetToken.mockResolvedValue(undefined)
    route.query = { token: 'tok' }
    sessionStorage.clear()
  })

  it('still resets with the token after a reload dropped it from the URL', async () => {
    const first = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()
    first.unmount()

    route.query = {}
    confirmPasswordReset.mockResolvedValue({})
    await submitFilled()

    expect(confirmPasswordReset).toHaveBeenCalledWith(expect.objectContaining({ token: 'tok' }))
  })

  it('forgets the token once the password was reset', async () => {
    confirmPasswordReset.mockResolvedValue({})
    await submitFilled()

    expect(sessionStorage.length).toBe(0)
  })

  it('forgets the token when the link is refused as invalid', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    await submitFilled()

    expect(sessionStorage.length).toBe(0)
  })

  it('keeps the token while the password is only too weak', async () => {
    confirmPasswordReset.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:validation-failed'),
    )
    await submitFilled()

    expect(sessionStorage.length).toBe(1)
  })
})

describe('ResetPasswordView token validation', () => {
  beforeEach(() => {
    confirmPasswordReset.mockReset()
    validatePasswordResetToken.mockReset()
    route.query = { token: 'tok' }
    sessionStorage.clear()
  })

  it('shows a loading state, without the form, while the token is checked', async () => {
    validatePasswordResetToken.mockReturnValue(new Promise<void>(() => undefined))
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(validatePasswordResetToken).toHaveBeenCalledWith('tok')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.checkingLink'))
  })

  it('shows the form once the token is valid', async () => {
    validatePasswordResetToken.mockResolvedValue(undefined)
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(true)
    expect(sessionStorage.length).toBe(1)
  })

  it('shows the invalid-link state and forgets the token when it is refused', async () => {
    validatePasswordResetToken.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.invalidLinkTitle'))
    expect(sessionStorage.length).toBe(0)
  })

  it('does not validate when the link carries no token', async () => {
    route.query = {}
    const wrapper = mount(ResetPasswordView, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(validatePasswordResetToken).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.invalidLinkTitle'))
  })
})
