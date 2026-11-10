import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import ConfirmEmailChangeView from '@/features/auth/views/ConfirmEmailChangeView.vue'
import { HttpError } from '@/services/http'

const { confirmEmailChange, routerReplace, route } = vi.hoisted(() => ({
  route: { path: '/confirm-email-change', query: {} as Record<string, unknown> },
  routerReplace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  confirmEmailChange: vi.fn<(request: unknown) => Promise<unknown>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: routerReplace }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/signUp', () => ({ confirmEmailChange }))

/**
 * Mounts the view and waits for the on-mount confirmation to settle.
 *
 * @returns The mounted wrapper.
 */
async function mountView() {
  const wrapper = mount(ConfirmEmailChangeView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ConfirmEmailChangeView', () => {
  beforeEach(() => {
    route.query = { token: 'tok', other: 'kept' }
    sessionStorage.clear()
    confirmEmailChange.mockReset()
    routerReplace.mockClear()
  })

  it('confirms on mount with the token alone and shows success', async () => {
    confirmEmailChange.mockResolvedValue({ next_step: 'sign_in' })
    const wrapper = await mountView()

    expect(confirmEmailChange).toHaveBeenCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessBody'))
    expect(wrapper.find('input').exists()).toBe(false)
    expect(sessionStorage.length).toBe(0)
  })

  it('removes the token from the address bar', async () => {
    confirmEmailChange.mockResolvedValue({ next_step: 'sign_in' })
    await mountView()

    expect(routerReplace).toHaveBeenCalledWith(
      expect.objectContaining({ query: { other: 'kept' } }),
    )
  })

  it.each([400, 404])('shows the invalid-link error, without a retry, on %i', async (status) => {
    confirmEmailChange.mockRejectedValue(
      new HttpError(status, 'Refused', null, 'urn:endurain:error:x'),
    )
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.retry'))
    expect(sessionStorage.length).toBe(0)
  })

  it('says the address is taken on a 409', async () => {
    confirmEmailChange.mockRejectedValue(new HttpError(409, 'Conflict', null))
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorEmailTaken'))
  })

  it('offers a retry that confirms with the same token after a transient failure', async () => {
    confirmEmailChange.mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    confirmEmailChange.mockResolvedValueOnce({ next_step: 'sign_in' })
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.retry'))
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(confirmEmailChange).toHaveBeenLastCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessTitle'))
  })

  it('shows the invalid-link error without calling the backend when the link has no token', async () => {
    route.query = {}
    const wrapper = await mountView()

    expect(confirmEmailChange).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
  })
})
