import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Bike, Dumbbell, Footprints, Sailboat } from '@lucide/vue'

import type { GearDetailDto, GearDto, GearInput } from '@/features/gears/types'

import { apiFetch, HttpError } from '@/services/http'
import {
  createGear,
  deleteGear,
  fetchGearById,
  fetchGears,
  fetchGearsByType,
  mapGear,
  mapGearDetail,
  searchGearsByNickname,
  updateGear,
} from '@/features/gears/services/gears'
import {
  currencySymbol,
  formatDuration,
  kmToDisplayDistance,
  metersToDisplayDistance,
} from '@/features/gears/utils/format'
import { GEAR_TYPE, presentGearType } from '@/features/gears/utils/gearType'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const gearDto: GearDto = {
  id: 5,
  user_id: 1,
  gear_type: 1,
  nickname: 'Road Bike',
  active: true,
  brand: 'Canyon',
  model: 'Endurace',
  created_at: '2024-01-15',
  initial_kms: 100,
  purchase_value: 2500,
  strava_gear_id: 'b123',
  garminconnect_gear_id: 'g456',
  version: 3,
}

const mappedGear = {
  id: 5,
  userId: 1,
  gearType: 1,
  nickname: 'Road Bike',
  brand: 'Canyon',
  model: 'Endurace',
  active: true,
  createdAt: '2024-01-15',
  initialKms: 100,
  purchaseValue: 2500,
  stravaGearId: 'b123',
  garminConnectGearId: 'g456',
  version: 3,
}

const gearInput: GearInput = {
  nickname: 'New Bike',
  gearType: 1,
  brand: 'Trek',
  model: 'Domane',
  active: true,
  createdAt: '2024-02-01',
  initialKms: 0,
  purchaseValue: 1000,
}

const expectedWirePayload = {
  nickname: 'New Bike',
  gear_type: 1,
  brand: 'Trek',
  model: 'Domane',
  active: true,
  created_at: '2024-02-01',
  initial_kms: 0,
  purchase_value: 1000,
}

describe('mapGear', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapGear(gearDto)).toEqual(mappedGear)
  })

  it('defaults active to true and absent optionals to null', () => {
    expect(mapGear({ id: 9, user_id: 2, gear_type: 2, nickname: 'Shoes', version: 1 })).toEqual({
      id: 9,
      userId: 2,
      gearType: 2,
      nickname: 'Shoes',
      brand: null,
      model: null,
      active: true,
      createdAt: null,
      initialKms: null,
      purchaseValue: null,
      stravaGearId: null,
      garminConnectGearId: null,
      version: 1,
    })
  })
})

describe('mapGearDetail', () => {
  it('adds the computed totals on top of the base gear fields', () => {
    const detailDto: GearDetailDto = {
      ...gearDto,
      total_distance: 5000,
      total_time: 3600,
      total_components_cost: 50,
    }

    expect(mapGearDetail(detailDto)).toEqual({
      ...mappedGear,
      totalDistance: 5000,
      totalTime: 3600,
      totalComponentsCost: 50,
    })
  })
})

