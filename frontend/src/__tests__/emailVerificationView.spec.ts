import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import EmailVerificationView from '@/features/auth/views/EmailVerificationView.vue'
import { HttpError } from '@/services/http'

const { confirmSignUp, resendSignUpVerification, toastSuccess } = vi.hoisted(() => ({
  confirmSignUp: vi.fn<(request: unknown) => Promise<unknown>>(),
  resendSignUpVerification: vi.fn<(request: unknown) => Promise<unknown>>(),
  toastSuccess: vi.fn<(message: string) => void>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { token: 'tok' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/signUp', () => ({ confirmSignUp, resendSignUpVerification }))
vi.mock('@/composables/useToasts', () => ({ useToasts: () => ({ success: toastSuccess }) }))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ password_length_regular_users: 8 }),
    load: vi.fn<() => Promise<void>>(),
  }),
}))

const passwordRequired = () =>
  new HttpError(400, 'Bad Request', null, 'urn:endurain:error:password-required')

/**
 * Mounts the view and waits for the on-mount confirmation to settle.
 *
 * @returns The mounted wrapper.
 */
async function mountView() {
  const wrapper = mount(EmailVerificationView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('EmailVerificationView', () => {
  beforeEach(() => {
    confirmSignUp.mockReset()
    resendSignUpVerification.mockReset()
    toastSuccess.mockReset()
  })

  it('confirms on mount and shows success without a password form', async () => {
    confirmSignUp.mockResolvedValue({ admin_approval_required: false })
    const wrapper = await mountView()

    expect(confirmSignUp).toHaveBeenCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.successTitle'))
    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
  })

  it('asks for a password when required, resubmits token and password, then succeeds', async () => {
    confirmSignUp.mockRejectedValueOnce(passwordRequired())
    confirmSignUp.mockResolvedValueOnce({ admin_approval_required: true })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.choosePasswordTitle'))
    expect(wrapper.get('input[name="new-password"]').attributes('autocomplete')).toBe(
      'new-password',
    )

    await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
    await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(confirmSignUp).toHaveBeenLastCalledWith({ token: 'tok', password: 'long-enough-pass' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.successTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.adminApprovalBody'))
  })

  it('keeps the form and shows the policy error on a 422', async () => {
    confirmSignUp.mockRejectedValueOnce(passwordRequired())
    confirmSignUp.mockRejectedValueOnce(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await mountView()

    await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
    await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.errorWeakPassword'))
  })

  it('names the minimum when the server refuses a password that is too short', async () => {
    confirmSignUp.mockRejectedValueOnce(passwordRequired())
    confirmSignUp.mockRejectedValueOnce(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-too-short'),
    )
    const wrapper = await mountView()

    await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
    await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('app.password.tooShort', { min: 8 }))
  })

  it('shows the generic error, not the form, for other failures', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await mountView()

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
  })

  it('offers a new verification email when the link failed, and sends it for the typed address', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    resendSignUpVerification.mockResolvedValue({ message: 'ok' })
    const wrapper = await mountView()

    await wrapper.get('input[name="email"]').setValue('  New@Example.com ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(resendSignUpVerification).toHaveBeenCalledWith({ email: 'new@example.com' })
    expect(toastSuccess).toHaveBeenCalledWith(i18n.global.t('verifyEmail.resendSent'))
  })

  it('tells the user to wait when resending is rate limited', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    resendSignUpVerification.mockRejectedValue(new HttpError(429, 'Too Many Requests', null))
    const wrapper = await mountView()

    await wrapper.get('input[name="email"]').setValue('new@example.com')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.resendTooManyAttempts'))
  })

  it('does not offer a resend once the email is verified', async () => {
    confirmSignUp.mockResolvedValue({ admin_approval_required: false })
    const wrapper = await mountView()

    expect(wrapper.find('input[name="email"]').exists()).toBe(false)
  })
})
