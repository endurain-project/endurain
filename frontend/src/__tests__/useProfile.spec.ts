import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProfileEditInput } from '@/features/profile/types'

import { useUpdateProfileMutation } from '@/features/profile/composables/useProfile'
import { updateProfile } from '@/features/profile/services/profile'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/profile/services/profile', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/profile')>()),
  updateProfile: vi.fn<(input: ProfileEditInput) => Promise<void>>(),
}))

const profileInput: ProfileEditInput = {
  name: 'Ada Lovelace',
  username: 'ada',
  email: 'ada@example.com',
  city: null,
  birthdate: null,
  gender: 'unspecified',
  units: 'metric',
  currency: 'euro',
  height: null,
  maxHeartRate: null,
  preferredLanguage: 'en',
  firstDayOfWeek: 'sunday',
  timezone: 'Europe/Lisbon',
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountMutation(queryClient: QueryClient): ReturnType<typeof useUpdateProfileMutation> {
  let mutation: ReturnType<typeof useUpdateProfileMutation> | undefined
  const TestComponent = defineComponent({
    setup() {
      mutation = useUpdateProfileMutation()
      return () => h('div')
    },
  })

  wrapper = mount(TestComponent, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
    },
  })

  if (!mutation) {
    throw new Error('Profile mutation was not initialized')
  }
  return mutation
}

describe('useUpdateProfileMutation', () => {
  it('invalidates week-dependent data when the first weekday changes', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.currentUser(), { firstDayOfWeek: 'monday' })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync(profileInput)
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.activities.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.goals.all() })
  })

  it('does not invalidate week-dependent data when the weekday is unchanged', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.currentUser(), { firstDayOfWeek: 'sunday' })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync(profileInput)
    await flushPromises()

    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: queryKeys.activities.all() })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: queryKeys.goals.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.currentUser() })
  })
})
