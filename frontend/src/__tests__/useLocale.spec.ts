import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ProfileDetails } from '@/features/profile/types'

import { useLocale } from '@/composables/useLocale'
import { fetchProfile, updateProfile } from '@/features/profile/services/profile'
import { loadLocaleMessages, setI18nLocale } from '@/i18n'
import i18n from '@/i18n'

const isAuthenticated = ref(false)
const toastError = vi.fn<(message: string) => void>()

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))
vi.mock('@/features/config/composables/useAppConfig', () => ({
  useAppConfig: () => ({ config: ref({ enabledLocales: [] }) }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: toastError }),
}))
vi.mock('@/i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/i18n')>()),
  loadLocaleMessages: vi.fn<typeof loadLocaleMessages>().mockResolvedValue(),
  setI18nLocale: vi.fn<typeof setI18nLocale>(),
}))
vi.mock('@/features/profile/services/profile', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/profile')>()),
  fetchProfile: vi.fn<typeof fetchProfile>(),
  updateProfile: vi.fn<typeof updateProfile>(),
}))

let wrapper: ReturnType<typeof mount> | undefined

function mountLocale(): ReturnType<typeof useLocale> {
  let locale: ReturnType<typeof useLocale> | undefined
  const TestComponent = defineComponent({
    setup() {
      locale = useLocale()
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  return locale!
}

describe('useLocale setLocale', () => {
  beforeEach(() => {
    isAuthenticated.value = false
    vi.mocked(fetchProfile).mockResolvedValue({
      version: 7,
      preferredLanguage: 'en',
    } as ProfileDetails)
    vi.mocked(updateProfile).mockResolvedValue()
  })
  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    vi.clearAllMocks()
  })

  it('only switches the interface when signed out', async () => {
    const { setLocale } = mountLocale()
    await setLocale('pt-PT')

    expect(setI18nLocale).toHaveBeenCalledWith('pt-PT')
    expect(updateProfile).not.toHaveBeenCalled()
  })

  it('also saves the language to the profile with its version when signed in', async () => {
    isAuthenticated.value = true
    const { setLocale } = mountLocale()
    await setLocale('pt-PT')
    await flushPromises()

    expect(setI18nLocale).toHaveBeenCalledWith('pt-PT')
    expect(updateProfile).toHaveBeenCalledWith({ preferredLanguage: 'pt-PT' }, 7)
  })

  it('does not write when the profile already has that language', async () => {
    isAuthenticated.value = true
    const { setLocale } = mountLocale()
    await setLocale('en')
    await flushPromises()

    expect(updateProfile).not.toHaveBeenCalled()
  })

  it('reports a failed save without undoing the switch', async () => {
    isAuthenticated.value = true
    vi.mocked(updateProfile).mockRejectedValue(new Error('boom'))
    const { setLocale } = mountLocale()
    await setLocale('pt-PT')
    await flushPromises()

    expect(setI18nLocale).toHaveBeenCalledWith('pt-PT')
    expect(toastError).toHaveBeenCalledTimes(1)
  })
})
