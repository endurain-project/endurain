import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import type { IdentityProvider } from '@/features/identityProviders/types'
import IdentityProviderFormDialog from '@/features/identityProviders/components/IdentityProviderFormDialog.vue'

// Replace only the network seam; keep the real `HttpError` for the dialog's
// `instanceof` checks in its error path.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof import('@/services/http').apiFetch>(),
}))

vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))

const provider: IdentityProvider = {
  id: '00000000-0000-4000-8000-000000000003',
  version: 4,
  name: 'Authentik',
  slug: 'authentik',
  providerType: 'oidc',
  enabled: true,
  issuerUrl: 'https://auth.example.com',
  clientId: 'endurain',
  scopes: 'openid profile email',
  icon: null,
  iconUploaded: false,
  autoCreateUsers: true,
  linkByEmail: false,
  syncUserInfo: true,
  syncEmail: false,
  authorizationEndpoint: null,
  tokenEndpoint: null,
  userinfoEndpoint: null,
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(IdentityProviderFormDialog, {
    props: { open: true, provider: null, templates: [], ...props },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
      },
    },
  })
}

/** Fills the create form with valid values and submits it. */
async function submitValidForm(wrapper: ReturnType<typeof mountDialog>) {
  await wrapper.find('input[name="name"]').setValue('Authentik')
  await wrapper.find('input[name="slug"]').setValue('authentik')
  await wrapper.find('input[name="issuerUrl"]').setValue('https://auth.example.com')
  await wrapper.find('input[name="clientId"]').setValue('endurain')
  await wrapper.find('input[name="clientSecret"]').setValue('secret')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

/** Types the administrator's password in the step-up dialog (the second form) and confirms it. */
async function confirmStepUp(wrapper: ReturnType<typeof mountDialog>) {
  await wrapper.get('#stepup-password').setValue('admin-pw')
  await wrapper.findAll('form')[1]!.trigger('submit')
  await flushPromises()
}

/** The JSON body of the request the dialog sent last. */
function sentBody(): { path: unknown; method: unknown; body: Record<string, unknown> } {
  const [path, init] = vi.mocked(apiFetch).mock.calls[vi.mocked(apiFetch).mock.calls.length - 1]!
  return { path, method: init?.method, body: JSON.parse(String(init?.body)) }
}

describe('IdentityProviderFormDialog save errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('explains a refused issuer URL when the backend answers 400', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )

    const wrapper = mountDialog()
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('error')).toEqual([
      [i18n.global.t('settings.idp.form.issuerUrlRefused')],
    ])
  })

  it.each([
    [409, 'urn:endurain:error:conflict', 'slugConflict'],
    [409, 'urn:endurain:error:issuer-in-use', 'issuerInUse'],
    [409, 'urn:endurain:error:issuer-locked', 'issuerLocked'],
  ])('maps a %i answer of type %s to %s', async (status, type, key) => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(status, 'Conflict', null, type))

    const wrapper = mountDialog()
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(wrapper.emitted('error')).toEqual([[i18n.global.t(`settings.idp.form.${key}`)]])
  })

  it('keeps the generic save error for other failures', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(500, 'Internal Server Error'))

    const wrapper = mountDialog()
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(wrapper.emitted('error')).toEqual([[i18n.global.t('settings.idp.form.saveError')]])
  })

  it('keeps the step-up dialog open and reports invalid credentials when it is refused', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'),
    )

    const wrapper = mountDialog()
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(wrapper.emitted('error')).toEqual([
      [i18n.global.t('settings.security.linked.invalidCredentials')],
    ])
    expect(wrapper.emitted('update:open')).toBeUndefined()
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
  })
})

describe('IdentityProviderFormDialog scopes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('refuses an OpenID Connect provider whose scopes lack openid, and sends nothing', async () => {
    const wrapper = mountDialog()
    await wrapper.find('input[name="scopes"]').setValue('profile email')
    await submitValidForm(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('settings.idp.form.scopesOpenidRequired'))
    expect(apiFetch).not.toHaveBeenCalled()
  })
})

describe('IdentityProviderFormDialog slug', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each(['login', 'backchannel-logout'])(
    'refuses the reserved slug %s and sends nothing',
    async (slug) => {
      const wrapper = mountDialog()
      await wrapper.find('input[name="name"]').setValue('Authentik')
      await wrapper.find('input[name="issuerUrl"]').setValue('https://auth.example.com')
      await wrapper.find('input[name="clientId"]').setValue('endurain')
      await wrapper.find('input[name="clientSecret"]').setValue('secret')
      await wrapper.find('input[name="slug"]').setValue(slug)
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.text()).toContain(i18n.global.t('settings.idp.form.slugReserved'))
      expect(apiFetch).not.toHaveBeenCalled()
    },
  )

  it('accepts a slug that only starts with a reserved word', async () => {
    const wrapper = mountDialog()
    await wrapper.find('input[name="name"]').setValue('Authentik')
    await wrapper.find('input[name="issuerUrl"]').setValue('https://auth.example.com')
    await wrapper.find('input[name="clientId"]').setValue('endurain')
    await wrapper.find('input[name="clientSecret"]').setValue('secret')
    await wrapper.find('input[name="slug"]').setValue('login-sso')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).not.toContain(i18n.global.t('settings.idp.form.slugReserved'))
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
  })
})

