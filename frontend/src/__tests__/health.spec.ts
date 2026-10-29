import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Schemas } from '@/types'
import type {
  FastingEntryInput,
  PoopEntryInput,
  SleepEntryInput,
  StepsEntryInput,
  WaterEntryInput,
  WeightEntryInput,
} from '@/features/health/types'

import { apiFetch } from '@/services/http'
import {
  completeFastingEntry,
  createFastingEntry,
  createPoopEntry,
  createSleepEntry,
  createStepsEntry,
  createWaterEntry,
  createWeightEntry,
  deleteFastingEntry,
  deletePoopEntry,
  deleteSleepEntry,
  deleteStepsEntry,
  deleteWaterEntry,
  deleteWeightEntry,
  fetchActiveFasting,
  fetchFastingEntries,
  fetchFastingStats,
  fetchHealthChart,
  fetchHealthDashboard,
  fetchPoopEntries,
  fetchRhrEntries,
  fetchSleepEntries,
  fetchStepsEntries,
  fetchWaterEntries,
  fetchWeightEntries,
  updateFastingEntry,
  updateFastingTarget,
  updatePoopEntry,
  updatePoopTarget,
  updateSleepEntry,
  updateSleepTarget,
  updateStepsEntry,
  updateStepsTarget,
  updateWaterEntry,
  updateWaterTarget,
  updateWeightEntry,
  updateWeightTarget,
} from '@/features/health/services/health'
import { formatBodyMass, formatHealthEntryDate } from '@/features/health/utils/healthFormat'
import { kgToLbs, lbsToKg } from '@/utils/units'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

describe('health dashboard service', () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset())

  it('maps dashboard metrics and targets from one response', async () => {
    const targets: Schemas['HealthTargetsRead'] = {
      id: 2,
      user_id: 9,
      version: 3,
      sleep: 28800,
      steps: 8000,
      weight: 70,
      fasting: 57600,
      water_ml: 2000,
      poop_count: 1,
    }
    vi.mocked(apiFetch).mockResolvedValueOnce({
      steps: { steps: 7500 },
      targets,
    })

    const dashboard = await fetchHealthDashboard()

    expect(apiFetch).toHaveBeenCalledExactlyOnceWith('/health/stats/daily', { signal: undefined })
    expect(dashboard.steps).toBe(7500)
    expect(dashboard.targets).toEqual({
      id: 2,
      userId: 9,
      version: 3,
      sleepSeconds: 28800,
      steps: 8000,
      weightKg: 70,
      fastingSeconds: 57600,
      waterMl: 2000,
      poopCount: 1,
    })
  })
})

/** Builds a full HealthWeightRead wire payload, overridable per case. */
function makeWeightDto(
  overrides: Partial<Schemas['HealthWeightRead']> = {},
): Schemas['HealthWeightRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date: '2026-06-25',
    weight: 72.5,
    bmi: 22.1,
    body_fat: 18.4,
    body_water: 55.2,
    bone_mass: 3.2,
    muscle_mass: 34.1,
    metabolic_age: 30,
    physique_rating: 5,
    visceral_fat: 7,
    source: 'garmin',
    ...overrides,
  }
}

/** A clean weight input mirroring {@link makeWeightDto}, in kilograms. */
const input: WeightEntryInput = {
  date: '2026-06-25',
  weightKg: 72.5,
  bmi: 22.1,
  bodyFatPct: 18.4,
  bodyWaterPct: 55.2,
  boneMassKg: 3.2,
  muscleMassKg: 34.1,
}

describe('weight unit conversion', () => {
  it('lbsToKg inverts kgToLbs', () => {
    expect(lbsToKg(kgToLbs(80))).toBeCloseTo(80, 6)
  })

  it('lbsToKg converts a known value', () => {
    expect(lbsToKg(220.462)).toBeCloseTo(100, 3)
  })
})

