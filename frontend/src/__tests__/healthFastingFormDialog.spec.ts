import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { FastingEntry } from '@/features/health/types'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthFastingFormDialog from '@/features/health/components/HealthFastingFormDialog.vue'

// Only the network seam is replaced; the real `HttpError` stays so `instanceof` checks hold.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const entry: FastingEntry = {
  id: 5,
  userId: 1,
  version: 2,
  fastStartTime: '2026-06-25T08:00:00.000Z',
  fastEndTime: '2026-06-25T22:00:00.000Z',
  fastingType: '16:8',
  targetDurationSeconds: 57600,
  actualDurationSeconds: 50400,
  status: 'completed',
  notes: null,
  source: 'manual',
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog(props: { entry?: FastingEntry | null } = {}) {
  const wrapper = mount(HealthFastingFormDialog, {
    props: { open: false, entry: null, ...props },
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

async function submit(wrapper: Wrapper) {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

/** The datetime inputs in form order: start, end (edit only). */
const dateTimes = (wrapper: Wrapper) => wrapper.findAll('input[type="datetime-local"]')

/** The status select, the last select in the form (edit only). */
const statusSelect = (wrapper: Wrapper) => {
  const selects = wrapper.findAll('select')
  return selects[selects.length - 1]!
}

describe('HealthFastingFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({})
  })

  it('sends no actual duration when editing', async () => {
    const wrapper = await openDialog({ entry })
    await submit(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
    const init = vi.mocked(apiFetch).mock.calls[0]![1] as { body: string }
    expect(JSON.parse(init.body)).not.toHaveProperty('actual_duration_seconds')
  })

  it('refuses an end before the start and does not save', async () => {
    const wrapper = await openDialog({ entry })
    await dateTimes(wrapper)[0]!.setValue('2026-06-25T10:00')
    await dateTimes(wrapper)[1]!.setValue('2026-06-25T09:00')
    await submit(wrapper)

    expect(wrapper.text()).toContain('The end time must not be before the start time.')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('shows a specific message when the fast overlaps another', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'),
    )
    const wrapper = await openDialog({ entry })
    await submit(wrapper)

    expect(wrapper.emitted('error')?.[0]).toEqual([
      'This fast overlaps another fasting session, or another fast is already in progress.',
    ])
  })

  it('shows a specific message when the server refuses the times or status', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(400, 'Bad Request'))
    const wrapper = await openDialog({ entry })
    await submit(wrapper)

    expect(wrapper.emitted('error')?.[0]).toEqual([
      'A fast cannot end before it starts, a completed or broken fast needs an end time, and a fast in progress cannot have one.',
    ])
  })

  it('refuses an end time on an in-progress fast beside the end field and does not save', async () => {
    const wrapper = await openDialog({ entry })
    await statusSelect(wrapper).setValue('in_progress')
    await submit(wrapper)

    expect(wrapper.text()).toContain('A fast in progress cannot have an end time.')
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('clears the in-progress error once the status is no longer in progress', async () => {
    const wrapper = await openDialog({ entry })
    const status = statusSelect(wrapper)
    await status.setValue('in_progress')
    expect(wrapper.text()).toContain('A fast in progress cannot have an end time.')

    await status.setValue('completed')

    expect(wrapper.text()).not.toContain('A fast in progress cannot have an end time.')
  })

  it('refuses setting an end time on a running fast until the status changes too', async () => {
    const wrapper = await openDialog({
      entry: { ...entry, fastEndTime: null, status: 'in_progress' },
    })
    await dateTimes(wrapper)[1]!.setValue('2026-06-25T22:00')
    await dateTimes(wrapper)[1]!.trigger('blur')

    expect(wrapper.text()).toContain('A fast in progress cannot have an end time.')

    await statusSelect(wrapper).setValue('completed')
    await submit(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
  })
})
