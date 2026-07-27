import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityDto, ActivityLapDto, ActivityStreamDto } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import {
  deleteActivity,
  editActivity,
  fetchActivity,
  fetchActivityLaps,
  fetchActivityStats,
  fetchActivityStreams,
  fetchUserActivitiesPage,
  fetchUserActivityTypeCodes,
  fetchUserActivityTypeMap,
  fetchUserWeekActivities,
  mapActivity,
  mapActivityLap,
  mapActivityStream,
  searchActivitiesByName,
  setActivityGear,
  updateUserActivitiesVisibility,
} from '@/features/activities/services/activities'

vi.mock('@/services/http', () => {
  class HttpError extends Error {
    constructor(
      readonly status: number,
      statusText: string,
      readonly detail: unknown = null,
    ) {
      super(`HTTP ${status} ${statusText}`)
      this.name = 'HttpError'
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

const activityDto: ActivityDto = {
  id: 5,
  user_id: 7,
  name: 'Morning run',
  description: 'Felt great',
  activity_type: 1,
  distance: 10000,
  is_hidden: false,
  visibility: 1,
  total_elapsed_time: 3600,
  total_timer_time: 3500,
  average_hr: 150,
  hide_hr: true,
  strava_activity_id: 999,
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapActivity', () => {
  it('maps wire fields and collapses nullable defaults', () => {
    const activity = mapActivity(activityDto)
    expect(activity).toMatchObject({
      id: 5,
      userId: 7,
      name: 'Morning run',
      description: 'Felt great',
      activityType: 1,
      visibility: 1,
      distance: 10000,
      averageHr: 150,
      stravaActivityId: 999,
    })
    expect(activity.privacy.hideHr).toBe(true)
    expect(activity.privacy.hideMap).toBe(false)
  })

  it('defaults a missing id and visibility', () => {
    const activity = mapActivity({ ...activityDto, id: null, visibility: null })
    expect(activity.id).toBe(0)
    expect(activity.visibility).toBe(0)
  })
})

describe('mapActivityStream', () => {
  it('maps stream type and waypoints with no HR zones', () => {
    const dto: ActivityStreamDto = {
      id: 3,
      activity_id: 5,
      stream_type: 1,
      stream_waypoints: [{ hr: 120 }],
    }
    expect(mapActivityStream(dto)).toEqual({
      id: 3,
      streamType: 1,
      waypoints: [{ hr: 120 }],
      hrZones: null,
    })
  })

  it('decodes the HR zone_percentages block into ordered buckets', () => {
    const dto: ActivityStreamDto = {
      id: 3,
      activity_id: 5,
      stream_type: 1,
      stream_waypoints: [{ hr: 120 }],
      zone_percentages: {
        hr: {
          zone_1: { percent: 25, hr: '< 100', time_seconds: 900 },
          zone_2: { percent: 30, hr: '100 - 129', time_seconds: 1200 },
          zone_3: { percent: 25, hr: '130 - 149', time_seconds: 900 },
          zone_4: { percent: 15, hr: '150 - 169', time_seconds: 540 },
          zone_5: { percent: 5, hr: '>= 170', time_seconds: 180 },
        },
      },
    }
    const stream = mapActivityStream(dto)
    expect(stream.hrZones).toHaveLength(5)
    expect(stream.hrZones?.[0]).toEqual({
      zone: 1,
      percent: 25,
      hrRange: '< 100',
      timeSeconds: 900,
    })
    expect(stream.hrZones?.[4]).toEqual({
      zone: 5,
      percent: 5,
      hrRange: '>= 170',
      timeSeconds: 180,
    })
  })

  it('returns null HR zones for a malformed payload', () => {
    const dto: ActivityStreamDto = {
      id: 3,
      activity_id: 5,
      stream_type: 1,
      stream_waypoints: [],
      zone_percentages: { other: {} },
    }
    expect(mapActivityStream(dto).hrZones).toBeNull()
  })
})

describe('mapActivityLap', () => {
  it('maps the consumed lap fields', () => {
    const dto: ActivityLapDto = {
      id: 2,
      activity_id: 5,
      start_time: '2024-05-01T07:00:00',
      total_distance: 1000,
      total_elapsed_time: 300,
      enhanced_avg_pace: 0.3,
      avg_heart_rate: 150,
    }
    expect(mapActivityLap(dto)).toMatchObject({
      id: 2,
      totalDistance: 1000,
      totalElapsedTime: 300,
      enhancedAvgPace: 0.3,
      avgHeartRate: 150,
    })
  })
})

describe('fetchActivity', () => {
  it('uses the authenticated endpoint when logged in', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(activityDto)
    const activity = await fetchActivity(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith('/activities/5', expect.objectContaining({ auth: true }))
    expect(activity?.id).toBe(5)
  })

  it('uses the public endpoint when unauthenticated', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(activityDto)
    await fetchActivity(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5',
      expect.objectContaining({ auth: false }),
    )
  })

  it('returns null on a 404/422 response', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(404, 'Not Found'))
    expect(await fetchActivity(5, { authenticated: true })).toBeNull()
  })

  it('rethrows non-not-found errors', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    await expect(fetchActivity(5, { authenticated: true })).rejects.toBeInstanceOf(HttpError)
  })
})

