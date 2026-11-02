import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import LoginView from '@/features/auth/views/LoginView.vue'

const { query } = vi.hoisted(() => ({ query: { value: {} as Record<string, string> } }))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ local_login_enabled: true, signup_enabled: true, sso_enabled: false }),
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
    processSsoCallback: vi.fn<() => Promise<{ status: string }>>(() =>
      Promise.resolve({ status: 'none' }),
    ),
    completeSsoMfa: vi.fn<() => Promise<void>>(),
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
  useRoute: () => ({ query: query.value, fullPath: '/login' }),
  useRouter: () => ({ replace: vi.fn<() => void>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

/**
 * Mounts the login view for the current mocked query.
 *
 * @returns The mounted wrapper.
 */
function mountView() {
  return mount(LoginView, {
    global: {
      plugins: [i18n],
      stubs: { AuthScreenLayout: { template: '<div><slot /></div>' } },
    },
  })
}

describe('LoginView resend verification link', () => {
  it('is offered after a sign-up that sent a verification email', () => {
    query.value = { emailVerificationSent: 'true' }

    expect(mountView().text()).toContain(i18n.global.t('login.resendVerification'))
  })

  it('is not offered otherwise', () => {
    query.value = {}

    expect(mountView().text()).not.toContain(i18n.global.t('login.resendVerification'))
  })
})
