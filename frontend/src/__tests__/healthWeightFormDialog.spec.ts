import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { WeightEntry } from '@/features/health/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthWeightFormDialog from '@/features/health/components/HealthWeightFormDialog.vue'

// Replace only the network seam; keep a real `HttpError` for the dialog's `instanceof` check.
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

const entry: WeightEntry = {
  id: 3,
  userId: 1,
  version: 4,
  date: '2026-10-30',
  weightKg: 84.6,
  bmi: 22.7,
  bodyFatPct: null,
  bodyWaterPct: null,
  boneMassKg: null,
  muscleMassKg: null,
  source: null,
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog(
  props: { entry?: WeightEntry | null; weightUnits?: 'metric' | 'imperial' } = {},
) {
  return mount(HealthWeightFormDialog, {
    props: { open: false, entry: null, weightUnits: 'metric', ...props },
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

type Wrapper = Awaited<ReturnType<typeof openDialog>>

/** Mounts the dialog closed, then opens it: the form is seeded from `entry` on open. */
async function openDialog(props: Parameters<typeof mountDialog>[0] = {}) {
  const wrapper = mountDialog(props)
  await wrapper.setProps({ open: true })
  return wrapper
}

/** The inputs in form order: date, weight, body fat, body water, bone mass, muscle mass. */
const inputs = (wrapper: Wrapper) => wrapper.findAll('input')

async function save(wrapper: Wrapper): Promise<Record<string, unknown>> {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(apiFetch).toHaveBeenCalledTimes(1)
  const init = vi.mocked(apiFetch).mock.calls[0]![1] as { body: string }
  return JSON.parse(init.body) as Record<string, unknown>
}

describe('HealthWeightFormDialog submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({ ...entry, weight_kg: 77.2, version: 5 })
  })

  it('saves a typed weight', async () => {
    // Regression: `<input type="number">` + `v-model` yields a `number`, which previously crashed
    // `massToKg` (`raw.trim()`) before any request, so Save silently did nothing.
    const wrapper = await openDialog()

    await inputs(wrapper)[1]!.setValue('77.2')

    expect((await save(wrapper)).weight_kg).toBe(77.2)
    expect(wrapper.emitted('success')).toBeTruthy()
  })

  it('offers no BMI input and sends no BMI', async () => {
    const wrapper = await openDialog({ entry })

    await inputs(wrapper)[1]!.setValue('77.2')

    expect(inputs(wrapper)).toHaveLength(6)
    const body = await save(wrapper)
    expect(body.weight_kg).toBe(77.2)
    expect(body).not.toHaveProperty('bmi')
  })

  it('sends no bone or muscle mass when those fields are blank', async () => {
    const wrapper = await openDialog()

    await inputs(wrapper)[1]!.setValue('77.2')

    const body = await save(wrapper)
    expect(body.bone_mass_kg).toBeNull()
    expect(body.muscle_mass_kg).toBeNull()
  })

  it('sends bone and muscle mass in kilograms', async () => {
    const wrapper = await openDialog({ weightUnits: 'imperial' })

    await inputs(wrapper)[1]!.setValue('170')
    await inputs(wrapper)[4]!.setValue('6.6')
    await inputs(wrapper)[5]!.setValue('66')

    const body = await save(wrapper)
    expect(body.weight_kg).toBeCloseTo(77.111, 3)
    expect(body.bone_mass_kg).toBeCloseTo(2.994, 3)
    expect(body.muscle_mass_kg).toBeCloseTo(29.937, 3)
  })
})