describe('searchActivitiesByName', () => {
  it('encodes the name search term and maps the results', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [activityDto],
      total: 1,
      page: 1,
      num_records: 25,
      next: null,
    })
    const result = await searchActivitiesByName('morning run')
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities?name=morning+run',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toHaveLength(1)
    expect(result[0]?.id).toBe(5)
  })

  it('treats an empty page as no matches', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 25,
      next: null,
    })
    await expect(searchActivitiesByName('x')).resolves.toEqual([])
  })
})

describe('fetchUserWeekActivities', () => {
  it('requests the user week endpoint and maps the results', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [activityDto],
      total: 1,
      page: 1,
      num_records: 200,
      next: null,
    })
    const result = await fetchUserWeekActivities(7, 3)
    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/activities\/users\/7\?start_date=\d{4}-\d{2}-\d{2}&end_date=\d{4}-\d{2}-\d{2}&num_records=200$/,
      ),
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toHaveLength(1)
    expect(result[0]?.id).toBe(5)
  })

  it('treats an empty page as no activities', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 200,
      next: null,
    })
    await expect(fetchUserWeekActivities(7, 0)).resolves.toEqual([])
  })
})

describe('fetchActivityStreams', () => {
  it('requests the authenticated and public stream endpoints', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    await fetchActivityStreams(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/5/streams',
      expect.objectContaining({ auth: true }),
    )
    await fetchActivityStreams(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5/streams',
      expect.objectContaining({ auth: false }),
    )
  })

  it('maps a null response to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchActivityStreams(5, { authenticated: true })).toEqual([])
  })
})

describe('fetchActivityLaps', () => {
  it('requests the authenticated and public lap endpoints', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    await fetchActivityLaps(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/5/laps',
      expect.objectContaining({ auth: true }),
    )
    await fetchActivityLaps(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5/laps',
      expect.objectContaining({ auth: false }),
    )
  })
})

describe('setActivityGear', () => {
  it('sends the required edit fields plus the gear id and maps the result', async () => {
    const activity = mapActivity(activityDto)
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...activityDto, gear_id: 42 })

    const updated = await setActivityGear(activity, 42)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      body: JSON.stringify({ gear_id: 42 }),
    })
    expect(updated.gearId).toBe(42)
  })

  it('clears the association when the gear id is null', async () => {
    const activity = mapActivity(activityDto)
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...activityDto, gear_id: null })

    await setActivityGear(activity, null)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      body: JSON.stringify({ gear_id: null }),
    })
  })
})

describe('deleteActivity', () => {
  it('sends a DELETE to the activity delete endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ detail: 'deleted' })

    await deleteActivity(5)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', { method: 'DELETE' })
  })
})

describe('updateUserActivitiesVisibility', () => {
  it('updates every existing activity to the requested visibility', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await updateUserActivitiesVisibility('followers')

    expect(apiFetch).toHaveBeenCalledWith('/activities/visibility/followers', {
      method: 'PUT',
      responseType: 'void',
    })
  })
})

describe('editActivity', () => {
  it('sends the full edit payload, clears empty text fields, and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...activityDto,
      name: 'Evening run',
      visibility: 2,
    })

    const updated = await editActivity(5, {
      name: 'Evening run',
      activityType: 1,
      description: '',
      privateNotes: 'note',
      visibility: 2,
      isHidden: true,
      hideStartTime: false,
      hideLocation: false,
      hideMap: true,
      hideHr: false,
      hidePower: false,
      hideCadence: false,
      hideElevation: false,
      hideSpeed: false,
      hidePace: false,
      hideLaps: false,
      hideWorkoutSetsSteps: false,
      hideGear: false,
    })

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      body: JSON.stringify({
        name: 'Evening run',
        activity_type: 1,
        description: null,
        private_notes: 'note',
        visibility: 2,
        is_hidden: true,
        hide_start_time: false,
        hide_location: false,
        hide_map: true,
        hide_hr: false,
        hide_power: false,
        hide_cadence: false,
        hide_elevation: false,
        hide_speed: false,
        hide_pace: false,
        hide_laps: false,
        hide_workout_sets_steps: false,
        hide_gear: false,
      }),
    })
    expect(updated.name).toBe('Evening run')
  })
})

