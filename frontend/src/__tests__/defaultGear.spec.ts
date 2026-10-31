import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DefaultGearDto } from '@/features/profile/types'

import { apiFetch } from '@/services/http'
import { fetchGearsByType } from '@/features/gears/services/gears'
import {
  fetchDefaultGear,
  mapDefaultGear,
  toDefaultGearWire,
  updateDefaultGear,
} from '@/features/profile/services/defaultGear'
import { DEFAULT_GEAR_GROUPS, DEFAULT_GEAR_TYPES } from '@/features/profile/utils/defaultGearFields'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full default-gear wire payload, overridable per case. */
function makeDefaultGearDto(overrides: Partial<DefaultGearDto> = {}): DefaultGearDto {
  return {
    id: 1,
    user_id: 5,
    version: 3,
    run_gear_id: 10,
    trail_run_gear_id: null,
    virtual_run_gear_id: null,
    walk_gear_id: null,
    hike_gear_id: null,
    ride_gear_id: 20,
    mtb_ride_gear_id: null,
    gravel_ride_gear_id: null,
    virtual_ride_gear_id: null,
    ows_gear_id: null,
    tennis_gear_id: null,
    alpine_ski_gear_id: null,
    nordic_ski_gear_id: null,
    snowboard_gear_id: null,
    windsurf_gear_id: null,
    ...overrides,
  }
}

describe('mapDefaultGear', () => {
  it('maps the wire shape to the clean camel-cased model', () => {
    const gear = mapDefaultGear(makeDefaultGearDto())
    expect(gear).toMatchObject({
      id: 1,
      userId: 5,
      runGearId: 10,
      rideGearId: 20,
      trailRunGearId: null,
      windsurfGearId: null,
    })
  })
})

describe('toDefaultGearWire', () => {
  it('round-trips every assignment and leaves out the record, user id and version', () => {
    const { id: _id, user_id: _userId, version: _version, ...assignments } = makeDefaultGearDto()

    expect(toDefaultGearWire(mapDefaultGear(makeDefaultGearDto()))).toEqual(assignments)
  })
})

describe('default gear service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchDefaultGear reads the endpoint and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(makeDefaultGearDto())
    const gear = await fetchDefaultGear()
    expect(apiFetch).toHaveBeenCalledWith('/profile/default-gear', { signal: undefined })
    expect(gear?.runGearId).toBe(10)
  })

  it('fetchDefaultGear returns null when no record exists', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchDefaultGear()).toBeNull()
  })

  it('updateDefaultGear PATCHes the snake-cased body, guarded by If-Match', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(makeDefaultGearDto())
    })

    await updateDefaultGear(mapDefaultGear(makeDefaultGearDto({ hike_gear_id: 30 })))

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/default-gear',
      expect.objectContaining({ method: 'PATCH', headers: { 'If-Match': '"3"' } }),
    )
    const parsed = JSON.parse(body as string) as Record<string, unknown>
    expect(parsed).not.toHaveProperty('id')
    expect(parsed).not.toHaveProperty('user_id')
    expect(parsed).not.toHaveProperty('version')
    expect(parsed.run_gear_id).toBe(10)
    expect(parsed.hike_gear_id).toBe(30)
    expect(parsed.windsurf_gear_id).toBeNull()
  })

  it('fetchGearsByType reads the gear-type endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [{ id: 10, user_id: 5, gear_type: 2, nickname: 'Trail shoes', version: 1 }],
      total: 1,
    })
    const gears = await fetchGearsByType(2)
    expect(apiFetch).toHaveBeenCalledWith('/gears?num_records=200&gear_type=2', {
      signal: undefined,
    })
    expect(gears).toHaveLength(1)
    expect(gears[0]?.nickname).toBe('Trail shoes')
  })
})

describe('default gear field config', () => {
  it('covers all 15 activity assignments with unique keys', () => {
    const keys = DEFAULT_GEAR_GROUPS.flatMap((group) => group.fields.map((field) => field.key))
    expect(keys).toHaveLength(15)
    expect(new Set(keys).size).toBe(15)
  })

  it('prefetches exactly the seven distinct gear types it uses', () => {
    expect(Array.from(DEFAULT_GEAR_TYPES).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })
})
