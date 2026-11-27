import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { MailSettings } from '@/features/serverSettings/types'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import MailSettingsForm from '@/features/serverSettings/components/MailSettingsForm.vue'
import { provideMailStepUpResume } from '@/features/serverSettings/composables/useMailStepUpResume'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof import('@/services/http').apiFetch>(),
}))

vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))

const toastError = vi.hoisted(() => vi.fn<(message: string) => void>())
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: toastError }),
}))

const settings: MailSettings = {
  version: 2,
  host: 'mail.example.com',
  port: 587,
  security: 'starttls',
  username: 'me@example.com',
  fromAddress: null,
  passwordSet: true,
  envManaged: {},
  emailStatus: { configured: true, problems: [] },
}

const passthrough = { template: '<div><slot /></div>' }
const stubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
}

/** Mounts the form under a host that provides the sign-in the page returned from. */
function mountForm(resume: IdpStepUpResume | null = null) {
  const Host = defineComponent({
    setup() {
      provideMailStepUpResume(resume)
      return () => h(MailSettingsForm, { settings })
    },
  })
  return mount(Host, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]], stubs },
  })
}

/** Submits the settings form (the first form) and waits for the step-up dialog. */
async function submitSettings(wrapper: ReturnType<typeof mountForm>) {
  await wrapper.find('input[inputmode="numeric"]').setValue('465')
  await wrapper.findAll('form')[0]!.trigger('submit')
  await flushPromises()
}

/** Types the administrator's password in the step-up dialog (the second form) and confirms it. */
async function confirmStepUp(wrapper: ReturnType<typeof mountForm>) {
  await wrapper.get('#stepup-password').setValue('admin-pw')
  await wrapper.findAll('form')[1]!.trigger('submit')
  await flushPromises()
}

function sentBody(): Record<string, unknown> {
  const [, init] = vi.mocked(apiFetch).mock.calls[vi.mocked(apiFetch).mock.calls.length - 1]!
  return JSON.parse(String(init?.body))
}

function resumeFor(pending: Record<string, unknown>): IdpStepUpResume {
  return {
    action: 'admin_mail_settings_edit',
    reauth: { ticket: 't1', codeVerifier: 'v1' },
    pending,
  } as IdpStepUpResume
}

describe('MailSettingsForm step-up', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({
      id: 1,
      version: 3,
      host: 'mail.example.com',
      port: 465,
      security: 'starttls',
      username: 'me@example.com',
      from_address: null,
      password_set: true,
      env_managed: {},
    })
  })

  it('sends nothing until the administrator confirms, then saves with the step-up', async () => {
    const wrapper = mountForm()
    await submitSettings(wrapper)

    expect(apiFetch).not.toHaveBeenCalled()
    await confirmStepUp(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(vi.mocked(apiFetch).mock.calls[0]![1]).toMatchObject({
      method: 'PUT',
      headers: { 'If-Match': '"2"' },
    })
    expect(sentBody()).toMatchObject({
      host: 'mail.example.com',
      port: 465,
      step_up: { current_password: 'admin-pw', mfa_code: null },
    })
  })

  it('keeps the step-up dialog open and reports invalid credentials when it is refused', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'),
    )
    const wrapper = mountForm()
    await submitSettings(wrapper)
    await confirmStepUp(wrapper)

    expect(toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.linked.invalidCredentials'),
    )
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
  })

  it('never puts the password in the pending context', async () => {
    const wrapper = mountForm()
    await wrapper.find('input[type="password"]').setValue('very-secret-value')

    const context = wrapper.findComponent({ name: 'StepUpDialog' }).props('pendingContext')
    expect(JSON.stringify(context)).not.toContain('very-secret-value')
    expect(context).toMatchObject({ draft: { host: 'mail.example.com', passwordTyped: true } })
    expect(context.draft).not.toHaveProperty('password')
  })

  it('reopens the step-up with the draft restored after the identity-provider return', async () => {
    const wrapper = mountForm(
      resumeFor({ draft: { host: 'smtp.example.org', port: '2525', passwordTyped: false } }),
    )
    await flushPromises()

    expect((wrapper.find('input[type="text"]').element as HTMLInputElement).value).toBe(
      'smtp.example.org',
    )
    const dialog = wrapper.findComponent({ name: 'StepUpDialog' })
    expect(dialog.props('open')).toBe(true)
    expect(dialog.props('reauth')).toEqual({ ticket: 't1', codeVerifier: 'v1' })
  })

  it('waits for a password the administrator was setting instead of saving without it', async () => {
    const wrapper = mountForm(
      resumeFor({ draft: { host: 'smtp.example.org', passwordTyped: true } }),
    )
    await flushPromises()

    const dialog = wrapper.findComponent({ name: 'StepUpDialog' })
    expect(dialog.props('open')).toBe(false)
    expect(dialog.props('reauth')).toEqual({ ticket: 't1', codeVerifier: 'v1' })
  })
})
