import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import NotificationsMenu from '@/features/notifications/components/NotificationsMenu.vue'
import { Popover } from '@/components/ui/popover'

const refetch = vi.fn<() => Promise<void>>(() => Promise.resolve())
const useNotificationsQuery =
  vi.fn<(params: unknown, enabled?: MaybeRefOrGetter<boolean>) => unknown>()

vi.mock('vue-router', () => ({
  useRoute: () => ({ fullPath: '/' }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: 1 }) }),
}))

vi.mock('@/features/notifications/composables/useNotifications', () => ({
  useUnreadNotificationsCount: () => ({ data: ref(0) }),
  useNotificationsQuery: (params: unknown, enabled?: MaybeRefOrGetter<boolean>) => {
    useNotificationsQuery(params, enabled)
    return { data: ref([]), isPending: ref(false), isError: ref(false), refetch }
  },
  useMarkNotificationReadMutation: () => ({ mutate: vi.fn<() => void>() }),
  useMarkAllNotificationsReadMutation: () => ({
    mutate: vi.fn<() => void>(),
    isPending: computed(() => false),
  }),
}))

function mountMenu() {
  return mount(NotificationsMenu, { global: { plugins: [i18n] } })
}

describe('NotificationsMenu', () => {
  beforeEach(() => {
    refetch.mockClear()
    useNotificationsQuery.mockClear()
  })

  /** Whether the menu currently lets the preview query run. */
  function previewEnabled(): boolean {
    const enabled = useNotificationsQuery.mock.calls[0]?.[1]
    if (enabled === undefined) {
      throw new Error('The menu did not gate the preview query')
    }
    return toValue(enabled)
  }

  it('keeps the preview query off until the panel opens', () => {
    mountMenu()

    expect(previewEnabled()).toBe(false)
    expect(refetch).not.toHaveBeenCalled()
  })

  it('runs the preview query only while the panel is open', async () => {
    const wrapper = mountMenu()
    const popover = wrapper.findComponent(Popover)

    popover.vm.$emit('update:open', true)
    await wrapper.vm.$nextTick()
    expect(previewEnabled()).toBe(true)

    popover.vm.$emit('update:open', false)
    await wrapper.vm.$nextTick()
    expect(previewEnabled()).toBe(false)
  })

  it('leaves refreshing on open to the query, instead of adding a second request', async () => {
    const wrapper = mountMenu()

    wrapper.findComponent(Popover).vm.$emit('update:open', true)
    await wrapper.vm.$nextTick()

    expect(refetch).not.toHaveBeenCalled()
  })
})
