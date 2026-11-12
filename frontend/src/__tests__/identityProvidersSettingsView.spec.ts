import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Plugin } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { IdentityProvider } from '@/features/identityProviders/types'

import i18n from '@/i18n'
import IdentityProviderFormDialog from '@/features/identityProviders/components/IdentityProviderFormDialog.vue'
import IdentityProvidersSettingsView from '@/features/identityProviders/views/IdentityProvidersSettingsView.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

const mocks = vi.hoisted(() => ({
  updateMutate: vi.fn<(...args: unknown[]) => void>(),
  toastError: vi.fn<(message: string) => void>(),
  providers: [] as IdentityProvider[],
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/settings/identity-providers' }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: mocks.toastError }),
}))
vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))
vi.mock('@/features/identityProviders/composables/useIdentityProviders', () => ({
  useIdentityProvidersQuery: () => ({
    data: ref(mocks.providers),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useIdentityProviderTemplatesQuery: () => ({ data: ref([]) }),
  useUpdateIdentityProviderMutation: () => ({
    mutate: mocks.updateMutate,
    isPending: ref(false),
  }),
  useDeleteIdentityProviderMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
}))

const passthrough = { template: '<div><slot /></div>' }
const stubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
  IdentityProviderFormDialog: { props: ['resume', 'provider'], template: '<i data-test="form" />' },
}
const plugins = (): (Plugin | [Plugin, ...unknown[]])[] => [
  i18n,
  [VueQueryPlugin, { queryClient: new QueryClient() }],
]

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

function storeReturn(action: string, pending: Record<string, unknown>): void {
  sessionStorage.setItem(
    'idp_step_up',
    JSON.stringify({
      action,
      verifier: 'v1',
      idpId: '00000000-0000-4000-8000-000000000009',
      pending,
      createdAt: Date.now(),
    }),
  )
  history.replaceState(null, '', '/settings/identity-providers#step_up_ticket=t1')
}

function mountView() {
  return mount(IdentityProvidersSettingsView, { global: { plugins: plugins(), stubs } })
}

beforeEach(() => {
  mocks.updateMutate.mockReset()
  mocks.toastError.mockReset()
  mocks.providers = [provider]
  sessionStorage.clear()
  history.replaceState(null, '', '/settings/identity-providers')
})

describe('IdentityProvidersSettingsView step-up', () => {
  it('hands the consumed return to the form dialog and strips the fragment', () => {
    storeReturn('admin_idp_create', { variant: 'form', draft: { name: 'Draft' } })
    const wrapper = mountView()

    expect(wrapper.findComponent(IdentityProviderFormDialog).props('resume')).toMatchObject({
      action: 'admin_idp_create',
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending: { variant: 'form', draft: { name: 'Draft' } },
    })
    expect(window.location.hash).toBe('')
  })

  it('selects the provider an edit return was started for', async () => {
    storeReturn('admin_idp_edit', {
      variant: 'form',
      idpId: '00000000-0000-4000-8000-000000000003',
      draft: {},
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findComponent(IdentityProviderFormDialog).props('provider')).toEqual(provider)
  })

  it('reports a return that was not fresh and passes no resume down', async () => {
    storeReturn('admin_idp_edit', {
      variant: 'form',
      idpId: '00000000-0000-4000-8000-000000000003',
      draft: {},
    })
    history.replaceState(null, '', '/settings/identity-providers#step_up_error=not_fresh')
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.stepUp.notFresh'),
    )
    expect(wrapper.findComponent(IdentityProviderFormDialog).props('resume')).toBeNull()
  })

  it('asks for the step-up before toggling a provider and sends it', async () => {
    const wrapper = mountView()
    await wrapper.get('input[role="switch"]').setValue(false)
    await flushPromises()

    expect(mocks.updateMutate).not.toHaveBeenCalled()
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')

    expect(mocks.updateMutate).toHaveBeenCalledWith(
      {
        id: '00000000-0000-4000-8000-000000000003',
        input: expect.objectContaining({ enabled: false, clientSecret: null }),
        version: 4,
        stepUp: { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null },
      },
      expect.any(Object),
    )
  })

  it('reopens the toggle step-up with the sign-in proof after a return', async () => {
    storeReturn('admin_idp_edit', {
      variant: 'toggle',
      idpId: '00000000-0000-4000-8000-000000000003',
      enabled: false,
    })
    const wrapper = mountView()
    await flushPromises()

    const dialog = wrapper.findComponent(StepUpDialog)
    expect(dialog.props('open')).toBe(true)
    expect(dialog.props('reauth')).toEqual({ ticket: 't1', codeVerifier: 'v1' })
    expect(wrapper.findComponent(IdentityProviderFormDialog).props('provider')).toBeNull()
  })
})
