import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import EmailVerificationView from '@/features/auth/views/EmailVerificationView.vue'
import { HttpError } from '@/services/http'

const { confirmSignUp } = vi.hoisted(() => ({
  confirmSignUp: vi.fn<(request: unknown) => Promise<unknown>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { token: 'tok' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/signUp', () => ({ confirmSignUp }))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ password_type: 'length_only', password_length_regular_users: 8 }),
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

  it('shows the generic error, not the form, for other failures', async () => {
    confirmSignUp.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await mountView()

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
  })
})