describe('formatHealthEntryDate', () => {
  it('formats a yyyy-mm-dd date keeping the calendar day (no timezone shift)', () => {
    const formatted = formatHealthEntryDate('2026-06-25', 'en')
    expect(formatted).toContain('25')
    expect(formatted).toContain('2026')
  })

  it('returns an empty string for a missing date', () => {
    expect(formatHealthEntryDate(null)).toBe('')
  })

  it('returns an empty string for a malformed date', () => {
    expect(formatHealthEntryDate('not-a-date')).toBe('')
  })
})

describe('formatBodyMass', () => {
  it('formats kilograms to two decimals for metric users', () => {
    expect(formatBodyMass(3.2, 'metric')).toBe('3.20 kg')
  })

  it('converts to pounds for imperial users', () => {
    expect(formatBodyMass(5, 'imperial')).toBe(`${kgToLbs(5).toFixed(2)} lb`)
  })
})

describe('weight service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchWeightEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeWeightDto(), makeWeightDto({ id: 6, source: null, weight: null, bmi: null })],
    } satisfies Schemas['Page_HealthWeightRead_'])

    const page = await fetchWeightEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/weight?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      date: '2026-06-25',
      weightKg: 72.5,
      bmi: 22.1,
      bodyFatPct: 18.4,
      bodyWaterPct: 55.2,
      boneMassKg: 3.2,
      muscleMassKg: 34.1,
      source: 'garmin',
    })
    expect(page.records[1]).toMatchObject({ id: 6, weightKg: null, bmi: null, source: null })
  })

  it('createWeightEntry POSTs the snake-cased payload as a JSON string', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeWeightDto())

    await createWeightEntry(input)

    expect(apiFetch).toHaveBeenCalledWith('/health/weight', {
      method: 'POST',
      body: JSON.stringify({
        date: '2026-06-25',
        weight: 72.5,
        bmi: 22.1,
        body_fat: 18.4,
        body_water: 55.2,
        bone_mass: 3.2,
        muscle_mass: 34.1,
      }),
    })
  })

  it('updateWeightEntry PATCHes the record path with only the changed fields', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeWeightDto())

    await updateWeightEntry(5, input, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/weight/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({
        date: '2026-06-25',
        weight: 72.5,
        bmi: 22.1,
        body_fat: 18.4,
        body_water: 55.2,
        bone_mass: 3.2,
        muscle_mass: 34.1,
      }),
    })
  })

  it('deleteWeightEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteWeightEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/weight/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updateWeightTarget PATCHes only weight', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      weight: 70,
    } satisfies Schemas['HealthTargetsRead'])

    await updateWeightTarget(3, 70)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ weight: 70 }),
    })
  })

  it('updateWeightTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updateWeightTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ weight: null }),
    })
  })
})

/** Builds a full HealthStepsRead wire payload, overridable per case. */
function makeStepsDto(
  overrides: Partial<Schemas['HealthStepsRead']> = {},
): Schemas['HealthStepsRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date: '2026-06-25',
    steps: 8500,
    source: 'garmin',
    ...overrides,
  }
}

/** A clean steps input mirroring {@link makeStepsDto}. */
const stepsInput: StepsEntryInput = {
  date: '2026-06-25',
  steps: 8500,
}

describe('steps service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchStepsEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeStepsDto(), makeStepsDto({ id: 6, source: null, steps: null })],
    } satisfies Schemas['Page_HealthStepsRead_'])

    const page = await fetchStepsEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/steps?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      date: '2026-06-25',
      steps: 8500,
      source: 'garmin',
    })
    expect(page.records[1]).toMatchObject({ id: 6, steps: null, source: null })
  })

  it('createStepsEntry POSTs the snake-cased payload as a JSON string', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeStepsDto())

    await createStepsEntry(stepsInput)

    expect(apiFetch).toHaveBeenCalledWith('/health/steps', {
      method: 'POST',
      body: JSON.stringify({ date: '2026-06-25', steps: 8500 }),
    })
  })

  it('updateStepsEntry PATCHes the record path with only the changed fields', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeStepsDto())

    await updateStepsEntry(5, stepsInput, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/steps/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ date: '2026-06-25', steps: 8500 }),
    })
  })

  it('deleteStepsEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteStepsEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/steps/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updateStepsTarget PATCHes only steps', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      steps: 10000,
    } satisfies Schemas['HealthTargetsRead'])

    await updateStepsTarget(3, 10000)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ steps: 10000 }),
    })
  })

  it('updateStepsTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updateStepsTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ steps: null }),
    })
  })
})

