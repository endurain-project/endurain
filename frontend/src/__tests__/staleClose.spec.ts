import { beforeEach, describe, expect, it, vi } from 'vitest'

import { computed, defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'

import type { Component } from 'vue'
import type { Activity } from '@/features/activities/types'
import type { Gear } from '@/features/gears/types'
import type { HealthTargets, WaterEntry } from '@/features/health/types'
import type { ProfileDetails } from '@/features/profile/types'

import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import { HttpError, apiFetch } from '@/services/http'
import { setActivityGear } from '@/features/activities/services/activities'
import ActivityGearCard from '@/features/activities/components/ActivityGearCard.vue'
import DefaultGearCard from '@/features/profile/components/DefaultGearCard.vue'
import GearFormDialog from '@/features/gears/components/GearFormDialog.vue'
import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'
import HealthFastingTargetDialog from '@/features/health/components/HealthFastingTargetDialog.vue'
import HealthPoopTargetDialog from '@/features/health/components/HealthPoopTargetDialog.vue'
import HealthSleepTargetDialog from '@/features/health/components/HealthSleepTargetDialog.vue'
import HealthStepsFormDialog from '@/features/health/components/HealthStepsFormDialog.vue'
import HealthStepsTargetDialog from '@/features/health/components/HealthStepsTargetDialog.vue'
import HealthWaterTargetDialog from '@/features/health/components/HealthWaterTargetDialog.vue'
import HealthWaterView from '@/features/health/views/HealthWaterView.vue'
import HealthWeightTargetDialog from '@/features/health/components/HealthWeightTargetDialog.vue'
import ProfileFormDialog from '@/features/profile/components/ProfileFormDialog.vue'
import ProfileSettingsView from '@/features/profile/views/ProfileSettingsView.vue'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { FormDialog } from '@/components/ui/form-dialog'
import { makeActivity } from './fixtures/activity'

// Only the network seam is replaced; the real `HttpError` stays so `instanceof` checks hold.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  setActivityGear: vi.fn<typeof setActivityGear>(),
}))

vi.mock('@/features/activities/composables/useActivityDetail', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/composables/useActivityDetail')>()),
  useActivityGearOptionsQuery: () => ({ data: ref([]) }),
}))

vi.mock('@/features/gears/composables/useGears', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/gears/composables/useGears')>()),
  useGearQuery: () => ({ data: ref(undefined) }),
}))

const { profileData, defaultGearData } = await vi.hoisted(async () => {
  const { ref: vueRef } = await import('vue')
  return { profileData: vueRef<unknown>(null), defaultGearData: vueRef<unknown>(null) }
})

vi.mock('@/features/profile/composables/useProfile', async (importOriginal) => {
  const { ref: vueRef } = await import('vue')
  const settled = (data: unknown) => ({
    data,
    isPending: vueRef(false),
    isError: vueRef(false),
    refetch: vi.fn<() => void>(),
  })
  return {
    ...(await importOriginal<typeof import('@/features/profile/composables/useProfile')>()),
    useProfileQuery: () => settled(profileData),
  }
})

vi.mock('@/features/profile/composables/useDefaultGear', async (importOriginal) => {
  const { ref: vueRef } = await import('vue')
  const settled = (data: unknown) => ({
    data,
    isPending: vueRef(false),
    isError: vueRef(false),
    refetch: vi.fn<() => void>(),
  })
  return {
    ...(await importOriginal<typeof import('@/features/profile/composables/useDefaultGear')>()),
    useDefaultGearQuery: () => settled(defaultGearData),
    useGearTypeOptionsQuery: () => settled(vueRef({})),
  }
})

const waterEntry: WaterEntry = {
  id: 9,
  userId: 1,
  version: 2,
  date: '2026-10-30',
  amountMl: 500,
  source: null,
}

