import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { Goal } from '@/features/goals/types'

import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import { HttpError, apiFetch } from '@/services/http'
import { isStaleWrite } from '@/services/ifMatch'
import { queryKeys } from '@/services/queryKeys'
import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'
import HealthStepsTargetDialog from '@/features/health/components/HealthStepsTargetDialog.vue'
import StravaCard from '@/features/integrations/components/StravaCard.vue'
import StravaConnectDialog from '@/features/integrations/components/StravaConnectDialog.vue'

// Only the network seam is replaced; the real `HttpError` stays so `instanceof` checks hold.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const staleMessage = i18n.global.t('app.staleError')
const stale = new HttpError(412, 'Precondition Failed')

/** Passthrough stub so the reka-ui portal/focus-trap is skipped. */
const passthrough = { template: '<div><slot /></div>' }
const dialogStubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
}

describe('isStaleWrite', () => {
  it('is true only for a 412 HttpError', () => {
    expect(isStaleWrite(stale)).toBe(true)
    expect(isStaleWrite(new HttpError(409, 'Conflict'))).toBe(false)
    expect(isStaleWrite(new Error('412'))).toBe(false)
    expect(isStaleWrite(null)).toBe(false)
  })
})

describe('a stale versioned write', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('names the stale copy and refetches when a goal edit is refused', async () => {
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    vi.mocked(apiFetch).mockRejectedValue(stale)
    const goal: Goal = {
      id: 4,
      userId: 1,
      version: 2,
      interval: 'weekly',
      activityType: 'run',
      goalType: 'activities',
      calories: null,
      activitiesNumber: 3,
      distanceMeters: null,
      elevationMeters: null,
      durationSeconds: null,
    }
    const wrapper = mount(GoalFormDialog, {
      props: { open: true, goal, units: 'metric' },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]], stubs: dialogStubs },
    })

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('error')).toEqual([[staleMessage]])
    expect(invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: queryKeys.goals.all() }),
    )
  })

  it('names the stale copy when a health target save is refused', async () => {
    vi.mocked(apiFetch).mockRejectedValue(stale)
    const wrapper = mount(HealthStepsTargetDialog, {
      props: {
        open: true,
        targets: { id: 1, userId: 1, version: 3, steps: 8000 } as never,
      },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: dialogStubs,
      },
    })

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('error')).toEqual([[staleMessage]])
  })

  it('refetches the profile and names the stale copy when the Strava client is refused', async () => {
    vi.mocked(apiFetch).mockImplementation((path) =>
      path === '/strava/client' ? Promise.reject(stale) : Promise.resolve('state-1'),
    )
    const queryClient = new QueryClient()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    const { toasts } = useToasts()
    const wrapper = mount(StravaCard, {
      props: { linked: false, integrationsVersion: 1 },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]], stubs: dialogStubs },
    })

    wrapper
      .findComponent(StravaConnectDialog)
      .vm.$emit('submit', { clientId: 1, clientSecret: 'secret' })
    await flushPromises()

    expect(toasts.value.map((toast) => toast.message)).toContain(staleMessage)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: queryKeys.profile.all() })
  })
})