/** Builds a full HealthWaterRead wire payload, overridable per case. */
function makeWaterDto(
  overrides: Partial<Schemas['HealthWaterRead']> = {},
): Schemas['HealthWaterRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date: '2026-06-25',
    amount_ml: 1500,
    source: 'garmin',
    ...overrides,
  }
}

/** A clean water input mirroring {@link makeWaterDto}, in millilitres. */
const waterInput: WaterEntryInput = {
  date: '2026-06-25',
  amountMl: 1500,
}

describe('water service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchWaterEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeWaterDto(), makeWaterDto({ id: 6, source: null, amount_ml: null })],
    } satisfies Schemas['Page_HealthWaterRead_'])

    const page = await fetchWaterEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/water?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      date: '2026-06-25',
      amountMl: 1500,
      source: 'garmin',
    })
    expect(page.records[1]).toMatchObject({ id: 6, amountMl: null, source: null })
  })

  it('createWaterEntry POSTs the snake-cased payload as a JSON string', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeWaterDto())

    await createWaterEntry(waterInput)

    expect(apiFetch).toHaveBeenCalledWith('/health/water', {
      method: 'POST',
      body: JSON.stringify({ date: '2026-06-25', amount_ml: 1500 }),
    })
  })

  it('updateWaterEntry PATCHes the record path with only the changed fields', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeWaterDto())

    await updateWaterEntry(5, waterInput, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/water/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ date: '2026-06-25', amount_ml: 1500 }),
    })
  })

  it('deleteWaterEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteWaterEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/water/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updateWaterTarget PATCHes only water_ml', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      water_ml: 2000,
    } satisfies Schemas['HealthTargetsRead'])

    await updateWaterTarget(3, 2000)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ water_ml: 2000 }),
    })
  })

  it('updateWaterTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updateWaterTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ water_ml: null }),
    })
  })
})

/** Builds a full HealthPoopRead wire payload, overridable per case. */
function makePoopDto(
  overrides: Partial<Schemas['HealthPoopRead']> = {},
): Schemas['HealthPoopRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date_time: '2026-06-25T08:30:00',
    bristol_type: 4,
    color: 'brown',
    notes: 'Normal',
    source: 'manual',
    ...overrides,
  }
}

/** A clean poop input mirroring {@link makePoopDto}. */
const poopInput: PoopEntryInput = {
  dateTime: '2026-06-25T08:30:00',
  bristolType: 4,
  color: 'brown',
  notes: 'Normal',
}

describe('poop service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchPoopEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makePoopDto(), makePoopDto({ id: 6, bristol_type: null, color: null, notes: null })],
    } satisfies Schemas['Page_HealthPoopRead_'])

    const page = await fetchPoopEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/poop?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      dateTime: '2026-06-25T08:30:00',
      bristolType: 4,
      color: 'brown',
      notes: 'Normal',
    })
    expect(page.records[1]).toMatchObject({ id: 6, bristolType: null, color: null, notes: null })
  })

  it('createPoopEntry POSTs the snake-cased payload as a JSON string', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makePoopDto())

    await createPoopEntry(poopInput)

    expect(apiFetch).toHaveBeenCalledWith('/health/poop', {
      method: 'POST',
      body: JSON.stringify({
        date_time: '2026-06-25T08:30:00',
        bristol_type: 4,
        color: 'brown',
        notes: 'Normal',
      }),
    })
  })

  it('updatePoopEntry PATCHes the record path with only the changed fields', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makePoopDto())

    await updatePoopEntry(5, poopInput, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/poop/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({
        date_time: '2026-06-25T08:30:00',
        bristol_type: 4,
        color: 'brown',
        notes: 'Normal',
      }),
    })
  })

  it('deletePoopEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deletePoopEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/poop/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updatePoopTarget PATCHes only poop_count', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      poop_count: 2,
    } satisfies Schemas['HealthTargetsRead'])

    await updatePoopTarget(3, 2)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ poop_count: 2 }),
    })
  })

  it('updatePoopTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updatePoopTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ poop_count: null }),
    })
  })
})

