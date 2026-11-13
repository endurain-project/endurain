import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import SignUpConfirmView from '@/features/auth/views/SignUpConfirmView.vue'
import { HttpError } from '@/services/http'

const { confirmSignUp, resendSignUpVerification, toastSuccess, routerReplace, route } = vi.hoisted(
  () => ({
    route: { path: '/signup/confirm', query: {} as Record<string, unknown> },
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

/**
 * Mounts the view and waits for it to settle.
 *
 * @returns The mounted wrapper.
 */
async function mountView() {
  const wrapper = mount(SignUpConfirmView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

/**
 * Types a password twice and submits the form.
 *
 * @param wrapper - The mounted view.
 */
async function submitPassword(wrapper: Awaited<ReturnType<typeof mountView>>) {
  await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
  await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('SignUpConfirmView', () => {
  beforeEach(() => {
    route.query = { token: 'tok', other: 'kept' }
    sessionStorage.clear()
    confirmSignUp.mockReset()
    resendSignUpVerification.mockReset()
    toastSuccess.mockReset()
    routerReplace.mockClear()
  })

  it('asks for the password at once, without calling the backend first', async () => {
    const wrapper = await mountView()

    expect(confirmSignUp).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.choosePasswordTitle'))
    expect(wrapper.get('input[name="new-password"]').attributes('autocomplete')).toBe(
      'new-password',
    )
  })

  it('removes the token from the address bar and still confirms with it', async () => {
    confirmSignUp.mockResolvedValue({ next_step: 'sign_in' })
    const wrapper = await mountView()

    expect(routerReplace).toHaveBeenCalledWith(
      expect.objectContaining({ query: { other: 'kept' } }),
    )
    await submitPassword(wrapper)

    expect(confirmSignUp).toHaveBeenCalledWith({ token: 'tok', password: 'long-enough-pass' })
  })

  it('shows success for the next step sign_in', async () => {
    confirmSignUp.mockResolvedValue({ next_step: 'sign_in' })
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.successTitle'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.adminApprovalBody'))
  })

  it('tells the user to wait for an administrator for the next step await_approval', async () => {
    confirmSignUp.mockResolvedValue({ next_step: 'await_approval' })
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.successTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.adminApprovalBody'))
  })

  it('keeps the form and shows the policy error on a 422', async () => {
    confirmSignUp.mockRejectedValueOnce(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:validation-failed'),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(i18n.global.t('resetPassword.errorWeakPassword'))
  })

  it('names the minimum when the server refuses a password that is too short', async () => {
    confirmSignUp.mockRejectedValueOnce(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-too-short'),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('app.password.tooShort', { min: 8 }))
  })

  it('keeps the form for a transient failure so the same password can be sent again', async () => {
    confirmSignUp.mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorGeneral'))
  })

  it('shows the invalid-link error and offers a new email when the link is refused', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    resendSignUpVerification.mockResolvedValue({ next_step: 'check_email' })
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.retry'))

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
    resendSignUpVerification.mockRejectedValue(
      new HttpError(429, 'Too Many Requests', null, 'urn:endurain:error:rate-limited'),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    await wrapper.get('input[name="email"]').setValue('new@example.com')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.resendTooManyAttempts'))
  })

  it('says email verification is off when the server has it disabled', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(403, 'Forbidden', null, 'urn:endurain:error:email-verification-disabled'),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorVerificationDisabled'))
  })

  it('says sign-up is turned off, without offering a resend, when the server refuses the confirmation', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(403, 'Forbidden', null, 'urn:endurain:error:permission-denied'),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('signup.errorSignupDisabled'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.errorGeneral'))
    expect(wrapper.find('input[name="email"]').exists()).toBe(false)
  })

  it('says sign-up is turned off when the server refuses a new email', async () => {
    route.query = {}
    resendSignUpVerification.mockRejectedValue(
      new HttpError(403, 'Forbidden', null, 'urn:endurain:error:permission-denied'),
    )
    const wrapper = await mountView()

    await wrapper.get('input[name="email"]').setValue('new@example.com')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('signup.errorSignupDisabled'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.resendError'))
  })

  it('does not offer a resend once the sign-up is confirmed', async () => {
    confirmSignUp.mockResolvedValue({ next_step: 'sign_in' })
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(wrapper.find('input[name="email"]').exists()).toBe(false)
  })

  it('keeps the token after a reload dropped it from the URL', async () => {
    ;(await mountView()).unmount()
    confirmSignUp.mockResolvedValue({ next_step: 'sign_in' })

    route.query = {}
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(confirmSignUp).toHaveBeenCalledWith({ token: 'tok', password: 'long-enough-pass' })
  })

  it('forgets the token once the sign-up was confirmed', async () => {
    confirmSignUp.mockResolvedValue({ next_step: 'sign_in' })
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(sessionStorage.length).toBe(0)
  })

  it.each([
    [400, 'invalid-input'],
    [404, 'not-found'],
  ])('forgets the token when the link is refused with %i', async (status, code) => {
    confirmSignUp.mockRejectedValue(
      new HttpError(status, 'Refused', null, `urn:endurain:error:${code}`),
    )
    const wrapper = await mountView()
    await submitPassword(wrapper)

    expect(sessionStorage.length).toBe(0)
  })

  it('shows the resend form without an error when the link has no token', async () => {
    route.query = {}
    const wrapper = await mountView()

    expect(confirmSignUp).not.toHaveBeenCalled()
    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.resendTitle'))
    expect(wrapper.find('input[name="email"]').exists()).toBe(true)
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.backToLogin'))
  })
})
