import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import NotificationsMenu from '@/features/notifications/components/NotificationsMenu.vue'
import { Popover } from '@/components/ui/popover'

const refetch = vi.fn<() => Promise<void>>(() => Promise.resolve())

vi.mock('vue-router', () => ({
  useRoute: () => ({ fullPath: '/' }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: 1 }) }),
}))

vi.mock('@/features/notifications/composables/useNotifications', () => ({
  useUnreadNotificationsCount: () => ({ data: ref(0) }),
  useNotificationsQuery: () => ({
    data: ref([]),
    isPending: ref(false),
    isError: ref(false),
    refetch,
  }),
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
  })

  it('does not refetch the preview just by mounting', () => {
    mountMenu()

    expect(refetch).not.toHaveBeenCalled()
  })

  it('refetches the preview each time the panel opens, not when it closes', async () => {
    const wrapper = mountMenu()
    const popover = wrapper.findComponent(Popover)

    popover.vm.$emit('update:open', true)
    await wrapper.vm.$nextTick()
    expect(refetch).toHaveBeenCalledTimes(1)

    popover.vm.$emit('update:open', false)
    await wrapper.vm.$nextTick()
    expect(refetch).toHaveBeenCalledTimes(1)

    popover.vm.$emit('update:open', true)
    await wrapper.vm.$nextTick()
    expect(refetch).toHaveBeenCalledTimes(2)
  })
})
