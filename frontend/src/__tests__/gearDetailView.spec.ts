import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { ref } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GearDetailView from '@/features/gears/views/GearDetailView.vue'

const { route } = vi.hoisted(() => ({ route: { params: {} as Record<string, unknown> } }))

vi.mock('vue-router', () => ({
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

async function mountView() {
  const wrapper = mount(GearDetailView, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  await flushPromises()
  return wrapper
}

describe('GearDetailView', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('shows the not-found state without a request when the id is not a UUID', async () => {
    route.params = { id: '5' }

    const wrapper = await mountView()

    expect(wrapper.text()).toContain(i18n.global.t('gears.detail.notFoundTitle'))
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
