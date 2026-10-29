import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useChangeEmailMutation } from '@/features/security/composables/useSecurity'
import { changeEmail } from '@/features/security/services/security'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/security/services/security', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/services/security')>()),
  changeEmail: vi.fn<typeof changeEmail>(),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountMutation(queryClient: QueryClient): ReturnType<typeof useChangeEmailMutation> {
  let mutation: ReturnType<typeof useChangeEmailMutation> | undefined
  const TestComponent = defineComponent({
    setup() {
      mutation = useChangeEmailMutation()
      return () => h('div')
    },
  })

  wrapper = mount(TestComponent, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
    },
  })

  if (!mutation) {
    throw new Error('Change-email mutation was not initialized')
  }
  return mutation
}

describe('useChangeEmailMutation', () => {
  it('refreshes the users domain, so an admin sees their new unverified email', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(changeEmail).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({
      email: 'new@example.com',
      stepUp: { currentPassword: 'secret', mfaCode: null },
      revokeOtherSessions: false,
    })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.users.all() })
  })
})
