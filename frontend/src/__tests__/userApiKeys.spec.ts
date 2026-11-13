import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Plugin } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ApiKey, ApiKeyDto } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import { apiFetch, HttpError } from '@/services/http'
import UserApiKeysList from '@/features/users/components/UserApiKeysList.vue'
import {
  fetchUserApiKeys,
  revokeAllUserApiKeys,
  revokeUserApiKey,
} from '@/features/users/services/apiKeys'

const mocks = vi.hoisted(() => ({
  apiKeys: [] as ApiKey[],
  isError: false,
  isPending: false,
  revokeMutate: vi.fn<(...args: unknown[]) => void>(),
  revokeAllMutate: vi.fn<(...args: unknown[]) => void>(),
  toastError: vi.fn<(message: string) => void>(),
  toastSuccess: vi.fn<(message: string) => void>(),
}))

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}))
vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))
vi.mock('@/features/users/composables/useUserApiKeys', () => ({
  useUserApiKeysQuery: () => ({
    data: ref(mocks.apiKeys),
    isPending: ref(mocks.isPending),
    isError: ref(mocks.isError),
    refetch: vi.fn<() => void>(),
  }),
  useRevokeUserApiKeyMutation: () => ({ mutate: mocks.revokeMutate, isPending: ref(false) }),
  useRevokeAllUserApiKeysMutation: () => ({
    mutate: mocks.revokeAllMutate,
    isPending: ref(false),
  }),
}))

const passthrough = { template: '<div><slot /></div>' }
const stubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
}
const plugins = (): (Plugin | [Plugin, ...unknown[]])[] => [
  i18n,
  [VueQueryPlugin, { queryClient: new QueryClient() }],
]

function makeKeyDto(overrides: Partial<ApiKeyDto> = {}): ApiKeyDto {
  return {
    id: 'key-1',
    user_id: '00000000-0000-4000-8000-000000000007',
    name: 'Upload script',
    key_prefix: 'endu_ab',
    scopes: ['activities:upload'],
    created_at: '2026-06-01T10:00:00Z',
    expires_at: '2027-06-01T10:00:00Z',
    last_used_at: null,
    is_active: true,
    ...overrides,
  }
}

function makeKey(overrides: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 'key-1',
    name: 'Upload script',
    keyPrefix: 'endu_ab',
    scopes: ['activities:upload'],
    expiresAt: '2027-06-01T10:00:00Z',
    lastUsedAt: null,
    createdAt: '2026-06-01T10:00:00Z',
    isActive: true,
    ...overrides,
  }
}

const stepUp = { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null }
const stepUpWire = { current_password: 'admin-pw', mfa_code: '123456' }

describe('user API keys service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchUserApiKeys calls the user API-keys endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [makeKeyDto()], next: null })

    const keys = await fetchUserApiKeys('00000000-0000-4000-8000-000000000007')

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/api-keys?num_records=200&page_number=1',
      {
        signal: undefined,
      },
    )
    expect(keys).toEqual([makeKey()])
  })

  it('fetchUserApiKeys follows the pages until the last one', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [makeKeyDto()], next: 2 })
      .mockResolvedValueOnce({ items: [makeKeyDto({ id: 'key-2' })], next: null })

    const keys = await fetchUserApiKeys('00000000-0000-4000-8000-000000000007')

    expect(keys.map((key) => key.id)).toEqual(['key-1', 'key-2'])
  })

  it('revokeUserApiKey POSTs the revoke route with the administrator step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeUserApiKey('key-1', '00000000-0000-4000-8000-000000000007', {
      currentPassword: 'admin-pw',
      mfaCode: '123456',
    })

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/api-keys/key-1/revoke',
      {
        method: 'POST',
        body: JSON.stringify({ step_up: stepUpWire }),
        responseType: 'void',
      },
    )
  })

  it('revokeAllUserApiKeys POSTs the bulk revoke route with the administrator step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeAllUserApiKeys('00000000-0000-4000-8000-000000000007', {
      currentPassword: 'admin-pw',
      mfaCode: '123456',
    })

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/api-keys/revoke',
      {
        method: 'POST',
        body: JSON.stringify({ step_up: stepUpWire }),
        responseType: 'void',
      },
    )
  })
})

