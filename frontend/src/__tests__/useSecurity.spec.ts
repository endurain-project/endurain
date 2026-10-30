import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useCancelEmailChangeMutation,
  useChangeEmailMutation,
  useResendEmailChangeMutation,
} from '@/features/security/composables/useSecurity'
import {
  cancelEmailChange,
  changeEmail,
  resendEmailChange,
} from '@/features/security/services/security'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/security/services/security', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/services/security')>()),
  changeEmail: vi.fn<typeof changeEmail>(),
  resendEmailChange: vi.fn<typeof resendEmailChange>(),
  cancelEmailChange: vi.fn<typeof cancelEmailChange>(),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountMutation<T>(queryClient: QueryClient, use: () => T): T {
  let mutation: T | undefined
  const TestComponent = defineComponent({
    setup() {
      mutation = use()
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
    vi.mocked(changeEmail).mockResolvedValue(true)
    const mutation = mountMutation(queryClient, useChangeEmailMutation)

    await mutation.mutateAsync({
      email: 'new@example.com',
      stepUp: { currentPassword: 'secret', mfaCode: null },
      revokeOtherSessions: false,
    })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.users.all() })
  })
})

describe.each([
  ['useResendEmailChangeMutation', useResendEmailChangeMutation, resendEmailChange],
  ['useCancelEmailChangeMutation', useCancelEmailChangeMutation, cancelEmailChange],
])('%s', (_name, use, service) => {
  it('calls its endpoint and refreshes profile, current user and users', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(service).mockResolvedValue()
    const mutation = mountMutation(
      queryClient,
      use as () => ReturnType<typeof useCancelEmailChangeMutation>,
    )

    await mutation.mutateAsync()
    await flushPromises()

    expect(service).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.currentUser() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.users.all() })
  })
})
