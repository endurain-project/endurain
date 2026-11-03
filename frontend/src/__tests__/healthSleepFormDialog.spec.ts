import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthSleepFormDialog from '@/features/health/components/HealthSleepFormDialog.vue'

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

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog() {
  const wrapper = mount(HealthSleepFormDialog, {
    props: { open: false, entry: null },
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