describe('gear service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the paginated list path and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [gearDto], total: 1 })

    const result = await fetchGears({ page: 1, numRecords: 25, showInactive: false })

    expect(apiFetch).toHaveBeenCalledWith(
      '/gears?page_number=1&num_records=25&show_inactive=false',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual({ records: [mappedGear], total: 1 })
  })

  it('treats an absent items array as an empty page', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 0 })
    await expect(fetchGears({ page: 1, numRecords: 25, showInactive: true })).resolves.toEqual({
      records: [],
      total: 0,
    })
  })

  it('encodes the nickname search term and maps the results', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [gearDto], total: 1 })

    const result = await searchGearsByNickname('road bike')

    expect(apiFetch).toHaveBeenCalledWith(
      '/gears?num_records=200&nickname_contains=road+bike',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual([mappedGear])
  })

  it('treats a search page without items as no matches', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 0 })
    await expect(searchGearsByNickname('x')).resolves.toEqual([])
  })

  it('filters the list by gear type', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [gearDto], total: 1 })

    await expect(fetchGearsByType(2)).resolves.toEqual([mappedGear])

    expect(apiFetch).toHaveBeenCalledWith(
      '/gears?num_records=200&gear_type=2',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('returns null when the gear does not exist', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(404, 'Not Found'))
    await expect(fetchGearById(5)).resolves.toBeNull()
  })

  it('maps a single gear detail and returns null when absent', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)
    await expect(fetchGearById(5)).resolves.toBeNull()
    expect(apiFetch).toHaveBeenCalledWith('/gears/5', expect.objectContaining({}))
  })

  it('creates a gear via a POST with the snake-cased payload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(gearDto)

    await createGear(gearInput)

    expect(apiFetch).toHaveBeenCalledWith('/gears', {
      method: 'POST',
      body: JSON.stringify(expectedWirePayload),
    })
  })

  it('updates a gear via a PATCH guarded by If-Match', async () => {
    vi.mocked(apiFetch).mockResolvedValue(gearDto)

    await updateGear(5, gearInput, 3)

    const [path, init] = vi.mocked(apiFetch).mock.calls[0]!
    expect(path).toBe('/gears/5')
    expect(init).toMatchObject({ method: 'PATCH', headers: { 'If-Match': '"3"' } })
    expect(JSON.parse(init!.body as string)).toEqual(expectedWirePayload)
  })

  it('leaves the fields the backend cannot clear out of a partial update', async () => {
    vi.mocked(apiFetch).mockResolvedValue(gearDto)

    await updateGear(5, { ...gearInput, createdAt: null, initialKms: null }, 3)

    const body = JSON.parse(vi.mocked(apiFetch).mock.calls[0]![1]!.body as string)
    expect(body).not.toHaveProperty('created_at')
    expect(body).not.toHaveProperty('initial_kms')
  })

  it('deletes a gear via a void DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteGear(5, 4)

    expect(apiFetch).toHaveBeenCalledWith('/gears/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"4"' },
      responseType: 'void',
    })
  })
})

describe('presentGearType', () => {
  it('maps known types to their icon and label key', () => {
    expect(presentGearType(GEAR_TYPE.BICYCLE)).toEqual({
      icon: Bike,
      labelKey: 'gears.types.bicycle',
    })
    expect(presentGearType(GEAR_TYPE.SHOES)).toEqual({
      icon: Footprints,
      labelKey: 'gears.types.shoes',
    })
    expect(presentGearType(GEAR_TYPE.WATER_SPORTS_BOARD)).toEqual({
      icon: Sailboat,
      labelKey: 'gears.types.waterSportsBoard',
    })
  })

  it('falls back to a neutral presentation for an unknown type', () => {
    expect(presentGearType(99)).toEqual({ icon: Dumbbell, labelKey: 'gears.types.unknown' })
  })
})

describe('gear format helpers', () => {
  it('returns the symbol for each currency', () => {
    expect(currencySymbol('euro')).toBe('€')
    expect(currencySymbol('dollar')).toBe('$')
    expect(currencySymbol('pound')).toBe('£')
  })

  it('keeps kilometres for metric and converts to miles for imperial', () => {
    expect(kmToDisplayDistance(10, 'metric')).toBe(10)
    expect(kmToDisplayDistance(1.609344, 'imperial')).toBe(1)
  })

  it('converts metres to the viewer distance unit', () => {
    expect(metersToDisplayDistance(1000, 'metric')).toBe(1)
    expect(metersToDisplayDistance(1609.344, 'imperial')).toBe(1)
  })

  it('formats durations as compact hours and minutes', () => {
    expect(formatDuration(3661)).toBe('1h 1m')
    expect(formatDuration(2700)).toBe('45m')
    expect(formatDuration(0)).toBe('0m')
  })
})
