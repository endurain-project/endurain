import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { StepsEntry } from '@/features/health/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthStepsFormDialog from '@/features/health/components/HealthStepsFormDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const passthrough = { template: '<div><slot /></div>' }

const entry: StepsEntry = {
  id: 7,
  userId: 1,
  version: 2,
  date: '2026-10-30',
  steps: 900,
  source: null,
}

async function openDialog(entryProp: StepsEntry | null) {
  const wrapper = mount(HealthStepsFormDialog, {
    props: { open: false, entry: entryProp },
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
  return wrapper
}

describe('HealthStepsFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({} as never)
  })

  it('sends the request when editing the steps', async () => {
    const wrapper = await openDialog(entry)
    await wrapper.get('input[type="number"]').setValue('1200')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(vi.mocked(apiFetch).mock.calls[0])).toContain('1200')
    expect(wrapper.emitted('error')).toBeUndefined()
    expect(wrapper.emitted('success')).toHaveLength(1)
  })
})
