import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import LoginView from '@/features/auth/views/LoginView.vue'

const target = 'endurain://native-callback?session_id=00000000-0000-4000-8000-0000000000f2'
const continueAppHandoff = vi.hoisted(() => vi.fn<(target: string) => Promise<void>>())

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ local_login_enabled: true, signup_enabled: false, sso_enabled: false }),
    ssoProviders: ref([]),
    isSettingsLoading: ref(false),
    isSsoLoading: ref(false),
    loginImageUrl: ref(''),
    load: vi.fn<() => Promise<void>>(() => Promise.resolve()),
  }),
}))

vi.mock('@/features/config/composables/useAppConfig', () => ({
  useAppConfig: () => ({ config: ref({ branding: { appName: 'Endurain' } }) }),
}))

vi.mock('@/features/auth/composables/useSsoLogin', () => ({
  useSsoLogin: () => ({
    startSsoLogin: vi.fn<() => Promise<void>>(),
    processSsoCallback: vi.fn<() => Promise<{ status: string; target: string }>>(() =>
      Promise.resolve({ status: 'app-handoff', target }),
    ),
    continueAppHandoff,
    maybeAutoRedirect: vi.fn<() => void>(),
  }),
}))

vi.mock('@/features/auth/composables/useLoginRouteMessages', () => ({
  useLoginRouteMessages: () => ({
    resolveInitialAlert: () => null,
    shouldForceLocalLogin: () => false,
  }),
}))

vi.mock('@/composables/useSafeRedirect', () => ({
  useSafeRedirect: () => ({ navigateAfterLogin: vi.fn<() => Promise<void>>() }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, fullPath: '/login' }),
  useRouter: () => ({ replace: vi.fn<() => void>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountLogin() {
  return mount(LoginView, {
    global: {
      plugins: [i18n],
      stubs: { AuthScreenLayout: { template: '<div><slot /></div>' } },
    },
  })
}

describe('LoginView native app hand-off', () => {
  it('asks for confirmation and hands the session over only on Continue', async () => {
    const wrapper = mountLogin()
    await flushPromises()

    expect(wrapper.find('[role="alertdialog"]').text()).toContain('endurain://native-callback')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(continueAppHandoff).not.toHaveBeenCalled()

    const buttons = wrapper.findAll('[role="alertdialog"] button')
    await buttons[0]!.trigger('click')
    expect(continueAppHandoff).toHaveBeenCalledWith(target)
  })

  it('drops the hand-off on Cancel and shows the sign-in form', async () => {
    continueAppHandoff.mockClear()
    const wrapper = mountLogin()
    await flushPromises()

    const buttons = wrapper.findAll('[role="alertdialog"] button')
    await buttons[1]!.trigger('click')

    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(true)
    expect(continueAppHandoff).not.toHaveBeenCalled()
  })
})
