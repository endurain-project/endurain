import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { Component } from 'vue'
import type { VueWrapper } from '@vue/test-utils'
import type { Gear, GearComponent } from '@/features/gears/types'
import type { Goal } from '@/features/goals/types'
import type { WaterEntry, WeightEntry } from '@/features/health/types'

import i18n from '@/i18n'
import { apiFetch } from '@/services/http'
import GearComponentFormDialog from '@/features/gears/components/GearComponentFormDialog.vue'
import GearFormDialog from '@/features/gears/components/GearFormDialog.vue'
import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'
import HealthWaterFormDialog from '@/features/health/components/HealthWaterFormDialog.vue'
import HealthWeightFormDialog from '@/features/health/components/HealthWeightFormDialog.vue'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

/** Opens an edit dialog in imperial units, submits it as-is or after `edit`, and returns the request body. */
async function save(
  component: Component,
  props: Record<string, unknown>,
  edit?: (wrapper: VueWrapper) => Promise<void>,
): Promise<Record<string, unknown>> {
  const wrapper = mount(component, {
    props: { open: false, ...props },
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
  await edit?.(wrapper)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(apiFetch).toHaveBeenCalledTimes(1)
  const init = vi.mocked(apiFetch).mock.calls[0]![1] as { body: string }
  return JSON.parse(init.body) as Record<string, unknown>
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(apiFetch).mockResolvedValue({})
})

/** Edits a field other than the unit-converted one, so the dialog has something to save. */
const editOtherField = (selector: string, value: string) => async (wrapper: VueWrapper) => {
  await wrapper.find(selector).setValue(value)
}

describe('an untouched imperial field keeps the stored metric value', () => {
  it('weight, bone mass and muscle mass', async () => {
    const entry: WeightEntry = {
      id: 3,
      userId: 1,
      version: 4,
      date: '2026-10-30',
      weightKg: 70.5,
      bmi: 22.7,
      bodyFatPct: null,
      bodyWaterPct: null,
      boneMassKg: 3.1,
      muscleMassKg: 33.3,
      source: null,
    }

    const body = await save(
      HealthWeightFormDialog,
      { entry, weightUnits: 'imperial' },
      editOtherField('input[type="date"]', '2026-10-29'),
    )

    expect(body).toMatchObject({ weight_kg: 70.5, bone_mass_kg: 3.1, muscle_mass_kg: 33.3 })
  })

  it('water', async () => {
    const entry: WaterEntry = {
      id: 9,
      userId: 1,
      version: 2,
      date: '2026-10-30',
      amountMl: 2000,
      source: null,
    }

    expect(
      await save(
        HealthWaterFormDialog,
        { entry, units: 'imperial' },
        editOtherField('input[type="date"]', '2026-10-29'),
      ),
    ).toMatchObject({ amount_ml: 2000 })
  })

  it('gear initial distance', async () => {
    const gear: Gear = {
      id: 2,
      userId: 1,
      gearType: GEAR_TYPE.BICYCLE,
      nickname: 'Road',
      brand: null,
      model: null,
      active: true,
      acquiredOn: '2026-01-01',
      initialKms: 100,
      purchaseValue: null,
      stravaGearId: null,
      garminConnectGearId: null,
      version: 5,
    }

    expect(
      await save(
        GearFormDialog,
        { gear, units: 'imperial', currency: 'euro' },
        editOtherField('input[name="nickname"]', 'Gravel'),
      ),
    ).toMatchObject({ initial_kms: 100 })
  })

  it('gear component expected distance', async () => {
    const component: GearComponent = {
      id: 7,
      userId: 1,
      gearId: 5,
      type: 'chain',
      brand: 'Shimano',
      model: 'XT',
      purchaseDate: '2024-01-10',
      retiredDate: null,
      active: true,
      expectedBaseUnits: 5_000_000,
      purchaseValue: null,
      currentDistance: 0,
      currentTime: 0,
      version: 1,
    }

    expect(
      await save(
        GearComponentFormDialog,
        {
          component,
          gearId: 5,
          gearType: GEAR_TYPE.BICYCLE,
          availableTypes: ['chain'],
          units: 'imperial',
          currency: 'euro',
        },
        editOtherField('input[name="brand"]', 'SRAM'),
      ),
    ).toMatchObject({ expected_kms: 5_000_000 })
  })

  it.each([
    ['distance', { goalType: 'distance', distanceMeters: 10_000 }, { goal_distance: 10_000 }],
    ['duration', { goalType: 'duration', durationSeconds: 3661 }, { goal_duration: 3661 }],
  ])('goal %s', async (_name, target, expected) => {
    const goal: Goal = {
      id: 4,
      userId: 1,
      version: 2,
      interval: 'weekly',
      activityType: 'run',
      calories: null,
      activitiesNumber: null,
      distanceMeters: null,
      elevationMeters: null,
      durationSeconds: null,
      ...target,
    } as Goal

    expect(
      await save(GoalFormDialog, { goal, units: 'imperial' }, async (wrapper) => {
        await wrapper.find('select').setValue('monthly')
      }),
    ).toMatchObject(expected)
  })
})

describe('an edited imperial value is still converted', () => {
  it('water', async () => {
    const entry: WaterEntry = {
      id: 9,
      userId: 1,
      version: 2,
      date: '2026-10-30',
      amountMl: 2000,
      source: null,
    }

    const body = await save(
      HealthWaterFormDialog,
      { entry, units: 'imperial' },
      async (wrapper) => {
        await wrapper.findAll('input')[1]!.setValue('70')
      },
    )

    expect(body.amount_ml).toBe(2070)
  })

  it('weight', async () => {
    const entry = {
      id: 3,
      userId: 1,
      version: 4,
      date: '2026-10-30',
      weightKg: 70.5,
      bmi: null,
      bodyFatPct: null,
      bodyWaterPct: null,
      boneMassKg: null,
      muscleMassKg: null,
      source: null,
    } satisfies WeightEntry

    const body = await save(
      HealthWeightFormDialog,
      { entry, weightUnits: 'imperial' },
      async (wrapper) => {
        await wrapper.findAll('input')[1]!.setValue('170')
      },
    )

    expect(body.weight_kg).toBeCloseTo(77.111, 3)
  })
})