vi.mock('@/features/health/composables/useHealth', async (importOriginal) => {
  const { ref: vueRef } = await import('vue')
  const settled = (data: unknown) => ({
    data: vueRef(data),
    isPending: vueRef(false),
    isError: vueRef(false),
    refetch: vi.fn<() => void>(),
  })
  return {
    ...(await importOriginal<typeof import('@/features/health/composables/useHealth')>()),
    useHealthTargetsQuery: () => settled(null),
    useWaterEntriesQuery: () => settled({ records: [waterEntry], total: 1 }),
    useHealthChartQuery: () => settled(undefined),
    useDeleteWaterEntryMutation: () => ({
      mutate: (_vars: unknown, options: { onError: (error: unknown) => void }) =>
        options.onError(new HttpError(412, 'Precondition Failed')),
      isPending: vueRef(false),
    }),
  }
})

vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ units: 'metric' }) }),
}))

vi.mock('@/features/config/composables/useRecordsPerPage', () => ({
  useRecordsPerPage: () => ({ recordsPerPage: computed(() => 25) }),
}))

vi.mock('@/composables/useChartProvider', () => ({
  useChartProvider: () => ({ isAvailable: false }),
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
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
}

const targets: HealthTargets = {
  id: 1,
  userId: 1,
  version: 3,
  sleepSeconds: 28800,
  steps: 8000,
  weightKg: 70,
  fastingSeconds: 57600,
  waterMl: 2000,
  poopCount: 1,
}

const profile = {
  id: 1,
  version: 1,
  name: 'Tester',
  username: 'tester',
  email: 'tester@example.com',
  gender: 'unspecified',
  units: 'metric',
  currency: 'euro',
  height: 172,
  preferredLanguage: 'en',
  firstDayOfWeek: 'monday',
  timezone: 'UTC',
  accessType: 'regular',
  hasLocalPassword: true,
  integrationsVersion: 1,
  privacy: {},
} as unknown as ProfileDetails

const gear: Gear = {
  id: 2,
  userId: 1,
  gearType: 1,
  nickname: 'Road',
  brand: null,
  model: null,
  active: true,
  acquiredOn: null,
  initialKms: null,
  purchaseValue: null,
  stravaGearId: null,
  garminConnectGearId: null,
  version: 5,
}

/** A form dialog that, when submitted against a 412, must close and say nothing was saved. */
const dialogs: [string, Component, Record<string, unknown>][] = [
  ['ProfileFormDialog', ProfileFormDialog, { profile }],
  ['GearFormDialog', GearFormDialog, { gear, units: 'metric', currency: 'euro' }],
  [
    'GoalFormDialog',
    GoalFormDialog,
    {
      units: 'metric',
      goal: {
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
      },
    },
  ],
  [
    'HealthStepsFormDialog',
    HealthStepsFormDialog,
    { entry: { id: 1, userId: 1, version: 2, date: '2026-10-30', steps: 900, source: null } },
  ],
  ['HealthStepsTargetDialog', HealthStepsTargetDialog, { targets }],
  ['HealthSleepTargetDialog', HealthSleepTargetDialog, { targets }],
  ['HealthPoopTargetDialog', HealthPoopTargetDialog, { targets }],
  ['HealthFastingTargetDialog', HealthFastingTargetDialog, { targets }],
  ['HealthWaterTargetDialog', HealthWaterTargetDialog, { targets, units: 'metric' }],
  ['HealthWeightTargetDialog', HealthWeightTargetDialog, { targets, weightUnits: 'metric' }],
]

describe('a dialog whose save is refused as stale', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each(dialogs)(
    '%s closes instead of keeping the stale copy open',
    async (_name, dialog, props) => {
      vi.mocked(apiFetch).mockRejectedValue(stale)
      const wrapper = mount(dialog, {
        props: { open: false, ...props },
        global: {
          plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
          stubs: dialogStubs,
        },
      })
      // The form seeds itself when the dialog opens.
      await wrapper.setProps({ open: true })
      // An unchanged edit is not sent, so change the first field.
      const field = wrapper.find('input')
      const isDate = field.attributes('type') === 'date'
      await field.setValue(isDate ? '2026-10-29' : `${(field.element as HTMLInputElement).value}1`)

      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.emitted('error')).toEqual([[staleMessage]])
      expect(wrapper.emitted('update:open')).toEqual([[false]])
    },
  )
})

