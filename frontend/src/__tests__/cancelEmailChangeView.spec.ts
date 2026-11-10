import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import CancelEmailChangeView from '@/features/auth/views/CancelEmailChangeView.vue'
import { HttpError } from '@/services/http'

const { cancelEmailChange, routerReplace, route } = vi.hoisted(() => ({
  route: { path: '/cancel-email-change', query: {} as Record<string, unknown> },
  routerReplace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  cancelEmailChange: vi.fn<(request: unknown) => Promise<void>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: routerReplace }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/emailChange', () => ({ cancelEmailChange }))

/**
 * Mounts the view.
 *
 * @returns The mounted wrapper after mount-time work settled.
 */
async function mountView() {
  const wrapper = mount(CancelEmailChangeView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('CancelEmailChangeView', () => {
  beforeEach(() => {
    route.query = { token: '7.123.abc' }
    sessionStorage.clear()
    cancelEmailChange.mockReset()
    routerReplace.mockClear()
  })

  it('asks for confirmation and changes nothing on load', async () => {
    const wrapper = await mountView()

    expect(cancelEmailChange).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelTitle'))
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('cancels with the token from the link and says what ended', async () => {
    cancelEmailChange.mockResolvedValue(undefined)
    const wrapper = await mountView()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(cancelEmailChange).toHaveBeenCalledWith({ token: '7.123.abc' })
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelledTitle'))
    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelledBody'))
  })

  it('removes the token from the address bar', async () => {
    await mountView()

    expect(routerReplace).toHaveBeenCalled()
  })

  it('shows that the link is no longer valid when the server refuses it', async () => {
    cancelEmailChange.mockRejectedValue(new HttpError(400, 'Bad Request', null, null))
    const wrapper = await mountView()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelInvalidTitle'))
  })

  it('shows a retryable error when the request fails for another reason', async () => {
    cancelEmailChange.mockRejectedValue(new HttpError(500, 'Server Error', null, null))
    const wrapper = await mountView()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelError'))
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('shows the invalid state without a token', async () => {
    route.query = {}
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('verifyEmail.cancelInvalidTitle'))
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
