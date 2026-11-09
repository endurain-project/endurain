import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useCancelEmailChangeMutation,
  useChangeEmailMutation,
  useDisableMfaMutation,
  useEnableMfaMutation,
  useResendEmailChangeMutation,
  useSignOutEverywhereMutation,
} from '@/features/security/composables/useSecurity'
import {
  cancelEmailChange,
  changeEmail,
  disableMfa,
  enableMfa,
  resendEmailChange,
  signOutEverywhere,
} from '@/features/security/services/security'
import { queryKeys } from '@/services/queryKeys'

const replace = vi.fn<(location: unknown) => Promise<void>>()
const clearLocalSession = vi.fn<() => void>()

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace }),
}))

vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({ clearLocalSession }),
}))

vi.mock('@/features/security/services/security', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/services/security')>()),
  changeEmail: vi.fn<typeof changeEmail>(),
  enableMfa: vi.fn<typeof enableMfa>(),
  disableMfa: vi.fn<typeof disableMfa>(),
  resendEmailChange: vi.fn<typeof resendEmailChange>(),
  cancelEmailChange: vi.fn<typeof cancelEmailChange>(),
  signOutEverywhere: vi.fn<typeof signOutEverywhere>(),
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

describe('MFA mutations', () => {
  it('refreshes the profile, which carries mfa_enabled, after MFA is enabled', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(enableMfa).mockResolvedValue(['code'])
    const mutation = mountMutation(queryClient, useEnableMfaMutation)

    await mutation.mutateAsync({
      mfaCode: '123456',
      currentPassword: 'secret',
      idpReauth: null,
      revokeOtherSessions: false,
    })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
  })

  it('refreshes the profile, which carries mfa_enabled, after MFA is disabled', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(disableMfa).mockResolvedValue()
    const mutation = mountMutation(queryClient, useDisableMfaMutation)

    await mutation.mutateAsync({
      input: { currentPassword: 'secret', mfaCode: '123456' },
      revokeOtherSessions: false,
    })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
  })
})

describe('useSignOutEverywhereMutation', () => {
  it('shows the login page, then clears the local session', async () => {
    vi.mocked(signOutEverywhere).mockResolvedValue()
    replace.mockResolvedValue()
    const mutation = mountMutation(new QueryClient(), useSignOutEverywhereMutation)

    await mutation.mutateAsync()
    await flushPromises()

    expect(replace).toHaveBeenCalledWith({ name: 'login', query: { logoutSuccess: 'true' } })
    expect(clearLocalSession).toHaveBeenCalledOnce()
    expect(replace.mock.invocationCallOrder[0] ?? Infinity).toBeLessThan(
      clearLocalSession.mock.invocationCallOrder[0] ?? 0,
    )
  })

  it('keeps the session when the request fails', async () => {
    vi.mocked(signOutEverywhere).mockRejectedValue(new Error('boom'))
    const mutation = mountMutation(new QueryClient(), useSignOutEverywhereMutation)

    await expect(mutation.mutateAsync()).rejects.toThrow('boom')

    expect(replace).not.toHaveBeenCalled()
    expect(clearLocalSession).not.toHaveBeenCalled()
  })
})