describe('IdentityProviderFormDialog step-up', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends nothing until the administrator confirms, then creates with the step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...provider })

    const wrapper = mountDialog()
    await submitValidForm(wrapper)

    expect(apiFetch).not.toHaveBeenCalled()
    await confirmStepUp(wrapper)

    expect(sentBody()).toMatchObject({
      path: '/identity-providers',
      method: 'POST',
      body: { client_secret: 'secret', step_up: { current_password: 'admin-pw', mfa_code: null } },
    })
  })

  it('offers the two protocols and creates a new provider with link by email and email sync off', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...provider })

    const wrapper = mountDialog()
    const options = wrapper.findAll('select option').map((option) => option.attributes('value'))
    expect(options).toContain('oidc')
    expect(options).toContain('oauth2')
    expect(options).not.toContain('saml')
    expect(wrapper.text()).toContain(i18n.global.t('settings.idp.form.linkByEmailHint'))
    expect(wrapper.text()).toContain(i18n.global.t('settings.idp.form.syncUserInfoHint'))
    expect(wrapper.text()).toContain(i18n.global.t('settings.idp.form.syncEmailHint'))

    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(sentBody().body).toMatchObject({
      provider_type: 'oidc',
      link_by_email: false,
      sync_user_info: true,
      sync_email: false,
    })
  })

  it('sends the switches an administrator turns on', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...provider })

    const wrapper = mountDialog()
    const typeSelect = wrapper
      .findAll('select')
      .find((select) => select.find('option[value="oauth2"]').exists())
    await typeSelect!.setValue('oauth2')
    const labels = wrapper.findAll('label')
    for (const key of ['linkByEmail', 'syncEmail'] as const) {
      const label = labels.find((l) => l.text() === i18n.global.t(`settings.idp.form.${key}`))
      await label!.find('input[role="switch"]').setValue(true)
    }
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(sentBody().body).toMatchObject({
      provider_type: 'oauth2',
      link_by_email: true,
      sync_email: true,
    })
  })

  it('shows the switches of the provider being edited', async () => {
    const wrapper = mountDialog({ provider: { ...provider, linkByEmail: true, syncEmail: true } })
    await flushPromises()

    const checked = (key: string) => {
      const label = wrapper
        .findAll('label')
        .find((l) => l.text() === i18n.global.t(`settings.idp.form.${key}`))
      return (label!.find('input[role="switch"]').element as HTMLInputElement).checked
    }
    expect(checked('linkByEmail')).toBe(true)
    expect(checked('syncEmail')).toBe(true)
  })

  it('asks for the step-up on every edit and keeps a blank secret out of the request', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...provider })

    const wrapper = mountDialog({ provider })
    await flushPromises()
    await wrapper.find('input[name="name"]').setValue('Renamed')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    await confirmStepUp(wrapper)

    const { path, method, body } = sentBody()
    expect(path).toBe('/identity-providers/00000000-0000-4000-8000-000000000003')
    expect(method).toBe('PATCH')
    expect(body).toMatchObject({ name: 'Renamed', step_up: { current_password: 'admin-pw' } })
    expect(body).not.toHaveProperty('client_secret')
  })

  it('never puts the client secret in the pending context', async () => {
    const wrapper = mountDialog()
    await wrapper.find('input[name="name"]').setValue('Authentik')
    await wrapper.find('input[name="clientSecret"]').setValue('very-secret-value')

    const context = wrapper.findComponent({ name: 'StepUpDialog' }).props('pendingContext')
    expect(JSON.stringify(context)).not.toContain('very-secret-value')
    expect(context).toMatchObject({ variant: 'form', draft: { name: 'Authentik' } })
    expect(context.draft).not.toHaveProperty('clientSecret')
  })

  it('reopens a create with the draft restored and the step-up ready after a return', async () => {
    const wrapper = mountDialog({
      open: false,
      resume: {
        action: 'admin_idp_create',
        reauth: { ticket: 't1', codeVerifier: 'v1' },
        pending: {
          variant: 'form',
          draft: { name: 'Draft', clientSecret: 'leaked', slug: 'draft' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect((wrapper.find('input[name="name"]').element as HTMLInputElement).value).toBe('Draft')
    expect((wrapper.find('input[name="clientSecret"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.findComponent({ name: 'StepUpDialog' }).props('open')).toBe(true)
    expect(wrapper.findComponent({ name: 'StepUpDialog' }).props('reauth')).toEqual({
      ticket: 't1',
      codeVerifier: 'v1',
    })
  })

  it.each([
    [
      'another provider',
      'admin_idp_edit',
      { variant: 'form', idpId: '00000000-0000-4000-8000-000000000009', draft: {} },
    ],
    [
      'a toggle',
      'admin_idp_edit',
      { variant: 'toggle', idpId: '00000000-0000-4000-8000-000000000003', enabled: false },
    ],
    ['a create', 'admin_idp_create', { variant: 'form', draft: {} }],
  ])('does not open the edit of a provider for %s', async (_label, action, pending) => {
    const wrapper = mountDialog({
      open: false,
      provider,
      resume: { action, reauth: { ticket: 't1', codeVerifier: 'v1' }, pending },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('reopens the edit of the provider the return was started for', async () => {
    const wrapper = mountDialog({
      open: false,
      provider,
      resume: {
        action: 'admin_idp_edit',
        reauth: { ticket: 't1', codeVerifier: 'v1' },
        pending: {
          variant: 'form',
          idpId: '00000000-0000-4000-8000-000000000003',
          draft: { name: 'Draft' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
  })

  it('shows a 422 on the field it names instead of a toast', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(
        422,
        'Unprocessable Content',
        null,
        'urn:endurain:error:validation-failed',
        null,
        [{ field: 'body.client_id', message: 'm', type: 'string_too_long' }],
      ),
    )

    const wrapper = mountDialog()
    await submitValidForm(wrapper)
    await confirmStepUp(wrapper)

    expect(wrapper.text()).toContain(i18n.global.t('app.fieldError.tooLong'))
    expect(wrapper.emitted('error')).toBeUndefined()
  })
})
