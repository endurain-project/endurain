import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { ref } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import UserProfileView from '@/features/users/views/UserProfileView.vue'

const { route } = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
}))

vi.mock('vue-router', () => ({
  RouterLink: { template: '<a><slot /></a>' },
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn<(to: unknown) => Promise<void>>() }),
}))
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))
vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref(null) }),
}))
vi.mock('@/features/activities/composables/useActivityDetail', () => ({
  useDisplayUnits: () => ref(null),
}))

describe('UserProfileView', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('shows the not-found state without a request when the id is not a UUID', async () => {
    route.params = { id: '5' }

    const wrapper = mount(UserProfileView, {
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('userProfile.notFound.title'))
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
