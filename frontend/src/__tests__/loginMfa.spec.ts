import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import { normalizeMfaCode } from '@/features/auth/utils/mfaCode'
import LoginView from '@/features/auth/views/LoginView.vue'

const { auth, sso } = vi.hoisted(() => ({
  auth: {
    login: vi.fn<(u: string, p: string) => Promise<unknown>>(),
    verifyMfa: vi.fn<(challenge: string, code: string) => Promise<unknown>>(),
  },
  sso: {
    processSsoCallback: vi.fn<() => Promise<{ status: string }>>(),
    completeSsoMfa: vi.fn<(code: string) => Promise<void>>(),
  },
}))

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
    processSsoCallback: sso.processSsoCallback,
    completeSsoMfa: sso.completeSsoMfa,
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

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => auth }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, fullPath: '/login' }),
  useRouter: () => ({ replace: vi.fn<() => void>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

function mountView() {
  return mount(LoginView, {
    global: {
      plugins: [i18n],
      stubs: { AuthScreenLayout: { template: '<div><slot /></div>' } },
    },
  })
}

type Wrapper = ReturnType<typeof mountView>

/** Signs in with a password so the view is on the MFA step. */
async function toMfaStep(wrapper: Wrapper): Promise<void> {
  auth.login.mockResolvedValue({ status: 'mfa-required', challenge: 'chal' })
  await wrapper.find('input[name="username"]').setValue('user')
  await wrapper.find('input[type="password"]').setValue('secret')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

async function submitCode(wrapper: Wrapper, code: string): Promise<void> {
  await wrapper.find('input[name="mfaCode"]').setValue(code)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('normalizeMfaCode', () => {
  it.each(['a3k97bdf', 'A3K9 7BDF', 'a3k9-7bdf', '  a3k9 - 7bdf '])(
    'formats %j as a backup code',
    (raw) => {
      expect(normalizeMfaCode(raw)).toBe('A3K9-7BDF')
    },
  )

  it('strips the space of a grouped authenticator code', () => {
    expect(normalizeMfaCode('022 643')).toBe('022643')
  })
})

describe('LoginView MFA step', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.verifyMfa.mockResolvedValue({ status: 'authenticated' })
    sso.processSsoCallback.mockResolvedValue({ status: 'none' })
  })

  it.each(['a3k97bdf', 'A3K9 7BDF', 'a3k9-7bdf'])('sends %j as A3K9-7BDF', async (raw) => {
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, raw)

    expect(auth.verifyMfa).toHaveBeenCalledWith('chal', 'A3K9-7BDF')
  })

  it('sends a backup code typed after an SSO callback in the same format', async () => {
    sso.processSsoCallback.mockResolvedValue({ status: 'mfa-required' })
    const wrapper = mountView()
    await flushPromises()

    await submitCode(wrapper, 'a3k97bdf')

    expect(sso.completeSsoMfa).toHaveBeenCalledWith('A3K9-7BDF')
  })

  it('reports a 422 from the MFA step as an invalid code', async () => {
    auth.verifyMfa.mockRejectedValue(new HttpError(422, 'Unprocessable Content'))
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '12')

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidMfa'))
  })

  it('keeps the MFA step and reports an invalid code on a 400', async () => {
    auth.verifyMfa.mockRejectedValue(new HttpError(400, 'Bad Request'))
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.find('input[name="mfaCode"]').exists()).toBe(true)
  })

  it('returns to the sign-in form with an expiry message on a 401', async () => {
    auth.verifyMfa.mockRejectedValue(new HttpError(401, 'Unauthorized'))
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.mfaChallengeExpired'))
    expect(wrapper.text()).not.toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.find('input[name="mfaCode"]').exists()).toBe(false)
    expect(wrapper.find('input[name="username"]').exists()).toBe(true)
  })

  it('keeps a 401 on the SSO MFA step an invalid code', async () => {
    sso.processSsoCallback.mockResolvedValue({ status: 'mfa-required' })
    sso.completeSsoMfa.mockRejectedValue(new HttpError(401, 'Unauthorized'))
    const wrapper = mountView()
    await flushPromises()

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.text()).not.toContain(i18n.global.t('login.mfaChallengeExpired'))
  })
})

describe('LoginView password step errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sso.processSsoCallback.mockResolvedValue({ status: 'none' })
  })

  async function submitPassword(status: number) {
    auth.login.mockRejectedValue(new HttpError(status, 'Refused'))
    const wrapper = mountView()
    await wrapper.find('input[name="username"]').setValue('user')
    await wrapper.find('input[type="password"]').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    return wrapper
  }

  it('hints at a pending account when the credentials are refused', async () => {
    const wrapper = await submitPassword(401)

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidCredentials'))
    expect(wrapper.text()).toContain(i18n.global.t('login.invalidCredentialsPendingHint'))
  })

  it.each([
    [429, 'login.tooManyAttemptsWait'],
    [503, 'login.unavailableWait'],
  ])('tells the user how long to wait after a %i', async (status, key) => {
    auth.login.mockRejectedValue(new HttpError(status, 'Refused', null, null, null, [], 42))
    const wrapper = mountView()
    await wrapper.find('input[name="username"]').setValue('user')
    await wrapper.find('input[type="password"]').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t(key, { seconds: 42 }))
  })

  it.each([403, 429])('does not add the hint to a %i', async (status) => {
    const wrapper = await submitPassword(status)

    expect(wrapper.text()).not.toContain(i18n.global.t('login.invalidCredentialsPendingHint'))
  })
})
