import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import EmailVerificationView from '@/features/auth/views/EmailVerificationView.vue'
import { HttpError } from '@/services/http'

const { confirmSignUp, resendSignUpVerification, toastSuccess, routerReplace, route } = vi.hoisted(
  () => ({
    route: { path: '/verify-email', query: {} as Record<string, unknown> },
    routerReplace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
    confirmSignUp: vi.fn<(request: unknown) => Promise<unknown>>(),
    resendSignUpVerification: vi.fn<(request: unknown) => Promise<unknown>>(),
    toastSuccess: vi.fn<(message: string) => void>(),
  }),
)

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: routerReplace }),
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
    route.query = { token: 'tok', other: 'kept' }
    sessionStorage.clear()
    confirmSignUp.mockReset()
    resendSignUpVerification.mockReset()
    toastSuccess.mockReset()
    routerReplace.mockClear()
  })

  it('confirms on mount and shows success without a password form', async () => {
    confirmSignUp.mockResolvedValue({ admin_approval_required: false })
    const wrapper = await mountView()

    expect(confirmSignUp).toHaveBeenCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.successTitle'))
    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
  })

  it('removes the token from the address bar and still confirms with it, even on a retry', async () => {
    confirmSignUp.mockRejectedValueOnce(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    confirmSignUp.mockResolvedValueOnce({ admin_approval_required: false })
    const wrapper = await mountView()

    expect(routerReplace).toHaveBeenCalledWith(
      expect.objectContaining({ query: { other: 'kept' } }),
    )
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(confirmSignUp).toHaveBeenLastCalledWith({ token: 'tok' })
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

  it('still confirms with the token after a reload dropped it from the URL', async () => {
    confirmSignUp.mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    ;(await mountView()).unmount()
    confirmSignUp.mockReset()
    confirmSignUp.mockResolvedValue({ admin_approval_required: false })

    route.query = {}
    await mountView()

    expect(confirmSignUp).toHaveBeenCalledWith({ token: 'tok' })
  })

  it('forgets the token once the sign-up was confirmed', async () => {
    confirmSignUp.mockResolvedValue({ admin_approval_required: false })
    await mountView()

    expect(sessionStorage.length).toBe(0)
  })

  it.each([400, 404])('forgets the token when the link is refused with %i', async (status) => {
    confirmSignUp.mockRejectedValue(new HttpError(status, 'Refused', null, 'urn:endurain:error:x'))
    await mountView()

    expect(sessionStorage.length).toBe(0)
  })

  it('keeps the token while a password is still being chosen', async () => {
    confirmSignUp.mockRejectedValue(passwordRequired())
    await mountView()

    expect(sessionStorage.length).toBe(1)
  })
})
