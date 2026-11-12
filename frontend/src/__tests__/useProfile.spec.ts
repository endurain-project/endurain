import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProfileEditInput } from '@/features/profile/types'

import { loadLocaleMessages, setI18nLocale } from '@/i18n'
import { useUpdateProfileMutation } from '@/features/profile/composables/useProfile'
import { updateProfile } from '@/features/profile/services/profile'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/i18n')>()),
  loadLocaleMessages: vi.fn<typeof loadLocaleMessages>().mockResolvedValue(),
  setI18nLocale: vi.fn<typeof setI18nLocale>(),
}))

vi.mock('@/features/profile/services/profile', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/profile')>()),
  updateProfile: vi.fn<(input: ProfileEditInput) => Promise<void>>(),
}))

const profileInput: ProfileEditInput = {
  name: 'Ada Lovelace',
  city: null,
  birthdate: null,
  gender: 'unspecified',
  units: 'metric',
  weightUnits: null,
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

    await mutation.mutateAsync({ input: profileInput, version: 1 })
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

    await mutation.mutateAsync({ input: profileInput, version: 1 })
    await flushPromises()

    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: queryKeys.activities.all() })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: queryKeys.goals.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.currentUser() })
  })

  it('invalidates the admin users domain, whose rows share the profile version', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({ input: profileInput, version: 1 })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.users.all() })
  })

  it('invalidates health data when the height changes', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.profile.detail(), { height: 170 })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({ input: { ...profileInput, height: 180 }, version: 1 })
    await flushPromises()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.health.all() })
  })

  it('leaves health data alone when the height is unchanged', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.profile.detail(), { height: 170 })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({ input: { ...profileInput, height: 170 }, version: 1 })
    await flushPromises()

    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: queryKeys.health.all() })
  })

  it('applies a changed preferred language immediately', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.profile.detail(), { preferredLanguage: 'en' })
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({
      input: { ...profileInput, preferredLanguage: 'pt-PT' },
      version: 1,
    })
    await flushPromises()

    expect(loadLocaleMessages).toHaveBeenCalledWith('pt-PT')
    expect(setI18nLocale).toHaveBeenCalledWith('pt-PT')
  })

  it('leaves the interface language alone when it is unchanged', async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.profile.detail(), { preferredLanguage: 'en' })
    vi.mocked(updateProfile).mockResolvedValue()
    const mutation = mountMutation(queryClient)

    await mutation.mutateAsync({ input: profileInput, version: 1 })
    await flushPromises()

    expect(setI18nLocale).not.toHaveBeenCalled()
  })
})
