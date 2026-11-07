import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { StepUpInput } from '@/features/security/types'

import { useDeleteAccountMutation } from '@/features/security/composables/useSecurity'
import { deleteAccount } from '@/features/security/services/security'

const mocks = vi.hoisted(() => ({
  calls: [] as string[],
  routerReplace: vi.fn<(to: unknown) => Promise<void>>(),
  clearLocalSession: vi.fn<() => void>(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: mocks.routerReplace }),
}))
vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({ clearLocalSession: mocks.clearLocalSession }),
}))
vi.mock('@/features/security/services/security', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/services/security')>()),
  deleteAccount: vi.fn<(input: StepUpInput) => Promise<void>>(),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  mocks.calls.splice(0)
  vi.clearAllMocks()
})

function mountMutation(): ReturnType<typeof useDeleteAccountMutation> {
  let mutation: ReturnType<typeof useDeleteAccountMutation> | undefined
  const TestComponent = defineComponent({
    setup() {
      mutation = useDeleteAccountMutation()
      return () => h('div')
    },
  })

  wrapper = mount(TestComponent, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]],
    },
  })

  if (!mutation) {
    throw new Error('Delete-account mutation was not initialized')
  }
  return mutation
}

describe('useDeleteAccountMutation', () => {
  it('leaves for the farewell page before clearing the local session', async () => {
    // Clearing the session empties the Query cache, which unmounts the settings
    // view; navigating first keeps the user from being left on a dead page.
    vi.mocked(deleteAccount).mockResolvedValue(undefined)
    mocks.routerReplace.mockImplementation(async () => {
      mocks.calls.push('navigate')
    })
    mocks.clearLocalSession.mockImplementation(() => {
      mocks.calls.push('clear')
    })

    mountMutation().mutate({ currentPassword: 'pw', mfaCode: null })
    await flushPromises()

    expect(mocks.routerReplace).toHaveBeenCalledWith({ name: 'account-deleted' })
    expect(mocks.calls).toEqual(['navigate', 'clear'])
  })

  it('stays on the page and keeps the session when the deletion fails', async () => {
    vi.mocked(deleteAccount).mockRejectedValue(new Error('boom'))

    mountMutation().mutate({ currentPassword: 'pw', mfaCode: null })
    await flushPromises()

    expect(mocks.routerReplace).not.toHaveBeenCalled()
    expect(mocks.clearLocalSession).not.toHaveBeenCalled()
  })
})
