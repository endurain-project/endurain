import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import OnboardingView from '@/features/auth/views/OnboardingView.vue'
import { HttpError } from '@/services/http'

const { replace, completeOnboarding, toastError } = vi.hoisted(() => ({
  replace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  completeOnboarding: vi.fn<(request: unknown) => Promise<void>>(),
  toastError: vi.fn<(message: string) => void>(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))
vi.mock('@/features/auth/services/onboarding', () => ({ completeOnboarding }))
vi.mock('@/composables/useToasts', () => ({ useToasts: () => ({ error: toastError }) }))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ password_type: 'length_only', password_length_admin_users: 12 }),
    loginImageUrl: ref('/login.png'),
    load: vi.fn<() => Promise<void>>(),
  }),
}))

/**
 * Mounts the view and fills every field with valid values.
 *
 * @returns The mounted wrapper, ready to submit.
 */
async function mountFilled() {
  const wrapper = mount(OnboardingView, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  await wrapper.get('input[name="setup-token"]').setValue(' tok ')
  await wrapper.get('input[name="name"]').setValue('Ada Lovelace')
  await wrapper.get('input[name="username"]').setValue('Ada')
  await wrapper.get('input[name="email"]').setValue('Ada@Example.com')
  await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
  await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
  return wrapper
}

describe('OnboardingView', () => {
  beforeEach(() => {
    replace.mockClear()
    completeOnboarding.mockReset()
    toastError.mockClear()
  })

  it('keeps submit disabled until the admin password policy is met and confirmed', async () => {
    const wrapper = await mountFilled()
    const submit = wrapper.get('button[type="submit"]')
    expect(submit.attributes('disabled')).toBeUndefined()

    await wrapper.get('input[name="new-password"]').setValue('short')
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('explains a password that misses the policy once the field is left', async () => {
    const wrapper = await mountFilled()
    const password = wrapper.get('input[name="new-password"]')
    await password.setValue('short')
    await password.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('app.password.invalid'))
  })

  it('submits normalised values and redirects to login with the success flag', async () => {
    completeOnboarding.mockResolvedValue()
    const wrapper = await mountFilled()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(completeOnboarding.mock.calls[0]?.[0]).toEqual({
      token: 'tok',
      name: 'Ada Lovelace',
      username: 'ada',
      email: 'ada@example.com',
      password: 'long-enough-pass',
    })
    expect(replace).toHaveBeenCalledWith({ name: 'login', query: { onboardingComplete: 'true' } })
  })

  it.each([
    [400, 'The setup token is invalid'],
    [422, 'The details were rejected'],
    [429, 'Too many attempts'],
    [503, 'temporarily unavailable'],
    [500, 'Could not create the administrator'],
  ])('shows a message for a %i response and stays on the page', async (status, text) => {
    completeOnboarding.mockRejectedValue(new HttpError(status, 'err'))
    const wrapper = await mountFilled()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(text)
    expect(replace).not.toHaveBeenCalled()
  })

  it('explains and redirects to login when an account already exists', async () => {
    completeOnboarding.mockRejectedValue(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'),
    )
    const wrapper = await mountFilled()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('already complete'))
    expect(replace).toHaveBeenCalledWith({ name: 'login' })
  })
})
