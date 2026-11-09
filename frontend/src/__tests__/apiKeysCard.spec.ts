import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ApiKeyCreateInput } from '@/features/security/types'

import i18n from '@/i18n'
import ApiKeyCreateDialog from '@/features/security/components/ApiKeyCreateDialog.vue'
import ApiKeysCard from '@/features/security/components/ApiKeysCard.vue'
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