/** Builds a HealthSleepRead payload with the RHR-relevant fields, overridable per case. */
function makeSleepDto(
  overrides: Partial<Schemas['HealthSleepRead']> = {},
): Schemas['HealthSleepRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date: '2026-06-25',
    resting_heart_rate: 52,
    source: 'garmin',
    ...overrides,
  }
}

describe('resting heart rate service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchRhrEntries reads the sleep history and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeSleepDto(), makeSleepDto({ id: 6, source: null })],
    } satisfies Schemas['Page_HealthSleepRead_'])

    const page = await fetchRhrEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/sleep?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      date: '2026-06-25',
      restingHeartRate: 52,
      source: 'garmin',
    })
    expect(page.records[1]).toMatchObject({ id: 6, restingHeartRate: 52, source: null })
  })

  it('fetchRhrEntries drops sleep records without a resting heart rate but keeps the total', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 3,
      page: 2,
      num_records: 25,
      items: [
        makeSleepDto(),
        makeSleepDto({ id: 6, resting_heart_rate: null }),
        makeSleepDto({ id: 7, resting_heart_rate: undefined }),
      ],
    } satisfies Schemas['Page_HealthSleepRead_'])

    const page = await fetchRhrEntries({ page: 1, numRecords: 25, interval: 'all_time' })

    // Only the record carrying an RHR survives, but the total stays the sleep total.
    expect(page.records).toHaveLength(1)
    expect(page.records[0]).toMatchObject({ id: 5, restingHeartRate: 52 })
    expect(page.total).toBe(3)
  })
})

describe('health chart service', () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset())

  it.each([
    ['sleep', '/health/sleep/chart?interval=last_year'],
    ['rhr', '/health/sleep/chart/resting-heart-rate?interval=last_year'],
    ['steps', '/health/steps/chart?interval=last_year'],
    ['weight', '/health/weight/chart?interval=last_year'],
    ['water', '/health/water/chart?interval=last_year'],
    ['poop', '/health/poop/chart?interval=last_year'],
  ] as const)('fetches the %s series from its own endpoint', async (metric, path) => {
    vi.mocked(apiFetch).mockResolvedValue({
      bucket: 'week',
      points: [{ date: '2026-06-22', value: 7.5 }],
    } satisfies Schemas['HealthChartSeries'])

    const series = await fetchHealthChart(metric, 'last_year')

    expect(apiFetch).toHaveBeenCalledExactlyOnceWith(path, { signal: undefined })
    expect(series).toEqual({ bucket: 'week', points: [{ date: '2026-06-22', value: 7.5 }] })
  })
})

/** Builds a full HealthFastingRead wire payload, overridable per case. */
function makeFastingDto(
  overrides: Partial<Schemas['HealthFastingRead']> = {},
): Schemas['HealthFastingRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    fast_start_time: '2026-06-25T08:00:00.000Z',
    fast_end_time: '2026-06-25T22:00:00.000Z',
    fasting_type: '16:8',
    target_duration_seconds: 57600,
    actual_duration_seconds: 50400,
    status: 'completed',
    notes: 'Felt good',
    source: 'manual',
    ...overrides,
  }
}

/** A clean fasting input mirroring {@link makeFastingDto}. */
const fastingInput: FastingEntryInput = {
  fastStartTime: '2026-06-25T08:00:00.000Z',
  fastEndTime: '2026-06-25T22:00:00.000Z',
  fastingType: '16:8',
  targetDurationSeconds: 57600,
  actualDurationSeconds: 50400,
  status: 'completed',
  notes: 'Felt good',
}

