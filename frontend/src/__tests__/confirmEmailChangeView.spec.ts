import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import ConfirmEmailChangeView from '@/features/auth/views/ConfirmEmailChangeView.vue'
import { HttpError } from '@/services/http'

const { confirmEmailChange, routerReplace, route } = vi.hoisted(() => ({
  route: { path: '/confirm-email-change', query: {} as Record<string, unknown>, hash: '' },
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
 * Mounts the view.
 *
 * @returns The mounted wrapper after mount-time work settled.
 */
async function mountView() {
  const wrapper = mount(ConfirmEmailChangeView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('ConfirmEmailChangeView', () => {
  beforeEach(() => {
    route.query = {}
    route.hash = '#token=tok'
    sessionStorage.clear()
    confirmEmailChange.mockReset()
    routerReplace.mockClear()
  })

  it('asks for confirmation and changes nothing on load', async () => {
    const wrapper = await mountView()

    expect(confirmEmailChange).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.confirmChangeTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.confirmChangeBody'))
  })

  it('confirms with the token alone when the button is pressed and shows success', async () => {
    confirmEmailChange.mockResolvedValue(undefined)
    const wrapper = await mountView()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(confirmEmailChange).toHaveBeenCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessBody'))
    expect(wrapper.find('input').exists()).toBe(false)
    expect(sessionStorage.length).toBe(0)
  })

  it('removes the token from the address bar', async () => {
    route.query = { other: 'kept' }
    await mountView()

    expect(routerReplace).toHaveBeenCalledWith({ query: { other: 'kept' }, hash: '' })
  })

  it('still reads the token of a link sent with it in the query string', async () => {
    route.hash = ''
    route.query = { token: 'old-link' }
    confirmEmailChange.mockResolvedValue(undefined)
    const wrapper = await mountView()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(confirmEmailChange).toHaveBeenCalledWith({ token: 'old-link' })
    expect(routerReplace).toHaveBeenCalledWith({ query: {}, hash: '' })
  })

  it.each([
    [400, 'invalid-input'],
    [404, 'not-found'],
  ])('shows the invalid-link error, without a retry, on %i', async (status, code) => {
    confirmEmailChange.mockRejectedValue(
      new HttpError(status, 'Refused', null, `urn:endurain:error:${code}`),
    )
    const wrapper = await mountView()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
    expect(wrapper.text()).not.toContain(i18n.global.t('verifyEmail.retry'))
    expect(sessionStorage.length).toBe(0)
  })

  it('says the address is taken on a 409', async () => {
    confirmEmailChange.mockRejectedValue(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'),
    )
    const wrapper = await mountView()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorEmailTaken'))
  })

  it('offers a retry that confirms with the same token after a transient failure', async () => {
    confirmEmailChange.mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    confirmEmailChange.mockResolvedValueOnce({ next_step: 'sign_in' })
    const wrapper = await mountView()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.retry'))
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(confirmEmailChange).toHaveBeenLastCalledWith({ token: 'tok' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.emailChangeSuccessTitle'))
  })

  it('shows the invalid-link error without calling the backend when the link has no token', async () => {
    route.hash = ''
    const wrapper = await mountView()

    expect(confirmEmailChange).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
  })

  it('needs the link again after a reload: the token is not kept anywhere', async () => {
    await mountView()
    route.hash = ''
    const reloaded = await mountView()

    expect(reloaded.text()).toContain(i18n.global.t('verifyEmail.errorInvalidToken'))
    expect(sessionStorage.length).toBe(0)
  })
})
