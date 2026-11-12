import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'

import type { Gear } from '@/features/gears/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GearDeleteDialog from '@/features/gears/components/GearDeleteDialog.vue'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))
vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

const gear: Gear = {
  id: '00000000-0000-4000-8000-000000000002',
  userId: 1,
  gearType: 'bike',
  nickname: 'Road',
  brand: null,
  model: null,
  active: true,
  acquiredOn: '2026-01-01',
  initialKms: null,
  purchaseValue: null,
  stravaGearId: null,
  garminConnectGearId: null,
  version: 5,
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the dialog renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog(total: number, componentCount?: number) {
  vi.mocked(apiFetch).mockResolvedValue({ items: [], total })
  setActivePinia(createPinia())
  const wrapper = mount(GearDeleteDialog, {
    props: { open: false, gear, pending: false, componentCount },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
      },
    },
  })
  await wrapper.setProps({ open: true })
  await flushPromises()
  return wrapper
}

describe('GearDeleteDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('says how many activities use the gear and that they are kept', async () => {
    const wrapper = await openDialog(3)

    expect(wrapper.text()).toContain(
      '3 activities use this gear; they will be kept and unassigned.',
    )
    expect(String(vi.mocked(apiFetch).mock.calls[0]![0])).toContain('num_records=1')
  })

  it('uses the singular for one activity and mentions the components', async () => {
    const wrapper = await openDialog(1, 2)

    expect(wrapper.text()).toContain('1 activity uses this gear; it will be kept and unassigned.')
    expect(wrapper.text()).toContain('Its 2 components will be deleted.')
  })

  it('adds nothing when no activity uses the gear', async () => {
    const wrapper = await openDialog(0)

    expect(wrapper.text()).not.toContain('unassigned')
  })
})
