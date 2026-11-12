import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { EditUserFields, ManagedUser } from '@/features/users/types'

import {
  useDeleteUserPhotoMutation,
  useUpdateUserMutation,
  useUploadUserPhotoMutation,
} from '@/features/users/composables/useUsers'
import { deleteUserPhoto, updateUser, uploadUserPhoto } from '@/features/users/services/users'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/users/services/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/users/services/users')>()),
  updateUser: vi.fn<() => Promise<ManagedUser>>(),
  uploadUserPhoto: vi.fn<() => Promise<string | null>>(),
  deleteUserPhoto: vi.fn<() => Promise<void>>(),
}))

const USER_ID = 4

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountMutation<T>(queryClient: QueryClient, useMutation: () => T): T {
  let mutation: T | undefined
  wrapper = mount(
    defineComponent({
      setup() {
        mutation = useMutation()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  if (!mutation) {
    throw new Error('Mutation was not initialized')
  }
  return mutation
}

/** A client with a cached profile, the self-profile the admin may have just edited. */
function clientWithProfile(): QueryClient {
  const queryClient = new QueryClient()
  queryClient.setQueryData(queryKeys.profile.detail(), {})
  return queryClient
}

describe('admin user writes', () => {
  it('an admin edit of a user refreshes the profile, whose version it may have bumped', async () => {
    const queryClient = clientWithProfile()
    vi.mocked(updateUser).mockResolvedValue({ id: USER_ID } as ManagedUser)
    const mutation = mountMutation(queryClient, useUpdateUserMutation)

    await mutation.mutateAsync({
      user: { id: USER_ID } as ManagedUser,
      edits: {} as EditUserFields,
    })
    await flushPromises()

    expect(queryClient.getQueryState(queryKeys.profile.detail())?.isInvalidated).toBe(true)
  })

  it('an admin photo upload refreshes the profile', async () => {
    const queryClient = clientWithProfile()
    vi.mocked(uploadUserPhoto).mockResolvedValue(null)
    const mutation = mountMutation(queryClient, useUploadUserPhotoMutation)

    await mutation.mutateAsync({ userId: USER_ID, file: new File([], 'a.png') })
    await flushPromises()

    expect(queryClient.getQueryState(queryKeys.profile.detail())?.isInvalidated).toBe(true)
  })

  it('an admin photo removal refreshes the profile', async () => {
    const queryClient = clientWithProfile()
    vi.mocked(deleteUserPhoto).mockResolvedValue()
    const mutation = mountMutation(queryClient, useDeleteUserPhotoMutation)

    await mutation.mutateAsync(USER_ID)
    await flushPromises()

    expect(queryClient.getQueryState(queryKeys.profile.detail())?.isInvalidated).toBe(true)
  })
})