describe('fasting service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchFastingEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeFastingDto(), makeFastingDto({ id: 6, notes: null, source: 'garmin' })],
    } satisfies Schemas['Page_HealthFastingRead_'])

    const page = await fetchFastingEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/fasting?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      fastStartTime: '2026-06-25T08:00:00.000Z',
      fastEndTime: '2026-06-25T22:00:00.000Z',
      fastingType: '16:8',
      targetDurationSeconds: 57600,
      actualDurationSeconds: 50400,
      status: 'completed',
      notes: 'Felt good',
      source: 'manual',
    })
    expect(page.records[1]).toMatchObject({ id: 6, notes: null, source: 'garmin' })
  })

  it('fetchActiveFasting maps the in-progress session', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      makeFastingDto({ status: 'in_progress', fast_end_time: null, actual_duration_seconds: null }),
    )

    const active = await fetchActiveFasting()

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/active', { signal: undefined })
    expect(active).toMatchObject({
      id: 5,
      userId: 9,
      version: 1,
      status: 'in_progress',
      fastEndTime: null,
      actualDurationSeconds: null,
    })
  })

  it('fetchActiveFasting returns null when no fast is in progress', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    const active = await fetchActiveFasting()

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/active', { signal: undefined })
    expect(active).toBeNull()
  })

  it('fetchFastingStats maps the aggregate statistics', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total_fasts: 12,
      current_streak: 3,
      longest_streak: 8,
      avg_duration_seconds: 50400,
      total_fasting_seconds: 604800,
      completion_rate: 75,
    } satisfies Schemas['HealthFastingStatsResponse'])

    const stats = await fetchFastingStats()

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/stats', { signal: undefined })
    expect(stats).toEqual({
      totalFasts: 12,
      currentStreak: 3,
      longestStreak: 8,
      avgDurationSeconds: 50400,
      totalFastingSeconds: 604800,
      completionRate: 75,
    })
  })

  it('createFastingEntry POSTs the snake-cased payload with manual source', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeFastingDto())

    await createFastingEntry(fastingInput)

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting', {
      method: 'POST',
      body: JSON.stringify({
        fast_start_time: '2026-06-25T08:00:00.000Z',
        fasting_type: '16:8',
        target_duration_seconds: 57600,
        notes: 'Felt good',
        source: 'manual',
      }),
    })
  })

  it('updateFastingEntry PATCHes the record path with only the changed fields and no source', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeFastingDto())

    await updateFastingEntry(5, fastingInput, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({
        fast_start_time: '2026-06-25T08:00:00.000Z',
        fast_end_time: '2026-06-25T22:00:00.000Z',
        fasting_type: '16:8',
        target_duration_seconds: 57600,
        actual_duration_seconds: 50400,
        status: 'completed',
        notes: 'Felt good',
      }),
    })
  })

  it('completeFastingEntry POSTs the end time and status to the complete path', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeFastingDto())

    await completeFastingEntry(5, '2026-06-25T22:00:00.000Z', 'broken', 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/5/complete', {
      method: 'POST',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ fast_end_time: '2026-06-25T22:00:00.000Z', status: 'broken' }),
    })
  })

  it('deleteFastingEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteFastingEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/fasting/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updateFastingTarget PATCHes only fasting', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      fasting: 57600,
    } satisfies Schemas['HealthTargetsRead'])

    await updateFastingTarget(3, 57600)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ fasting: 57600 }),
    })
  })

  it('updateFastingTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updateFastingTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ fasting: null }),
    })
  })
})

