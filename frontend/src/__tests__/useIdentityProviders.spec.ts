import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { IdentityProviderInput } from '@/features/identityProviders/types'

import { updateIdentityProvider } from '@/features/identityProviders/services/identityProviders'
import { useUpdateIdentityProviderMutation } from '@/features/identityProviders/composables/useIdentityProviders'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/identityProviders/services/identityProviders', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('@/features/identityProviders/services/identityProviders')
  >()),
  updateIdentityProvider: vi.fn<typeof updateIdentityProvider>(),
}))

const input: IdentityProviderInput = {
  name: 'Keycloak',
  slug: 'keycloak',
  providerType: 'oidc',
  enabled: true,
  issuerUrl: 'https://idp.test',
  clientId: 'endurain',
  clientSecret: null,
  scopes: 'openid profile email',
  icon: null,
  autoCreateUsers: true,
  syncUserInfo: true,
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountMutation(
  queryClient: QueryClient,
): ReturnType<typeof useUpdateIdentityProviderMutation> {
  let mutation: ReturnType<typeof useUpdateIdentityProviderMutation> | undefined
  const TestComponent = defineComponent({
    setup() {
      mutation = useUpdateIdentityProviderMutation()
      return () => h('div')
    },
  })

  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })

  if (!mutation) {
    throw new Error('Identity-provider mutation was not initialized')
  }
  return mutation
}

describe('useUpdateIdentityProviderMutation', () => {
  it('invalidates provider queries after a stale edit so the current version is fetched', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    const stale = Object.assign(new Error('stale'), { status: 412 })
    vi.mocked(updateIdentityProvider).mockRejectedValue(stale)
    const mutation = mountMutation(queryClient)

    await expect(mutation.mutateAsync({ id: 3, input, version: 1 })).rejects.toBe(stale)
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.identityProviders.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.public.identityProviders(),
    })
  })
})
