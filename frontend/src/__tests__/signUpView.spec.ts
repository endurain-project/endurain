import { computed, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import SignUpView from '@/features/auth/views/SignUpView.vue'

const { push, replace, requestSignUp, requireVerification } = vi.hoisted(() => ({
  push: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  replace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  requestSignUp: vi.fn<(request: unknown) => Promise<unknown>>(),
  requireVerification: { value: false },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@/features/auth/services/signUp', () => ({ requestSignUp }))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: computed(() => ({
      signup_enabled: true,
      signup_require_email_verification: requireVerification.value,
      password_type: 'length_only',
      password_length_regular_users: 8,
      units: 'metric',
      currency: 'euro',
    })),
    isSettingsLoading: ref(false),
    loginImageUrl: ref('/login.png'),
    load: vi.fn<() => Promise<void>>(),
  }),
}))

/**
 * Mounts the view and fills the identity fields.
 *
 * @returns The mounted wrapper.
 */
async function mountFilled() {
  const wrapper = mount(SignUpView, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  await flushPromises()
  await wrapper.get('input[name="name"]').setValue('Ada Lovelace')
  await wrapper.get('input[name="username"]').setValue('Ada')
  await wrapper.get('input[name="email"]').setValue('Ada@Example.com')
  return wrapper
}

describe('SignUpView', () => {
  beforeEach(() => {
    requestSignUp.mockReset()
    requestSignUp.mockResolvedValue({ email_verification_required: true })
    push.mockClear()
  })

  it('hides the password fields, shows the hint and sends no password when verification is required', async () => {
    requireVerification.value = true
    const wrapper = await mountFilled()

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)
    expect(wrapper.find('input[name="confirm-password"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('signup.passwordByEmailHint'))
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const payload = requestSignUp.mock.calls[0]?.[0] as Record<string, unknown>
    expect(payload).not.toHaveProperty('password')
    expect(payload.email).toBe('ada@example.com')
  })

  it('shows the password fields and sends the password when verification is not required', async () => {
    requireVerification.value = false
    const wrapper = await mountFilled()

    expect(wrapper.text()).not.toContain(i18n.global.t('signup.passwordByEmailHint'))
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('input[name="new-password"]').setValue('long-enough-pass')
    await wrapper.get('input[name="confirm-password"]').setValue('long-enough-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(requestSignUp.mock.calls[0]?.[0]).toMatchObject({ password: 'long-enough-pass' })
  })

  it('asks only for the account fields', async () => {
    requireVerification.value = true
    const wrapper = await mountFilled()

    const fields = wrapper.findAll('input, select').map((field) => field.attributes('name'))
    expect(fields).toEqual(['name', 'username', 'email'])

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const payload = requestSignUp.mock.calls[0]?.[0] as Record<string, unknown>
    expect(Object.keys(payload).sort()).toEqual(['email', 'name', 'preferred_language', 'username'])
  })

  it('sends the language the form is shown in', async () => {
    requireVerification.value = true
    i18n.global.locale.value = 'pt-PT'
    try {
      const wrapper = await mountFilled()
      await wrapper.get('form').trigger('submit')
      await flushPromises()
    } finally {
      i18n.global.locale.value = 'en'
    }

    expect(requestSignUp.mock.calls[0]?.[0]).toMatchObject({ preferred_language: 'pt-PT' })
  })
})