// Toasts live in module state; clear them so each test sees only its own.
beforeEach(() => {
  const { toasts, dismiss } = useToasts()
  toasts.value.forEach((toast) => dismiss(toast.id))
})

describe('a delete confirmation refused as stale', () => {
  it('closes the health delete dialog and names the stale copy', async () => {
    const { toasts } = useToasts()
    const wrapper = mount(HealthWaterView, {
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: { ...dialogStubs, HealthWaterFormDialog: true, HealthWaterTargetDialog: true },
      },
    })
    const confirm = wrapper.findComponent(ConfirmDialog)

    wrapper.findComponent({ name: 'HealthWaterListItem' }).vm.$emit('delete', waterEntry)
    await flushPromises()
    expect(confirm.props('open')).toBe(true)

    confirm.vm.$emit('confirm')
    await flushPromises()

    expect(toasts.value.map((toast) => toast.message)).toContain(staleMessage)
    expect(confirm.props('open')).toBe(false)
  })
})

describe('ActivityGearCard', () => {
  beforeEach(() => {
    vi.mocked(setActivityGear).mockRejectedValue(stale)
  })

  function mountCard() {
    const activity: Activity = makeActivity({ id: 5, gearId: 2, activityType: 1 })
    return mount(ActivityGearCard, {
      props: { activity },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: dialogStubs,
      },
    })
  }

  it('names the stale copy and closes the picker when the gear save is refused', async () => {
    const { toasts } = useToasts()
    const picker = mountCard().findComponent(FormDialog)
    picker.vm.$emit('update:open', true)
    await flushPromises()

    picker.vm.$emit('submit')
    await flushPromises()

    const messages = toasts.value.map((toast) => toast.message)
    expect(messages).toEqual([staleMessage])
    expect(picker.props('open')).toBe(false)
  })

  it('names the stale copy and closes the remove dialog when the removal is refused', async () => {
    const { toasts } = useToasts()
    const confirm = mountCard().findComponent(ConfirmDialog)
    confirm.vm.$emit('update:open', true)
    await flushPromises()

    confirm.vm.$emit('confirm')
    await flushPromises()

    const messages = toasts.value.map((toast) => toast.message)
    expect(messages).toEqual([staleMessage])
    expect(confirm.props('open')).toBe(false)
  })
})

/** Stands in for a keyed inline form, counting how many times it is built. */
function countingStub(mounted: { count: number }): Component {
  return defineComponent({
    created() {
      mounted.count += 1
    },
    template: '<div />',
  })
}

describe('inline forms keyed on the resource version', () => {
  const plugins = () => [
    i18n,
    createPinia(),
    [VueQueryPlugin, { queryClient: new QueryClient() }] as [typeof VueQueryPlugin, unknown],
  ]

  it('rebuilds the privacy form when the profile refetch changes its version', async () => {
    const mounted = { count: 0 }
    profileData.value = { ...profile, privacy: { version: 1 } } as ProfileDetails
    const wrapper = mount(ProfileSettingsView, {
      global: {
        plugins: plugins(),
        stubs: {
          PrivacySettingsCard: countingStub(mounted),
          ProfileInfoCard: true,
          DefaultGearCard: true,
          DataTransferCard: true,
        },
      },
    })
    expect(mounted.count).toBe(1)

    profileData.value = { ...profile, privacy: { version: 2 } } as ProfileDetails
    await flushPromises()

    expect(mounted.count).toBe(2)
    wrapper.unmount()
  })

  it('rebuilds the default gear form when the refetch changes its version', async () => {
    const mounted = { count: 0 }
    defaultGearData.value = { id: 1, userId: 1, version: 1 }
    const wrapper = mount(DefaultGearCard, {
      global: { plugins: plugins(), stubs: { DefaultGearForm: countingStub(mounted) } },
    })
    expect(mounted.count).toBe(1)

    defaultGearData.value = { id: 1, userId: 1, version: 2 }
    await flushPromises()

    expect(mounted.count).toBe(2)
    wrapper.unmount()
  })
})