describe('UserApiKeysList', () => {
  function mountList(resume: IdpStepUpResume | null = null) {
    return mount(UserApiKeysList, {
      props: { userId: '00000000-0000-4000-8000-000000000007', resume },
      global: { plugins: plugins(), stubs },
    })
  }

  function resumeFor(pending: Record<string, unknown>) {
    return {
      action: 'admin_api_keys_revoke',
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending,
    } as IdpStepUpResume
  }

  beforeEach(() => {
    mocks.apiKeys = [makeKey(), makeKey({ id: 'key-2', name: 'Old key', isActive: false })]
    mocks.isError = false
    mocks.isPending = false
    mocks.revokeMutate.mockReset()
    mocks.revokeAllMutate.mockReset()
    mocks.toastError.mockReset()
    mocks.toastSuccess.mockReset()
  })

  it('shows the key state and offers revoke only on an active key', () => {
    const wrapper = mountList()
    const rows = wrapper.findAll('ul > li')

    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('Upload script')
    expect(rows[0]!.text()).toContain(i18n.global.t('settings.security.apiKeys.statusActive'))
    expect(rows[0]!.find('button').exists()).toBe(true)
    expect(rows[1]!.text()).toContain(i18n.global.t('settings.security.apiKeys.statusRevoked'))
    expect(rows[1]!.find('button').exists()).toBe(false)
  })

  it('disables revoke-all when no key is active', () => {
    mocks.apiKeys = [makeKey({ isActive: false })]
    const wrapper = mountList()

    expect(wrapper.get('.justify-between button').attributes('disabled')).toBeDefined()
  })

  it('shows the empty, error and loading states', () => {
    mocks.apiKeys = []
    expect(mountList().text()).toContain(i18n.global.t('settings.users.apiKeys.empty'))

    mocks.isError = true
    expect(mountList().text()).toContain(i18n.global.t('settings.users.apiKeys.error'))

    mocks.isError = false
    mocks.isPending = true
    expect(mountList().find('[aria-busy="true"]').exists()).toBe(true)
  })

  it('sends the administrator step-up when revoking one key', async () => {
    const wrapper = mountList()
    await wrapper.findAll('ul button')[0]!.trigger('click')
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')

    expect(mocks.revokeMutate).toHaveBeenCalledWith(
      { apiKeyId: 'key-1', userId: '00000000-0000-4000-8000-000000000007', stepUp },
      expect.any(Object),
    )
  })

  it('sends the administrator step-up when revoking all keys', async () => {
    const wrapper = mountList()
    await wrapper.get('.justify-between button').trigger('click')
    await wrapper.findAll('#stepup-password')[1]!.setValue('admin-pw')
    await wrapper.findAll('form')[1]!.trigger('submit')

    expect(mocks.revokeAllMutate).toHaveBeenCalledWith(
      { userId: '00000000-0000-4000-8000-000000000007', stepUp },
      expect.any(Object),
    )
  })

  it('reports invalid credentials and keeps the dialog open on a refused step-up', async () => {
    const wrapper = mountList()
    await wrapper.findAll('ul button')[0]!.trigger('click')
    await wrapper.get('#stepup-password').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    const { onError } = mocks.revokeMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.linked.invalidCredentials'),
    )
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
  })

  it('closes the dialog and says so when the key no longer exists', async () => {
    const wrapper = mountList()
    await wrapper.findAll('ul button')[0]!.trigger('click')
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')
    const { onError } = mocks.revokeMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(404, 'Not Found', null, 'urn:endurain:error:not-found'))
    await flushPromises()

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.users.apiKeys.revokeNotFound'),
    )
    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[0]!.props('open')).toBe(false)
  })

  it('reopens the revoke dialog for the key the return was started for', async () => {
    const wrapper = mountList(
      resumeFor({ userId: '00000000-0000-4000-8000-000000000007', apiKeyId: 'key-1' }),
    )
    await flushPromises()

    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[0]!.props('open')).toBe(true)
    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[1]!.props('open')).toBe(false)
  })

  it('reopens the revoke-all dialog after the return', async () => {
    const wrapper = mountList(
      resumeFor({ userId: '00000000-0000-4000-8000-000000000007', all: true }),
    )
    await flushPromises()

    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[0]!.props('open')).toBe(false)
    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[1]!.props('open')).toBe(true)
  })
})
