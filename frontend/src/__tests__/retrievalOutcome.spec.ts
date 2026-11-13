import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import { useRetrievalOutcome } from '@/features/integrations/composables/useIntegrations'
import { HttpError } from '@/services/http'
import { followJob, JobTimeoutError } from '@/services/jobStatus'

vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  followJob: vi.fn<typeof followJob>(),
}))

const job = {
  id: '00000000-0000-4000-8000-0000000000a1',
  kind: 'strava_gear',
  created_at: '2026-01-01T00:00:00Z',
} as const

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountOutcome() {
  let outcome!: ReturnType<typeof useRetrievalOutcome>
  wrapper = mount(
    defineComponent({
      setup() {
        outcome = useRetrievalOutcome('Strava')
        return () => h('div')
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return outcome
}

/** The kinds of the toasts shown since `before` toasts were on screen. */
function toastKindsSince(before: number): string[] {
  return useToasts()
    .toasts.value.slice(before)
    .map((toast) => toast.kind)
}

describe('useRetrievalOutcome', () => {
  it('toasts success when the followed job succeeds', async () => {
    vi.mocked(followJob).mockResolvedValue({ ...job, status: 'succeeded' } as never)
    const before = useToasts().toasts.value.length
    await mountOutcome().follow('00000000-0000-4000-8000-0000000000a1')
    await flushPromises()

    expect(followJob).toHaveBeenCalledWith('00000000-0000-4000-8000-0000000000a1')
    expect(toastKindsSince(before)).toEqual(['success'])
  })

  it('toasts an error when the followed job fails or cannot be read', async () => {
    vi.mocked(followJob).mockResolvedValueOnce({ ...job, status: 'failed' } as never)
    vi.mocked(followJob).mockRejectedValueOnce(new Error('network'))
    const before = useToasts().toasts.value.length
    const outcome = mountOutcome()
    await outcome.follow('00000000-0000-4000-8000-0000000000a1')
    await outcome.follow('00000000-0000-4000-8000-0000000000a1')

    expect(toastKindsSince(before)).toEqual(['error', 'error'])
  })

  it('stays quiet when it gives up following a job that is still running', async () => {
    vi.mocked(followJob).mockRejectedValue(new JobTimeoutError())
    const before = useToasts().toasts.value.length
    await mountOutcome().follow('00000000-0000-4000-8000-0000000000a1')

    expect(toastKindsSince(before)).toEqual([])
  })

  it('follows the running job a 409 names and says it is already running', async () => {
    vi.mocked(followJob).mockResolvedValue({ ...job, status: 'succeeded' } as never)
    const before = useToasts().toasts.value.length
    const conflict = new HttpError(
      409,
      'Conflict',
      null,
      null,
      null,
      [],
      null,
      '00000000-0000-4000-8000-0000000000a9',
    )

    expect(mountOutcome().resumeOnConflict(conflict)).toBe(true)
    await flushPromises()

    expect(followJob).toHaveBeenCalledWith('00000000-0000-4000-8000-0000000000a9')
    expect(toastKindsSince(before)).toEqual(['info', 'success'])
  })

  it('leaves any other failure, including a 409 that names no job, to the caller', () => {
    const outcome = mountOutcome()

    expect(outcome.resumeOnConflict(new HttpError(409, 'Conflict'))).toBe(false)
    expect(outcome.resumeOnConflict(new HttpError(500, 'Server Error'))).toBe(false)
    expect(followJob).not.toHaveBeenCalled()
  })
})