describe('fetchUserActivitiesPage', () => {
  it('builds the list URL from the filters and reads the total from the envelope', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [activityDto],
      total: 42,
      page: 2,
      num_records: 25,
      next: 3,
    })

    const result = await fetchUserActivitiesPage({
      userId: 7,
      page: 2,
      numRecords: 25,
      filters: { type: 1, startDate: '2024-01-01', endDate: '2024-12-31', nameSearch: ' run ' },
      sortBy: 'distance',
      sortOrder: 'asc',
    })

    // One request, not two: the total now travels with the page, so the filters
    // cannot drift between a list call and a separate count call.
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities?type=1&start_date=2024-01-01&end_date=2024-12-31&name=run&sort_by=distance&sort_order=asc&page_number=2&num_records=25',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result.total).toBe(42)
    expect(result.records).toHaveLength(1)
    expect(result.records[0]?.id).toBe(5)
  })

  it('omits empty filters from the list URL', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 10,
      next: null,
    })

    const result = await fetchUserActivitiesPage({
      userId: 3,
      page: 1,
      numRecords: 10,
      filters: { type: null, startDate: null, endDate: null, nameSearch: null },
      sortBy: 'start_time',
      sortOrder: 'desc',
    })

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities?sort_by=start_time&sort_order=desc&page_number=1&num_records=10',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual({ records: [], total: 0 })
  })

  it('treats the "all types" sentinel (0) as no type filter', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 25,
      next: null,
    })

    await fetchUserActivitiesPage({
      userId: 1,
      page: 1,
      numRecords: 25,
      filters: { type: 0, startDate: null, endDate: null, nameSearch: null },
      sortBy: 'name',
      sortOrder: 'asc',
    })

    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/activities?sort_by=name&sort_order=asc&page_number=1&num_records=25',
      expect.objectContaining({ signal: undefined }),
    )
  })
})

describe('fetchUserActivityTypeCodes', () => {
  it('parses the type map into ascending numeric codes', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ '9': 'Ride', '1': 'Run', '11': 'Walk' })

    await expect(fetchUserActivityTypeCodes()).resolves.toEqual([1, 9, 11])
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/types',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('returns an empty list when the body is null', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    await expect(fetchUserActivityTypeCodes()).resolves.toEqual([])
  })
})

describe('fetchUserActivityTypeMap', () => {
  it('parses the response into a code→name map with numeric keys', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ '9': 'Ride', '1': 'Run', '11': 'Walk' })

    const map = await fetchUserActivityTypeMap()

    expect(map).toBeInstanceOf(Map)
    // Integer-like object keys iterate in ascending numeric order, so the map
    // entries come out ordered by code regardless of the response's literal order.
    expect([...map.entries()]).toEqual([
      [1, 'Run'],
      [9, 'Ride'],
      [11, 'Walk'],
    ])
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/types',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('returns an empty map when the body is null', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    await expect(fetchUserActivityTypeMap()).resolves.toEqual(new Map())
  })
})

describe('local-calendar period anchoring', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends the viewer local date so the backend resolves the right week/month', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({})
    await fetchActivityStats(7, 'week')

    const url = vi.mocked(apiFetch).mock.calls[0]?.[0] as string
    const sentDate = new URLSearchParams(url.split('?')[1]).get('date')
    const now = new Date()
    const localToday = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0'),
    ].join('-')

    expect(sentDate).toBe(localToday)
  })

  it('derives the week range from the local calendar, not UTC', async () => {
    // 2026-01-05T13:30:00Z is Monday the 5th in UTC but already Tuesday the 6th
    // for a viewer at UTC+13 — either way the range must start on a Monday and
    // span exactly seven days in the viewer's own calendar.
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2026-01-05T13:30:00Z'))
      vi.mocked(apiFetch).mockResolvedValueOnce([])
      await fetchUserWeekActivities(7, 0)

      const url = vi.mocked(apiFetch).mock.calls[0]?.[0] as string
      const params = new URLSearchParams(url.split('?')[1])
      const start = params.get('start_date') as string
      const end = params.get('end_date') as string

      const [sy, sm, sd] = start.split('-').map(Number)
      const startLocal = new Date(sy as number, (sm as number) - 1, sd as number)
      expect(startLocal.getDay()).toBe(1) // Monday in the viewer's calendar

      const [ey, em, ed] = end.split('-').map(Number)
      const endLocal = new Date(ey as number, (em as number) - 1, ed as number)
      expect((endLocal.getTime() - startLocal.getTime()) / 86_400_000).toBe(6)

      // The anchor day itself must fall inside the returned week.
      const now = new Date()
      const todayLocal = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      expect(todayLocal.getTime()).toBeGreaterThanOrEqual(startLocal.getTime())
      expect(todayLocal.getTime()).toBeLessThanOrEqual(endLocal.getTime())
    } finally {
      vi.useRealTimers()
    }
  })
})
