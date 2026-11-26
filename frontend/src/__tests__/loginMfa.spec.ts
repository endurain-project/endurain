import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import { normalizeMfaCode } from '@/features/auth/utils/mfaCode'
import LoginView from '@/features/auth/views/LoginView.vue'

const { auth, sso, settings } = vi.hoisted(() => ({
  auth: {
    login: vi.fn<(u: string, p: string) => Promise<unknown>>(),
    verifyMfa: vi.fn<(challenge: string, code: string) => Promise<unknown>>(),
  },
  sso: {
    processSsoCallback: vi.fn<() => Promise<unknown>>(),
  },
  settings: { local: true, sso: false },
}))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({
      local_login_enabled: settings.local,
      signup_enabled: false,
      sso_enabled: settings.sso,
    }),
    ssoProviders: ref(settings.sso ? [{ slug: 'acme', name: 'Acme', icon: null }] : []),
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

/** The SSO callback of an account with MFA, which continues at the MFA step. */
const SSO_MFA_STEP = {
  status: 'next-step',
  result: { status: 'mfa-required', challenge: 'sso-chal' },
}

const SESSION_ENDED = new HttpError(401, 'Unauthorized', null, 'urn:endurain:error:session-ended')

/** Types a code; a whole code submits the form by itself. */
async function submitCode(wrapper: Wrapper, code: string): Promise<void> {
  await wrapper.find('#login-mfa-code').setValue(code)
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
    settings.local = true
    settings.sso = false
    auth.verifyMfa.mockResolvedValue({ status: 'authenticated' })
    sso.processSsoCallback.mockResolvedValue({ status: 'none' })
  })

  it.each(['a3k97bdf', 'A3K9 7BDF', 'a3k9-7bdf'])('sends %j as A3K9-7BDF', async (raw) => {
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, raw)

    expect(auth.verifyMfa).toHaveBeenCalledWith('chal', 'A3K9-7BDF')
  })

  it('verifies the code of an SSO sign-in with the challenge the exchange returned', async () => {
    sso.processSsoCallback.mockResolvedValue(SSO_MFA_STEP)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('login.mfaRequired'))
    await submitCode(wrapper, 'a3k97bdf')

    expect(auth.verifyMfa).toHaveBeenCalledWith('sso-chal', 'A3K9-7BDF')
  })

  it('reports a validation failure from the MFA step as a generic error', async () => {
    auth.verifyMfa.mockRejectedValue(
      new HttpError(422, 'Unprocessable Content', null, 'urn:endurain:error:validation-failed'),
    )
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.genericError'))
    expect(wrapper.text()).not.toContain(i18n.global.t('login.invalidMfa'))
  })

  it('keeps the MFA step and reports an invalid code on an invalid-mfa-code', async () => {
    auth.verifyMfa.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-mfa-code'),
    )
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.find('#login-mfa-code').exists()).toBe(true)
  })

  it('returns to the sign-in form with an expiry message when the sign-in has ended', async () => {
    auth.verifyMfa.mockRejectedValue(SESSION_ENDED)
    const wrapper = mountView()
    await toMfaStep(wrapper)

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.mfaChallengeExpired'))
    expect(wrapper.text()).not.toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.find('#login-mfa-code').exists()).toBe(false)
    expect(wrapper.find('input[name="username"]').exists()).toBe(true)
  })

  it('keeps a wrong code on the SSO MFA step an invalid code', async () => {
    sso.processSsoCallback.mockResolvedValue(SSO_MFA_STEP)
    auth.verifyMfa.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-mfa-code'),
    )
    const wrapper = mountView()
    await flushPromises()

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.invalidMfa'))
    expect(wrapper.text()).not.toContain(i18n.global.t('login.mfaChallengeExpired'))
    expect(wrapper.find('#login-mfa-code').exists()).toBe(true)
  })

  it('returns an ended SSO MFA step to the provider buttons', async () => {
    settings.local = false
    settings.sso = true
    sso.processSsoCallback.mockResolvedValue(SSO_MFA_STEP)
    auth.verifyMfa.mockRejectedValue(SESSION_ENDED)
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('#login-mfa-code').exists()).toBe(true)
    expect(wrapper.text()).not.toContain(i18n.global.t('login.ssoButton', { provider: 'Acme' }))

    await submitCode(wrapper, '123456')

    expect(wrapper.text()).toContain(i18n.global.t('login.mfaChallengeExpired'))
    expect(wrapper.find('#login-mfa-code').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('login.ssoButton', { provider: 'Acme' }))
  })

  it('stops an SSO sign-in at a step this client does not know', async () => {
    sso.processSsoCallback.mockResolvedValue({
      status: 'next-step',
      result: { status: 'unsupported-step' },
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('login.unsupportedStep'))
    expect(wrapper.find('#login-mfa-code').exists()).toBe(false)
  })
})

describe('LoginView password step errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sso.processSsoCallback.mockResolvedValue({ status: 'none' })
  })

  const TYPE_BY_STATUS: Record<number, string> = {
    401: 'unauthorized',
    403: 'permission-denied',
    429: 'too-many-requests',
  }

  async function submitPassword(status: number) {
    auth.login.mockRejectedValue(
      new HttpError(status, 'Refused', null, `urn:endurain:error:${TYPE_BY_STATUS[status]}`),
    )
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
    [429, 'too-many-requests', 'app.retryAfter.tooManyAttempts'],
    [503, 'service-unavailable', 'app.retryAfter.unavailable'],
  ])('tells the user how long to wait after a %i %s', async (status, code, key) => {
    auth.login.mockRejectedValue(
      new HttpError(status, 'Refused', null, `urn:endurain:error:${code}`, null, [], 42),
    )
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
