import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import LoginView from '@/features/auth/views/LoginView.vue'

const { auth, navigateAfterLogin } = vi.hoisted(() => ({
  auth: {
    login: vi.fn<(u: string, p: string) => Promise<unknown>>(),
    verifyMfa: vi.fn<(challenge: string, code: string) => Promise<unknown>>(),
    changePassword: vi.fn<(challenge: string, password: string) => Promise<unknown>>(),
  },
  navigateAfterLogin: vi.fn<() => Promise<void>>(),
}))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({
      local_login_enabled: true,
      signup_enabled: false,
      sso_enabled: false,
      password_length_regular_users: 8,
      password_length_admin_users: 12,
    }),
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
    completeSsoMfa: vi.fn<(code: string) => Promise<void>>(),
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
  useSafeRedirect: () => ({ navigateAfterLogin }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => auth }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, fullPath: '/login' }),
  useRouter: () => ({ replace: vi.fn<() => void>() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const NEW_PASSWORD = 'a brand new passphrase'

function mountView() {
  return mount(LoginView, {
    global: {
      plugins: [i18n],
      stubs: { AuthScreenLayout: { template: '<div><slot /></div>' } },
    },
  })
}

type Wrapper = ReturnType<typeof mountView>

async function submitPassword(wrapper: Wrapper): Promise<void> {
  await wrapper.find('input[name="username"]').setValue('user')
  await wrapper.find('input[name="password"]').setValue('secret-password')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

/** Signs in with a password the server says must be changed, so the view is on the password-change step. */
async function toPasswordChangeStep(wrapper: Wrapper): Promise<void> {
  auth.login.mockResolvedValue({ status: 'password-change-required', challenge: 'chal' })
  await submitPassword(wrapper)
}

async function submitNewPassword(wrapper: Wrapper, password = NEW_PASSWORD): Promise<void> {
  await wrapper.find('input[name="newPassword"]').setValue(password)
  await wrapper.find('input[name="confirmNewPassword"]').setValue(password)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('LoginView next step', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('goes on after a completed sign-in', async () => {
    auth.login.mockResolvedValue({ status: 'authenticated' })
    const wrapper = mountView()

    await submitPassword(wrapper)

    expect(navigateAfterLogin).toHaveBeenCalled()
  })

  it('asks for the new password after a password step that requires one', async () => {
    const wrapper = mountView()

    await toPasswordChangeStep(wrapper)

    expect(wrapper.find('input[name="newPassword"]').exists()).toBe(true)
    expect(wrapper.find('input[name="confirmNewPassword"]').exists()).toBe(true)
    expect(wrapper.find('input[name="username"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(i18n.global.t('login.passwordChangeRequired'))
    expect(navigateAfterLogin).not.toHaveBeenCalled()
  })

  it('asks for the new password after the MFA step too', async () => {
    auth.login.mockResolvedValue({ status: 'mfa-required', challenge: 'mfa-chal' })
    auth.verifyMfa.mockResolvedValue({ status: 'password-change-required', challenge: 'chal' })
    const wrapper = mountView()
    await submitPassword(wrapper)

    await wrapper.find('input[name="mfaCode"]').setValue('123456')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('input[name="newPassword"]').exists()).toBe(true)
    expect(wrapper.find('input[name="mfaCode"]').exists()).toBe(false)
  })

  it('reports a step it does not know instead of failing', async () => {
    auth.login.mockResolvedValue({ status: 'unsupported-step' })
    const wrapper = mountView()

    await submitPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('login.unsupportedStep'))
    expect(wrapper.find('input[name="username"]').exists()).toBe(true)
    expect(navigateAfterLogin).not.toHaveBeenCalled()
  })
})

describe('LoginView password-change step', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends the challenge and the new password, then goes on', async () => {
    auth.changePassword.mockResolvedValue({ status: 'authenticated' })
    const wrapper = mountView()
    await toPasswordChangeStep(wrapper)

    await submitNewPassword(wrapper)

    expect(auth.changePassword).toHaveBeenCalledWith('chal', NEW_PASSWORD)
    expect(navigateAfterLogin).toHaveBeenCalled()
  })

  it('does not submit while the confirmation differs', async () => {
    const wrapper = mountView()
    await toPasswordChangeStep(wrapper)

    await wrapper.find('input[name="newPassword"]').setValue(NEW_PASSWORD)
    await wrapper.find('input[name="confirmNewPassword"]').setValue('something else entirely')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(auth.changePassword).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(i18n.global.t('app.password.mismatch'))
  })

  it('returns to the sign-in form with a message when the challenge is refused', async () => {
    auth.changePassword.mockRejectedValue(
      new HttpError(401, 'Unauthorized', null, 'urn:endurain:error:unauthorized'),
    )
    const wrapper = mountView()
    await toPasswordChangeStep(wrapper)

    await submitNewPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('login.passwordChangeExpired'))
    expect(wrapper.find('input[name="username"]').exists()).toBe(true)
    expect(wrapper.find('input[name="newPassword"]').exists()).toBe(false)
  })

  it('shows the reason a refused password gives and keeps the step', async () => {
    auth.changePassword.mockRejectedValue(
      new HttpError(422, 'Unprocessable Content', null, 'urn:endurain:error:password-too-common'),
    )
    const wrapper = mountView()
    await toPasswordChangeStep(wrapper)

    await submitNewPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('app.password.tooCommon'))
    expect(wrapper.find('input[name="newPassword"]').exists()).toBe(true)
  })

  it('names a refusal that has no password reason', async () => {
    auth.changePassword.mockRejectedValue(
      new HttpError(422, 'Unprocessable Content', null, 'urn:endurain:error:validation-failed'),
    )
    const wrapper = mountView()
    await toPasswordChangeStep(wrapper)

    await submitNewPassword(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('login.passwordChangeRejected'))
  })
})