/** Builds a full HealthSleepRead wire payload, overridable per case. */
function makeFullSleepDto(
  overrides: Partial<Schemas['HealthSleepRead']> = {},
): Schemas['HealthSleepRead'] {
  return {
    id: 5,
    user_id: 9,
    version: 1,
    date: '2026-06-25',
    sleep_start_time_local: '2026-06-24T23:00',
    sleep_end_time_local: '2026-06-25T07:00',
    total_sleep_seconds: 28800,
    deep_sleep_seconds: 7200,
    light_sleep_seconds: 16200,
    rem_sleep_seconds: 4500,
    awake_sleep_seconds: 900,
    sleep_score_overall: 82,
    sleep_score_duration: 'GOOD',
    sleep_score_quality: 'EXCELLENT',
    deep_percentage_score: 'GOOD',
    light_percentage_score: 'FAIR',
    rem_percentage_score: 'EXCELLENT',
    awake_count_score: 'GOOD',
    resting_heart_rate: 52,
    avg_heart_rate: 58,
    min_heart_rate: 48,
    max_heart_rate: 72,
    avg_skin_temp_deviation: 0.3,
    hrv_status: 'BALANCED',
    avg_spo2: 96,
    lowest_spo2: 92,
    highest_spo2: 99,
    avg_respiration: 14,
    lowest_respiration: 11,
    highest_respiration: 18,
    avg_sleep_stress: 25,
    awake_count: 3,
    sleep_stages: [
      {
        stage_type: 0,
        start_time_gmt: '2026-06-24T23:00:00',
        end_time_gmt: '2026-06-25T00:30:00',
        duration_seconds: 5400,
      },
      {
        stage_type: 2,
        start_time_gmt: '2026-06-25T00:30:00',
        end_time_gmt: '2026-06-25T01:15:00',
        duration_seconds: 2700,
      },
    ],
    source: 'garmin',
    ...overrides,
  }
}

/** A clean sleep input mirroring {@link makeFullSleepDto}, in seconds. */
const sleepInput: SleepEntryInput = {
  date: '2026-06-25',
  sleepStartTimeLocal: '2026-06-24T23:00',
  sleepEndTimeLocal: '2026-06-25T07:00',
  totalSleepSeconds: 28800,
  deepSleepSeconds: 7200,
  lightSleepSeconds: 16200,
  remSleepSeconds: 4500,
  awakeSleepSeconds: 900,
  sleepScoreOverall: 82,
  restingHeartRate: 52,
  avgHeartRate: 58,
  minHeartRate: 48,
  maxHeartRate: 72,
  avgSkinTempDeviation: 0.3,
  avgSpo2: 96,
  lowestSpo2: 92,
  highestSpo2: 99,
  avgSleepStress: 25,
  awakeCount: 3,
  sleepStages: [
    {
      stageType: 0,
      startTimeGmt: '2026-06-24T23:00',
      endTimeGmt: '2026-06-25T00:30',
      durationSeconds: 5400,
    },
  ],
}

