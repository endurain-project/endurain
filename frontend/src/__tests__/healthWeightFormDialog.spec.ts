import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { WeightEntry } from '@/features/health/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthWeightFormDialog from '@/features/health/components/HealthWeightFormDialog.vue'

// Replace only the network seam; keep a real `HttpError` for the dialog's
// `instanceof` check in its error path.
vi.mock('@/services/http', () => {
  class HttpError extends Error {
    constructor(
      public status: number,
      message?: string,
    ) {
      super(message)
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog(entry: WeightEntry | null = null) {
  return mount(HealthWeightFormDialog, {
    props: { open: false, entry, weightUnits: 'metric' as const },
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
}

/** Opens the dialog, applies `change`, submits, and returns the request body. */
async function submit(
  entry: WeightEntry | null,
  change: (wrapper: ReturnType<typeof mountDialog>) => Promise<void>,
) {
  vi.mocked(apiFetch).mockResolvedValue({ id: 3, user_id: 1, version: 2 })
  const wrapper = mountDialog(entry)
  await wrapper.setProps({ open: true })
  await change(wrapper)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(apiFetch).toHaveBeenCalledTimes(1)
  const [, init] = vi.mocked(apiFetch).mock.calls[0]!
  return JSON.parse(String(init!.body))
}

describe('HealthWeightFormDialog submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('creates the entry from a typed weight and leaves empty masses null', async () => {
    const body = await submit(null, async (wrapper) => {
      await wrapper.find('input[step="0.1"]').setValue('80')
    })
    expect(body.weight).toBe(80)
    expect(body.bone_mass).toBeNull()
    expect(body.muscle_mass).toBeNull()
  })
})
