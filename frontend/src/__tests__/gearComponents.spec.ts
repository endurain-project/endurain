import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  GearComponent,
  GearComponentDto,
  GearComponentInput,
  GearComponentTypeLists,
} from '@/features/gears/types'

import { apiFetch } from '@/services/http'
import {
  createGearComponent,
  deleteGearComponent,
  fetchGearComponents,
  fetchGearComponentTypes,
  mapGearComponent,
  updateGearComponent,
} from '@/features/gears/services/gearComponents'
import {
  componentTypeListKey,
  componentWearPercent,
  gearTypeSupportsComponents,
  humanizeComponentType,
  isTimeBasedGear,
} from '@/features/gears/utils/gearComponentType'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const componentDto: GearComponentDto = {
  id: 7,
  user_id: 1,
  gear_id: 5,
  type: 'chain',
  brand: 'Shimano',
  model: 'XT',
  purchase_date: '2024-01-10',
  retired_date: null,
  active: true,
  expected_kms: 5_000_000,
  purchase_value: 45,
  current_distance: 1_200_000,
  current_time: 360_000,
  version: 2,
}

const mappedComponent: GearComponent = {
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
  purchaseValue: 45,
  currentDistance: 1_200_000,
  currentTime: 360_000,
  version: 2,
}

const componentInput: GearComponentInput = {
  gearId: 5,
  type: 'chain',
  brand: 'Shimano',
  model: 'XT',
  purchaseDate: '2024-01-10',
  retiredDate: null,
  active: true,
  expectedBaseUnits: 5_000_000,
  purchaseValue: 45,
}

const expectedComponentWire = {
  gear_id: 5,
  type: 'chain',
  brand: 'Shimano',
  model: 'XT',
  purchase_date: '2024-01-10',
  retired_date: null,
  active: true,
  expected_kms: 5_000_000,
  purchase_value: 45,
}

describe('mapGearComponent', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapGearComponent(componentDto)).toEqual(mappedComponent)
  })

  it('defaults active to true, absent optionals to null, and usage to zero', () => {
    expect(
      mapGearComponent({
        id: 9,
        user_id: 2,
        gear_id: 3,
        type: 'cleats',
        brand: 'Look',
        model: 'Keo',
        current_distance: 0,
        current_time: 0,
        version: 1,
      }),
    ).toEqual({
      id: 9,
      userId: 2,
      gearId: 3,
      type: 'cleats',
      brand: 'Look',
      model: 'Keo',
      purchaseDate: null,
      retiredDate: null,
      active: true,
      expectedBaseUnits: null,
      purchaseValue: null,
      currentDistance: 0,
      currentTime: 0,
      version: 1,
    })
  })
})

describe('gear-component service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the components-by-gear path and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [componentDto],
      total: 1,
      page: 1,
      num_records: 200,
      next: null,
    })

    const result = await fetchGearComponents(5)

    expect(apiFetch).toHaveBeenCalledWith(
      '/gears/5/components',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual([mappedComponent])
  })

  it('returns an empty list for an empty page', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, page: 1, num_records: 200 })
    await expect(fetchGearComponents(5)).resolves.toEqual([])
  })

  it('requests the component-type catalogues', async () => {
    const types: GearComponentTypeLists = {
      bike: ['chain'],
      shoes: ['cleats'],
      racquet: ['strings'],
      windsurf: ['sail'],
    }
    vi.mocked(apiFetch).mockResolvedValue(types)

    const result = await fetchGearComponentTypes()

    expect(apiFetch).toHaveBeenCalledWith(
      '/gear-components/types',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual(types)
  })

  it('creates a component via a POST with the snake-cased payload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(componentDto)

    await createGearComponent(componentInput)

    expect(apiFetch).toHaveBeenCalledWith('/gear-components', {
      method: 'POST',
      body: JSON.stringify(expectedComponentWire),
    })
  })

  it('updates a component via a PATCH guarded by If-Match, without the gear id', async () => {
    vi.mocked(apiFetch).mockResolvedValue(componentDto)

    await updateGearComponent(7, componentInput, 2)

    const [path, init] = vi.mocked(apiFetch).mock.calls[0]!
    expect(path).toBe('/gear-components/7')
    expect(init).toMatchObject({ method: 'PATCH', headers: { 'If-Match': '"2"' } })
    const { gear_id: _gearId, ...expected } = expectedComponentWire
    expect(JSON.parse(init!.body as string)).toEqual(expected)
  })

  it('deletes a component via a void DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteGearComponent(7, 2)

    expect(apiFetch).toHaveBeenCalledWith('/gear-components/7', {
      method: 'DELETE',
      headers: { 'If-Match': '"2"' },
      responseType: 'void',
    })
  })
})

describe('componentTypeListKey', () => {
  it('maps component-bearing gear families to their catalogue key', () => {
    expect(componentTypeListKey(GEAR_TYPE.BICYCLE)).toBe('bike')
    expect(componentTypeListKey(GEAR_TYPE.SHOES)).toBe('shoes')
    expect(componentTypeListKey(GEAR_TYPE.RACQUET)).toBe('racquet')
    expect(componentTypeListKey(GEAR_TYPE.WINDSURF)).toBe('windsurf')
  })

  it('returns null for families without components', () => {
    expect(componentTypeListKey(GEAR_TYPE.WETSUIT)).toBeNull()
    expect(componentTypeListKey(GEAR_TYPE.WATER_SPORTS_BOARD)).toBeNull()
  })
})

describe('gearTypeSupportsComponents', () => {
  it('is true for component-bearing families and false otherwise', () => {
    expect(gearTypeSupportsComponents(GEAR_TYPE.BICYCLE)).toBe(true)
    expect(gearTypeSupportsComponents(GEAR_TYPE.WETSUIT)).toBe(false)
  })
})

describe('isTimeBasedGear', () => {
  it('tracks the racquet family by time and every other family by distance', () => {
    expect(isTimeBasedGear(GEAR_TYPE.RACQUET)).toBe(true)
    expect(isTimeBasedGear(GEAR_TYPE.BICYCLE)).toBe(false)
  })
})

describe('humanizeComponentType', () => {
  it('sentence-cases the id and fixes the catalogue break/brake spelling', () => {
    expect(humanizeComponentType('front_break_pads')).toBe('Front brake pads')
    expect(humanizeComponentType('bottom_bracket')).toBe('Bottom bracket')
    expect(humanizeComponentType('chain')).toBe('Chain')
  })
})

describe('componentWearPercent', () => {
  it('returns the rounded ratio of usage to the threshold', () => {
    expect(componentWearPercent(1_200_000, 5_000_000)).toBe(24)
    expect(componentWearPercent(6_000_000, 5_000_000)).toBe(120)
  })

  it('returns null when there is no positive threshold', () => {
    expect(componentWearPercent(1000, null)).toBeNull()
    expect(componentWearPercent(1000, 0)).toBeNull()
  })
})