describe('sleep service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchSleepEntries builds the paginated, filtered URL and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      total: 2,
      page: 2,
      num_records: 25,
      items: [makeFullSleepDto(), makeFullSleepDto({ id: 6, source: null, hrv_status: null })],
    } satisfies Schemas['Page_HealthSleepRead_'])

    const page = await fetchSleepEntries({ page: 2, numRecords: 25, interval: 'last_30_days' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/health/sleep?page_number=2&num_records=25&interval=last_30_days',
      { signal: undefined },
    )
    expect(page.total).toBe(2)
    expect(page.records[0]).toEqual({
      id: 5,
      userId: 9,
      version: 1,
      date: '2026-06-25',
      sleepStartTimeLocal: '2026-06-24T23:00',
      sleepEndTimeLocal: '2026-06-25T07:00',
      totalSleepSeconds: 28800,
      deepSleepSeconds: 7200,
      lightSleepSeconds: 16200,
      remSleepSeconds: 4500,
      awakeSleepSeconds: 900,
      sleepScoreOverall: 82,
      sleepScoreDuration: 'GOOD',
      sleepScoreQuality: 'EXCELLENT',
      deepPercentageScore: 'GOOD',
      lightPercentageScore: 'FAIR',
      remPercentageScore: 'EXCELLENT',
      awakeCountScore: 'GOOD',
      restingHeartRate: 52,
      avgHeartRate: 58,
      minHeartRate: 48,
      maxHeartRate: 72,
      avgSkinTempDeviation: 0.3,
      hrvStatus: 'BALANCED',
      avgSpo2: 96,
      lowestSpo2: 92,
      highestSpo2: 99,
      avgRespiration: 14,
      lowestRespiration: 11,
      highestRespiration: 18,
      avgSleepStress: 25,
      awakeCount: 3,
      sleepStages: [
        {
          stageType: 0,
          startTimeGmt: '2026-06-24T23:00:00',
          endTimeGmt: '2026-06-25T00:30:00',
          durationSeconds: 5400,
        },
        {
          stageType: 2,
          startTimeGmt: '2026-06-25T00:30:00',
          endTimeGmt: '2026-06-25T01:15:00',
          durationSeconds: 2700,
        },
      ],
      source: 'garmin',
    })
    expect(page.records[1]).toMatchObject({ id: 6, source: null, hrvStatus: null })
  })

  it('createSleepEntry POSTs the snake-cased payload (no source)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeFullSleepDto())

    await createSleepEntry(sleepInput)

    expect(apiFetch).toHaveBeenCalledWith('/health/sleep', {
      method: 'POST',
      body: JSON.stringify({
        date: '2026-06-25',
        sleep_start_time_local: '2026-06-24T23:00',
        sleep_end_time_local: '2026-06-25T07:00',
        total_sleep_seconds: 28800,
        deep_sleep_seconds: 7200,
        light_sleep_seconds: 16200,
        rem_sleep_seconds: 4500,
        awake_sleep_seconds: 900,
        sleep_score_overall: 82,
        resting_heart_rate: 52,
        avg_heart_rate: 58,
        min_heart_rate: 48,
        max_heart_rate: 72,
        avg_skin_temp_deviation: 0.3,
        avg_spo2: 96,
        lowest_spo2: 92,
        highest_spo2: 99,
        awake_count: 3,
        avg_sleep_stress: 25,
        sleep_stages: [
          {
            stage_type: 0,
            start_time_gmt: '2026-06-24T23:00',
            end_time_gmt: '2026-06-25T00:30',
            duration_seconds: 5400,
          },
        ],
      }),
    })
  })

  it('updateSleepEntry PATCHes the record path with only the changed fields', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeFullSleepDto())

    await updateSleepEntry(5, sleepInput, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/sleep/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({
        date: '2026-06-25',
        sleep_start_time_local: '2026-06-24T23:00',
        sleep_end_time_local: '2026-06-25T07:00',
        total_sleep_seconds: 28800,
        deep_sleep_seconds: 7200,
        light_sleep_seconds: 16200,
        rem_sleep_seconds: 4500,
        awake_sleep_seconds: 900,
        sleep_score_overall: 82,
        resting_heart_rate: 52,
        avg_heart_rate: 58,
        min_heart_rate: 48,
        max_heart_rate: 72,
        avg_skin_temp_deviation: 0.3,
        avg_spo2: 96,
        lowest_spo2: 92,
        highest_spo2: 99,
        awake_count: 3,
        avg_sleep_stress: 25,
        sleep_stages: [
          {
            stage_type: 0,
            start_time_gmt: '2026-06-24T23:00',
            end_time_gmt: '2026-06-25T00:30',
            duration_seconds: 5400,
          },
        ],
      }),
    })
  })

  it('deleteSleepEntry DELETEs the entry path (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteSleepEntry(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/health/sleep/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
      responseType: 'void',
    })
  })

  it('updateSleepTarget PATCHes only sleep', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
      sleep: 28800,
    } satisfies Schemas['HealthTargetsRead'])

    await updateSleepTarget(3, 28800)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ sleep: 28800 }),
    })
  })

  it('updateSleepTarget sends null to clear the target', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      id: 3,
      user_id: 9,
      version: 1,
    } satisfies Schemas['HealthTargetsRead'])

    await updateSleepTarget(3, null)

    expect(apiFetch).toHaveBeenCalledWith('/health/targets', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({ sleep: null }),
    })
  })
})
