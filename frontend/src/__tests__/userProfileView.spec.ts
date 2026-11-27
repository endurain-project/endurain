import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { ref } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import UserProfileView from '@/features/users/views/UserProfileView.vue'

const { OWN_ID, route } = vi.hoisted(() => ({
  OWN_ID: '5f1c9a2e-7b3d-4e8a-9c1f-0a2b3c4d5e6f',
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
  useCurrentUser: () => ({ data: ref({ id: OWN_ID }) }),
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

  it('treats an upper-case route id equal to the own id as the own profile', async () => {
    route.params = { id: OWN_ID.toUpperCase() }
    vi.mocked(apiFetch).mockImplementation((path) =>
      Promise.resolve(
        String(path).includes('/overview')
          ? {
              user: { id: OWN_ID, name: 'Own', username: 'own' },
              week_stats: {},
              month_stats: {},
              month_activity_count: 0,
            }
          : { items: [], total: 0 },
      ),
    )

    const wrapper = mount(UserProfileView, {
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('userProfile.editProfile'))
    expect(vi.mocked(apiFetch).mock.calls[0]![0]).toContain(`/users/${OWN_ID}/`)
  })
})
