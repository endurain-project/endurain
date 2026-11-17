import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { authedPinia } from './fixtures/authedPinia'
import type { SleepListEntry } from '@/features/health/types'
import HealthSleepFormDialog from '@/features/health/components/HealthSleepFormDialog.vue'

vi.mock('@/services/http', () => {
  class HttpError extends Error {
    constructor(
      public status: number,
      message?: string,
      public detail: unknown = null,
      public type: string | null = null,
    ) {
      super(message)
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog() {
  const wrapper = mount(HealthSleepFormDialog, {
    props: { open: false, entry: null },
    global: {
      plugins: [i18n, authedPinia(), [VueQueryPlugin, { queryClient: new QueryClient() }]],
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

type Wrapper = Awaited<ReturnType<typeof openDialog>>

async function setInput(wrapper: Wrapper, selector: string, value: string, nth = 0) {
  const input = wrapper.findAll(selector)[nth]!
  await input.setValue(value)
}

async function submit(wrapper: Wrapper) {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

const sectionOpen = (wrapper: Wrapper, index: number) =>
  (wrapper.findAll('details')[index]!.element as HTMLDetailsElement).open

describe('HealthSleepFormDialog layout', () => {
  it('uses a wide dialog and inputs that may shrink', async () => {
    const wrapper = await openDialog()
    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThan(0)
    for (const input of inputs) {
      expect(input.classes()).toContain('min-w-0')
      expect(input.classes()).toContain('w-full')
    }
    expect(wrapper.html()).toContain('max-w-2xl')
  })
})

describe('HealthSleepFormDialog validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({})
  })

  it('shows a message when total sleep is missing and does not save', async () => {
    const wrapper = await openDialog()
    await submit(wrapper)
    expect(wrapper.text()).toContain('Please enter how long you slept.')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('shows the end-before-start error and opens its section', async () => {
    const wrapper = await openDialog()
    await setInput(wrapper, 'input[type="number"]', '7')
    await setInput(wrapper, 'input[type="datetime-local"]', '2026-10-30T08:00', 0)
    await setInput(wrapper, 'input[type="datetime-local"]', '2026-10-30T07:00', 1)
    await submit(wrapper)
    expect(wrapper.text()).toContain('Sleep end must be after the start time.')
    expect(sectionOpen(wrapper, 0)).toBe(true)
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('rejects an out-of-range heart rate, opening its section', async () => {
    const wrapper = await openDialog()
    await setInput(wrapper, 'input[type="number"]', '7')
    const rest = wrapper.find('input[type="number"][max="220"]')
    await rest.setValue('300')
    await submit(wrapper)
    expect(wrapper.text()).toContain('Enter a value between 20 and 220.')
    expect(sectionOpen(wrapper, 2)).toBe(true)
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('rejects minutes above 59', async () => {
    const wrapper = await openDialog()
    await setInput(wrapper, 'input[type="number"]', '7', 0)
    await setInput(wrapper, 'input[type="number"]', '75', 1)
    await submit(wrapper)
    expect(wrapper.text()).toContain('Enter a value between 0 and 59.')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('saves a valid entry', async () => {
    const wrapper = await openDialog()
    await setInput(wrapper, 'input[type="number"]', '7')
    await submit(wrapper)
    expect(apiFetch).toHaveBeenCalledTimes(1)
  })
})

describe('HealthSleepFormDialog stage consistency', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({})
  })

  /** Fills total sleep, then deep, light and REM hours (inputs 0, 2, 4, 6 of the number inputs). */
  async function fill(wrapper: Wrapper, total: string, deep: string, light: string, rem: string) {
    await setInput(wrapper, 'input[type="number"]', total, 0)
    await setInput(wrapper, 'input[type="number"]', deep, 2)
    await setInput(wrapper, 'input[type="number"]', light, 4)
    await setInput(wrapper, 'input[type="number"]', rem, 6)
  }

  it('refuses stages that add up to more than the total and does not save', async () => {
    const wrapper = await openDialog()
    await fill(wrapper, '7', '4', '3', '1')
    await submit(wrapper)

    expect(wrapper.text()).toContain('Deep, light and REM sleep add up to more than the total.')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('accepts stages that match the total', async () => {
    const wrapper = await openDialog()
    await fill(wrapper, '8', '4', '3', '1')
    await submit(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
  })

  it('accepts stages that exceed the total by exactly a minute', async () => {
    const wrapper = await openDialog()
    await fill(wrapper, '7', '4', '3', '')
    await setInput(wrapper, 'input[type="number"]', '1', 7)
    await submit(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
  })

  it('shows a specific message when the server refuses the figures', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await openDialog()
    await setInput(wrapper, 'input[type="number"]', '7')
    await submit(wrapper)

    expect(wrapper.emitted('error')?.[0]).toEqual([
      "These sleep figures don't add up. Check that the stages and the total fit within the sleep times.",
    ])
  })
})

describe('HealthSleepFormDialog hours/minutes names', () => {
  it.each(['Total sleep', 'Deep sleep', 'Light sleep', 'REM sleep', 'Awake'])(
    'names both inputs of the %s pair',
    async (field) => {
      const wrapper = await openDialog()
      for (const unit of ['hours', 'minutes']) {
        const input = wrapper.find(`input[aria-label="${field}, ${unit}"]`)
        expect(input.exists()).toBe(true)
        expect(input.attributes('type')).toBe('number')
      }
    },
  )
})

describe('HealthSleepFormDialog edit', () => {
  const row: SleepListEntry = {
    id: '00000000-0000-4000-8000-000000000005',
    userId: '00000000-0000-4000-8000-000000000009',
    version: 1,
    date: '2026-06-25',
    totalSleepSeconds: 7 * 3600,
    hasSleepStages: true,
  } as SleepListEntry

  /** The full record the single read returns: a newer version than the list row, with one stage. */
  const fullDto = {
    id: '00000000-0000-4000-8000-000000000005',
    user_id: '00000000-0000-4000-8000-000000000009',
    version: 4,
    date: '2026-06-25',
    total_sleep_seconds: 8 * 3600,
    sleep_stages: [
      {
        stage_type: 'deep',
        start_time_gmt: '2026-06-24T23:00:00',
        end_time_gmt: '2026-06-25T00:30:00',
        duration_seconds: 5400,
      },
    ],
  }

  async function openEdit(retry = true) {
    const wrapper = mount(HealthSleepFormDialog, {
      props: { open: false, entry: row },
      global: {
        plugins: [
          i18n,
          authedPinia(),
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry } } }) },
          ],
        ],
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

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a loading state, then fills the form from the full record', async () => {
    let resolve: (value: unknown) => void = () => undefined
    vi.mocked(apiFetch).mockReturnValue(new Promise((done) => (resolve = done)))

    const wrapper = await openEdit()

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/sleep/00000000-0000-4000-8000-000000000005',
      expect.anything(),
    )
    expect(wrapper.text()).toContain(i18n.global.t('health.sleep.form.loading'))
    expect(wrapper.find('input').exists()).toBe(false)

    resolve(fullDto)
    await flushPromises()

    expect(wrapper.text()).not.toContain(i18n.global.t('health.sleep.form.loading'))
    // The total comes from the full record (8 h), not the list row (7 h).
    expect((wrapper.findAll('input[type="number"]')[0]!.element as HTMLInputElement).value).toBe(
      '8',
    )
    // The stage row comes from the full record; the list row has none.
    expect(wrapper.text()).toContain('Stage 1')
  })

  it('sends the version of the full record as If-Match', async () => {
    vi.mocked(apiFetch).mockResolvedValue(fullDto)
    const wrapper = await openEdit()
    await flushPromises()

    await setInput(wrapper, 'input[type="number"]', '7', 0)
    await submit(wrapper)

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/sleep/00000000-0000-4000-8000-000000000005',
      expect.objectContaining({ method: 'PATCH', headers: { 'If-Match': '"4"' } }),
    )
  })

  it('offers a retry when the record cannot be read', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('boom'))
    const wrapper = await openEdit(false)
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('health.sleep.form.loadError'))
    expect(wrapper.find('input').exists()).toBe(false)
  })
})
