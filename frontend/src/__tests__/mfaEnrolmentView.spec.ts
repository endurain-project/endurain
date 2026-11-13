import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import i18n from '@/i18n'
import { useAuthStore } from '@/features/auth/stores/auth'
import MfaEnrolmentView from '@/features/security/views/MfaEnrolmentView.vue'

const mocks = vi.hoisted(() => ({
  push: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  signOut: vi.fn<() => Promise<void>>(() => Promise.resolve()),
  invalidateQueries: vi.fn<() => Promise<void>>(() => Promise.resolve()),
  profileError: false,
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('@tanstack/vue-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/vue-query')>()),
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))
vi.mock('@/features/auth/composables/useSignOut', () => ({
  useSignOut: () => ({ signOut: mocks.signOut }),
}))

const mfaStatus = ref<{ enabled: boolean } | undefined>({ enabled: false })
vi.mock('@/features/security/composables/useSecurity', () => ({
  useMfaStatusQuery: () => ({ data: mfaStatus }),
}))
vi.mock('@/features/profile/composables/useProfile', () => ({
  useProfileQuery: () => ({
    data: ref(mocks.profileError ? undefined : { hasLocalPassword: false }),
    isPending: ref(false),
    isError: ref(mocks.profileError),
    refetch: vi.fn<() => void>(),
  }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  consumeIdpStepUpReturn: () => null,
}))

const MfaCardStub = {
  props: ['hasLocalPassword', 'resume'],
  template: '<div data-test="mfa-card">{{ hasLocalPassword }}</div>',
}

function mountView() {
  return mount(MfaEnrolmentView, {
    global: { plugins: [i18n], stubs: { MfaCard: MfaCardStub } },
  })
}

describe('MfaEnrolmentView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mfaStatus.value = { enabled: false }
    mocks.profileError = false
    useAuthStore().requireMfaEnrolment()
  })

  it('explains that the server requires MFA', () => {
    const wrapper = mountView()

    expect(wrapper.get('h1').text()).toBe('Set up two-step verification')
    expect(wrapper.text()).toContain('This server requires two-step verification')
  })

  it('reuses the MFA card, telling it whether the account has a local password', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="mfa-card"]').text()).toBe('false')
  })

  it('lets the user sign out instead', async () => {
    const wrapper = mountView()

    await wrapper.get('[data-test="sign-out"]').trigger('click')

    expect(mocks.signOut).toHaveBeenCalledOnce()
  })

  it('offers no way on until MFA is set up, and keeps the app closed', () => {
    const wrapper = mountView()

    expect(wrapper.find('[data-test="continue"]').exists()).toBe(false)
    expect(useAuthStore().mfaEnrolmentRequired).toBe(true)
  })

  it('opens the app again once MFA is set up, and goes on when the user continues', async () => {
    mfaStatus.value = { enabled: true }
    const wrapper = mountView()
    await flushPromises()

    expect(useAuthStore().mfaEnrolmentRequired).toBe(false)

    await wrapper.get('[data-test="continue"]').trigger('click')
    await flushPromises()

    // Requests the server refused meanwhile are asked again before the app is shown.
    expect(mocks.invalidateQueries).toHaveBeenCalledOnce()
    expect(mocks.push).toHaveBeenCalledWith({ name: 'home' })
  })

  it('says so when the account cannot be read, and does not show the card', async () => {
    mocks.profileError = true
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="mfa-card"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="sign-out"]').exists()).toBe(true)
  })
})
