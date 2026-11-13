import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ApiKeyCreateInput } from '@/features/security/types'

import i18n from '@/i18n'
import ApiKeyCreateDialog from '@/features/security/components/ApiKeyCreateDialog.vue'
import ApiKeysCard from '@/features/security/components/ApiKeysCard.vue'
import {
  API_KEY_SCOPES,
  API_KEY_SCOPE_GROUPS,
  apiKeyScopeLabelKey,
  apiKeyScopesOf,
} from '@/features/security/services/security'
import { HttpError } from '@/services/http'

const mocks = vi.hoisted(() => ({
  mutate: vi.fn<(input: unknown, options: { onError: (e: unknown) => void }) => void>(),
  toastError: vi.fn<(message: string) => void>(),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: mocks.toastError }),
}))
vi.mock('@/features/security/composables/useSecurity', () => {
  const idle = () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) })
  return {
    useApiKeysQuery: () => ({
      data: ref([]),
      isPending: ref(false),
      isError: ref(false),
      refetch: vi.fn<() => void>(),
    }),
    useCreateApiKeyMutation: () => ({ mutate: mocks.mutate, isPending: ref(false) }),
    useRevokeApiKeyMutation: idle,
    useDeleteApiKeyMutation: idle,
  }
})

const fieldError = (field: string) => [{ field, message: 'refused', type: 'value_error' }]

/** Submits a create request and fails it with the given 422 or status. */
async function createFailsWith(expiresAt: string | null, error: HttpError): Promise<void> {
  const wrapper = mount(ApiKeysCard, {
    props: { hasLocalPassword: true, mfaEnabled: false, resume: null },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        ApiKeyCreateDialog: {
          emits: ['submit'],
          template: '<div data-test="create" />',
        },
      },
    },
  })
  const input: ApiKeyCreateInput = {
    name: 'CI',
    scopes: ['activities:upload'],
    expiresAt,
    currentPassword: 'pw',
    mfaCode: null,
  }
  wrapper.findComponent(ApiKeyCreateDialog).vm.$emit('submit', input)
  await flushPromises()
  mocks.mutate.mock.calls[0]![1].onError(error)
}

describe('ApiKeysCard create refusals', () => {
  beforeEach(() => {
    mocks.mutate.mockReset()
    mocks.toastError.mockReset()
  })

  it('tells a past expiry from the date the user chose', async () => {
    await createFailsWith(
      '2000-01-01',
      new HttpError(
        422,
        'Unprocessable',
        null,
        'urn:endurain:error:validation-failed',
        null,
        fieldError('body.expires_at'),
      ),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.expiryNotFuture'),
    )
  })

  it('says a future expiry is later than the server allows', async () => {
    await createFailsWith(
      '2999-01-01',
      new HttpError(
        422,
        'Unprocessable',
        null,
        'urn:endurain:error:validation-failed',
        null,
        fieldError('body.expires_at'),
      ),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.expiryTooLate'),
    )
  })

  it('reports permissions the server does not allow when the scopes fail validation', async () => {
    await createFailsWith(
      null,
      new HttpError(
        422,
        'Unprocessable',
        null,
        'urn:endurain:error:validation-failed',
        null,
        fieldError('body.scopes'),
      ),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.invalidScopes'),
    )
  })

  it('reports a refused scope entry the same way as the scope list', async () => {
    await createFailsWith(
      null,
      new HttpError(
        422,
        'Unprocessable',
        null,
        'urn:endurain:error:validation-failed',
        null,
        fieldError('body.scopes.0'),
      ),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.invalidScopes'),
    )
  })

  it('tells the user when the account holds the most active keys', async () => {
    await createFailsWith(
      null,
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:api-key-limit'),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.apiKeyLimit'),
    )
  })

  it('shows the generic error for a 400, which this route does not raise', async () => {
    await createFailsWith(
      null,
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.apiKeys.createError'),
    )
  })
})

describe('ApiKeyCreateDialog scopes', () => {
  /** Mounts the open dialog and returns it with the emitted submit payloads reachable. */
  async function mountDialog() {
    const wrapper = mount(ApiKeyCreateDialog, {
      props: { open: false, requirePassword: true, requireMfa: false, pending: false },
      attachTo: document.body,
      global: { plugins: [i18n] },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    return wrapper
  }

  it('lists every scope under its group heading', async () => {
    const wrapper = await mountDialog()
    const text = document.body.textContent ?? ''

    for (const group of API_KEY_SCOPE_GROUPS) {
      expect(text).toContain(i18n.global.t(`settings.security.apiKeys.scopeGroups.${group}`))
      for (const scope of apiKeyScopesOf(group)) {
        expect(text).toContain(scope)
        expect(text).toContain(
          i18n.global.t(`settings.security.apiKeys.scopeLabels.${apiKeyScopeLabelKey(scope)}`),
        )
      }
    }
    expect(API_KEY_SCOPE_GROUPS.flatMap(apiKeyScopesOf)).toEqual(API_KEY_SCOPES)
    expect(API_KEY_SCOPES).toHaveLength(15)
    wrapper.unmount()
  })

  it('submits every selected scope', async () => {
    const wrapper = await mountDialog()
    const switches = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input[role=switch]'),
    )
    for (const index of [0, 1, 11]) {
      switches[index]!.click()
    }
    const nameInput = document.body.querySelector<HTMLInputElement>('#apikey-name')!
    nameInput.value = 'CI'
    nameInput.dispatchEvent(new Event('input'))
    const password = document.body.querySelector<HTMLInputElement>('#apikey-password')!
    password.value = 'pw'
    password.dispatchEvent(new Event('input'))
    await flushPromises()
    document.body.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await flushPromises()

    const [input] = wrapper.emitted('submit')![0] as [ApiKeyCreateInput]
    expect(input.scopes).toEqual([API_KEY_SCOPES[0], API_KEY_SCOPES[1], API_KEY_SCOPES[11]])
    wrapper.unmount()
  })
})
