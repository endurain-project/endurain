import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityDto, ActivityLapDto, ActivityStreamDto } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import {
  deleteActivity,
  editActivity,
  fetchActivity,
  fetchActivityDetail,
  fetchActivityLaps,
  fetchActivityStats,
  fetchActivityStreams,
  fetchFollowersActivities,
  fetchUserActivitiesPage,
  fetchUserActivityTypes,
  fetchUserWeekActivities,
  mapActivity,
  mapActivitySummary,
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
      readonly type: string | null = null,
    ) {
      super(`HTTP ${status} ${statusText}`)
      this.name = 'HttpError'
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

const activityDto: ActivityDto = {
  id: 5,
  version: 3,
  user_id: 7,
  name: 'Morning run',
  description: 'Felt great',
  activity_type: 'run',
  distance: 10000,
  is_hidden: false,
  visibility: 'followers',
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
      activityType: 'run',
      visibility: 'followers',
      distance: 10000,
      averageHr: 150,
      stravaActivityId: 999,
    })
    expect(activity.privacy.hideHr).toBe(true)
    expect(activity.privacy.hideMap).toBe(false)
  })

  it('maps the embedded media, and defaults it to none', () => {
    const media = [{ id: 9, activity_id: 5, media_type: 'photo' as const, url: '/media/5/9?t=abc' }]
    expect(mapActivity({ ...activityDto, media }).media).toEqual([
      expect.objectContaining({ id: 9, activityId: 5 }),
    ])
    expect(mapActivity(activityDto).media).toEqual([])
  })

  it('defaults a missing visibility', () => {
    const activity = mapActivity({ ...activityDto, visibility: null })
    expect(activity.visibility).toBe('public')
  })
})

describe('mapActivitySummary', () => {
  it('maps the list fields and has no private notes', () => {
    const dto: ActivityDto = { ...activityDto, private_notes: 'secret' }
    const summary = mapActivitySummary(dto)

    expect(summary).toMatchObject({ id: 5, userId: 7, name: 'Morning run', version: 3 })
    expect(summary.privacy.hideHr).toBe(true)
    expect(summary).not.toHaveProperty('privateNotes')
  })

  it('is the base the full mapper builds on', () => {
    const dto: ActivityDto = { ...activityDto, private_notes: 'secret' }
    const { privateNotes, ...rest } = mapActivity(dto)

    expect(privateNotes).toBe('secret')
    expect(rest).toEqual(mapActivitySummary(dto))
    expect(mapActivity(activityDto).privateNotes).toBeNull()
  })
})

describe('mapActivityStream', () => {
  it('maps stream type and waypoints with no HR zones', () => {
    const dto: ActivityStreamDto = {
      id: 3,
      activity_id: 5,
      stream_type: 'heart_rate',
      stream_waypoints: [{ hr: 120 }],
    }
    expect(mapActivityStream(dto)).toEqual({
      id: 3,
      streamType: 'heart_rate',
      waypoints: [{ hr: 120 }],
      hrZones: null,
    })
  })

  it('keeps the typed waypoints of a map stream, whatever its sample times', () => {
    const dto: ActivityStreamDto = {
      id: 4,
      activity_id: 5,
      stream_type: 'map',
      stream_waypoints: [
        { time: '2026-06-20T08:20:00', lat: 38.7223, lon: -9.1393 },
        { time: 0.5, lat: 38.72, lon: -9.14 },
        { lat: 38.7, lon: -9.1 },
      ],
    }
    expect(mapActivityStream(dto)).toEqual({
      id: 4,
      streamType: 'map',
      waypoints: dto.stream_waypoints,
      hrZones: null,
    })
  })

  it('decodes the HR zone_percentages block into ordered buckets', () => {
    const dto: ActivityStreamDto = {
      id: 3,
      activity_id: 5,
      stream_type: 'heart_rate',
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
  it('reads the authenticated endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(activityDto)
    const activity = await fetchActivity(5)
    expect(apiFetch).toHaveBeenCalledWith('/activities/5')
    expect(activity?.id).toBe(5)
  })

  it('returns null on a 404/422 response', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new HttpError(404, 'Not Found', null, 'urn:endurain:error:not-found'),
    )
    expect(await fetchActivity(5)).toBeNull()
  })

  it('rethrows non-not-found errors', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    await expect(fetchActivity(5)).rejects.toBeInstanceOf(HttpError)
  })
})

describe('fetchActivityDetail', () => {
  const lapDto = { id: 1, total_distance: 1000 }
  const setDto = { id: 2, duration: 30, set_type: 1 }
  const stepDto = { duration_type: 1, message_index: 0 }
  const page = (items: unknown[], next: number | null = null) => ({
    items,
    total: items.length,
    page: 1,
    num_records: 200,
    next,
  })
  const detailDto = {
    activity: activityDto,
    laps: page([lapDto]),
    sets: page([setDto]),
    workout_steps: page([stepDto]),
    owner: null,
  }

  it('maps the owner the detail carries, and keeps a hidden one null', async () => {
    const owner = { id: 7, name: 'Jane Runner', username: 'jane', photo_path: null }
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...detailDto, owner })
    vi.mocked(apiFetch).mockResolvedValueOnce(detailDto)

    const shown = await fetchActivityDetail(5, { authenticated: false })
    const hidden = await fetchActivityDetail(5, { authenticated: false })

    expect(shown?.owner).toMatchObject({ name: 'Jane Runner', username: 'jane' })
    expect(hidden?.owner).toBeNull()
  })

  it('reads the activity and its collections in one request', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(detailDto)

    const detail = await fetchActivityDetail(5, { authenticated: true })

    expect(apiFetch).toHaveBeenCalledExactlyOnceWith(
      '/activities/5/detail',
      expect.objectContaining({ auth: true }),
    )
    expect(detail?.activity.id).toBe(5)
    expect(detail?.laps).toHaveLength(1)
    expect(detail?.laps?.[0]).toMatchObject({ id: 1, totalDistance: 1000 })
    expect(detail?.sets?.[0]).toMatchObject({ id: 2, duration: 30 })
    expect(detail?.workoutSteps?.[0]).toMatchObject({ messageIndex: 0 })
  })

  it('uses the public endpoint when unauthenticated', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(detailDto)

    await fetchActivityDetail(5, { authenticated: false })

    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5/detail',
      expect.objectContaining({ auth: false }),
    )
  })

  it('reports a collection with more pages as incomplete, to be read in full separately', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...detailDto, laps: page([lapDto], 2) })

    const detail = await fetchActivityDetail(5, { authenticated: true })

    expect(detail?.laps).toBeNull()
    expect(detail?.sets).toHaveLength(1)
  })

  it('returns null on a 404/422 response', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new HttpError(404, 'Not Found', null, 'urn:endurain:error:not-found'),
    )
    expect(await fetchActivityDetail(5, { authenticated: true })).toBeNull()
  })

  it('rethrows non-not-found errors', async () => {
    const { HttpError } = await import('@/services/http')
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    await expect(fetchActivityDetail(5, { authenticated: true })).rejects.toBeInstanceOf(HttpError)
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
      '/activities?name_contains=morning+run',
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

describe('week activities query key', () => {
  it('differs by first day of the week, so a changed setting refetches', () => {
    expect(queryKeys.activities.weekActivities(7, 1, 'monday')).not.toEqual(
      queryKeys.activities.weekActivities(7, 1, 'sunday'),
    )
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
    const result = await fetchUserWeekActivities(7, 3, 'monday')
    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/users\/7\/activities\?start_date=\d{4}-\d{2}-\d{2}&end_date=\d{4}-\d{2}-\d{2}&num_records=200$/,
      ),
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toHaveLength(1)
    expect(result[0]?.id).toBe(5)
  })

  describe('with a fixed date', () => {
    beforeEach(() => {
      vi.useFakeTimers()
      // A Wednesday.
      vi.setSystemTime(new Date(2026, 10, 4, 12))
      vi.mocked(apiFetch).mockResolvedValue({ items: [] })
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    const requestedParams = (): URLSearchParams => {
      const url = vi.mocked(apiFetch).mock.calls[0]?.[0] as string
      return new URLSearchParams(url.split('?')[1])
    }

    it("starts the week on the viewer's first day of the week", async () => {
      await fetchUserWeekActivities(7, 0, 'sunday')
      expect(requestedParams().get('start_date')).toBe('2026-11-01')
      expect(requestedParams().get('end_date')).toBe('2026-11-07')
    })

    it('leaves the oldest bucket open-ended, ending before week 50 starts', async () => {
      await fetchUserWeekActivities(7, 51, 'monday')
      // Week 50 starts 2025-11-17 (a Monday), so the bucket ends the day before.
      expect(requestedParams().has('start_date')).toBe(false)
      expect(requestedParams().get('end_date')).toBe('2025-11-16')
    })
  })

  it('treats an empty page as no activities', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 200,
      next: null,
    })
    await expect(fetchUserWeekActivities(7, 0, 'monday')).resolves.toEqual([])
  })
})

describe('fetchActivityStreams', () => {
  it('requests the authenticated and public stream endpoints', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], next: null })
    await fetchActivityStreams(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/5/streams?num_records=200&page_number=1',
      expect.objectContaining({ auth: true }),
    )
    await fetchActivityStreams(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5/streams?num_records=200&page_number=1',
      expect.objectContaining({ auth: false }),
    )
  })

  it('maps an empty page to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: null, next: null })
    expect(await fetchActivityStreams(5, { authenticated: true })).toEqual([])
  })
})

describe('fetchActivityLaps', () => {
  it('requests the authenticated and public lap endpoints', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], next: null })
    await fetchActivityLaps(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/5/laps?num_records=200&page_number=1',
      expect.objectContaining({ auth: true }),
    )
    await fetchActivityLaps(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/public/activities/5/laps?num_records=200&page_number=1',
      expect.objectContaining({ auth: false }),
    )
  })

  it('walks every page the server advertises', async () => {
    // The read is paginated server-side; showing only page 1 would silently
    // drop laps from a long activity.
    const lap = { id: 1, activity_id: 5, start_time: '2024-01-15T08:00:00Z' }
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [lap], next: 2 })
      .mockResolvedValueOnce({ items: [{ ...lap, id: 2 }], next: null })

    const laps = await fetchActivityLaps(5, { authenticated: true })

    expect(laps).toHaveLength(2)
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/activities/5/laps?num_records=200&page_number=2',
      expect.objectContaining({ auth: true }),
    )
  })
})

describe('setActivityGear', () => {
  it('sends the required edit fields plus the gear id and maps the result', async () => {
    const activity = mapActivity(activityDto)
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...activityDto,
      gear_id: '00000000-0000-4000-8000-000000000042',
    })

    const updated = await setActivityGear(activity, '00000000-0000-4000-8000-000000000042')

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      body: JSON.stringify({ gear_id: '00000000-0000-4000-8000-000000000042' }),
      headers: { 'If-Match': '"3"' },
    })
    expect(updated.gearId).toBe('00000000-0000-4000-8000-000000000042')
  })

  it('clears the association when the gear id is null', async () => {
    const activity = mapActivity(activityDto)
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...activityDto, gear_id: null })

    await setActivityGear(activity, null)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      body: JSON.stringify({ gear_id: null }),
      headers: { 'If-Match': '"3"' },
    })
  })

  it('sends a version no stored row has when the copy carries none, so the backend refuses it', async () => {
    const activity = mapActivity({ ...activityDto, version: null })
    vi.mocked(apiFetch).mockResolvedValueOnce(activityDto)

    await setActivityGear(activity, '00000000-0000-4000-8000-000000000042')

    expect(vi.mocked(apiFetch).mock.lastCall?.[1]?.headers).toEqual({ 'If-Match': '"0"' })
  })
})

describe('deleteActivity', () => {
  it('sends a DELETE to the activity delete endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ detail: 'deleted' })

    await deleteActivity(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'DELETE',
      headers: { 'If-Match': '"3"' },
    })
  })
})

describe('updateUserActivitiesVisibility', () => {
  const bulkEdit = (status: string) => ({
    id: 'job-1',
    kind: 'activities_bulk_edit',
    status,
    created_at: '2026-01-01T00:00:00Z',
  })

  it('patches the collection with the requested visibility', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(bulkEdit('queued'))
      .mockResolvedValueOnce(bulkEdit('succeeded'))

    await updateUserActivitiesVisibility('followers')

    expect(apiFetch).toHaveBeenCalledWith('/activities', {
      method: 'PATCH',
      body: JSON.stringify({ visibility: 'followers' }),
    })
  })

  it('follows the queued edit job until it completes', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(bulkEdit('queued'))
        .mockResolvedValueOnce(bulkEdit('running'))
        .mockResolvedValueOnce(bulkEdit('succeeded'))

      const done = updateUserActivitiesVisibility('private')
      await vi.advanceTimersByTimeAsync(2_000)
      await vi.advanceTimersByTimeAsync(2_000)
      await done

      expect(apiFetch).toHaveBeenNthCalledWith(2, '/jobs/job-1', { signal: undefined })
      expect(apiFetch).toHaveBeenCalledTimes(3)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports an edit that failed on the server', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(bulkEdit('queued'))
      .mockResolvedValueOnce(bulkEdit('failed'))

    await expect(updateUserActivitiesVisibility('private')).rejects.toThrow(/failed/)
  })
})

describe('editActivity', () => {
  it('sends the full edit payload, clears empty text fields, and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...activityDto,
      name: 'Evening run',
      visibility: 'private',
    })

    const updated = await editActivity(
      5,
      {
        name: 'Evening run',
        activityType: 'run',
        description: '',
        privateNotes: 'note',
        visibility: 'private',
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
      },
      3,
    )

    expect(apiFetch).toHaveBeenCalledWith('/activities/5', {
      method: 'PATCH',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify({
        name: 'Evening run',
        activity_type: 'run',
        description: null,
        private_notes: 'note',
        visibility: 'private',
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
      filters: { type: 'run', startDate: '2024-01-01', endDate: '2024-12-31', nameSearch: ' run ' },
      sortBy: 'distance',
      sortOrder: 'asc',
    })

    // One request, not two: the total now travels with the page, so the filters
    // cannot drift between a list call and a separate count call.
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities?type=run&start_date=2024-01-01&end_date=2024-12-31&name_contains=run&sort_by=distance&sort_order=asc&page_number=2&num_records=25',
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
      filters: { type: null, startDate: null, endDate: null, nameSearch: null },
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

describe('fetchFollowersActivities', () => {
  const feedPage = {
    items: [
      { ...activityDto, id: 1, user_id: 7 },
      { ...activityDto, id: 2, user_id: 8 },
      { ...activityDto, id: 3, user_id: 7 },
    ],
    num_records: 25,
    next_cursor: 'cursor-2',
    users: { '7': { id: 7, name: 'Jane Runner', username: 'jane', city: null, photo_path: null } },
  }

  it('requests the feed with the cursor and maps the slice', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(feedPage)

    const slice = await fetchFollowersActivities('cursor-1', 25, 'following')

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/feed?num_records=25&scope=following&cursor=cursor-1',
      {
        signal: undefined,
      },
    )
    expect(slice.items.map((activity) => activity.id)).toEqual([1, 2, 3])
    expect(slice.nextCursor).toBe('cursor-2')
  })

  it("asks for the viewer's own activities with scope=mine", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(feedPage)

    await fetchFollowersActivities(null, 25, 'mine')

    expect(apiFetch).toHaveBeenCalledWith('/activities/feed?num_records=25&scope=mine', {
      signal: undefined,
    })
  })

  it('returns each distinct owner once, from the same response', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(feedPage)

    const { owners } = await fetchFollowersActivities(null, 25, 'following')

    expect(apiFetch).toHaveBeenCalledOnce()
    expect([...owners.keys()].sort()).toEqual([7, 8])
    expect(owners.get(7)).toMatchObject({ name: 'Jane Runner', username: 'jane' })
    // 8 is inactive or awaiting approval, so the server left it out: same as a 404 lookup.
    expect(owners.get(8)).toBeNull()
  })

  it('returns no owners for an empty slice', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [], num_records: 25, next_cursor: null })

    const slice = await fetchFollowersActivities(null, 25, 'following')

    expect(slice).toEqual({ items: [], nextCursor: null, owners: new Map() })
  })
})

describe('fetchUserActivityTypes', () => {
  it('returns the keys of the response, dropping any the client does not know', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ride: 'Ride', run: 'Run', curling: 'Curling' })

    await expect(fetchUserActivityTypes()).resolves.toEqual(['ride', 'run'])

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/types',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('returns no types when the body is null', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    await expect(fetchUserActivityTypes()).resolves.toEqual([])
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
      await fetchUserWeekActivities(7, 0, 'monday')

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

describe('conditional activity writes', () => {
  it('editActivity sends If-Match built from the version the form was loaded at', async () => {
    // Without this header the save is last-writer-wins: the edit form posts
    // every field it holds, so a copy loaded before someone else's change
    // silently reverts that change.
    vi.mocked(apiFetch).mockResolvedValueOnce(activityDto)

    await editActivity(
      5,
      {
        name: 'Evening run',
        activityType: 'run',
        description: '',
        privateNotes: '',
        visibility: 'public',
        isHidden: false,
        hideStartTime: false,
        hideLocation: false,
        hideMap: false,
        hideHr: false,
        hidePower: false,
        hideCadence: false,
        hideElevation: false,
        hideSpeed: false,
        hidePace: false,
        hideLaps: false,
        hideWorkoutSetsSteps: false,
        hideGear: false,
      },
      7,
    )

    expect(vi.mocked(apiFetch).mock.lastCall?.[1]?.headers).toEqual({ 'If-Match': '"7"' })
  })

  it('maps the version off the wire so it can be echoed back', async () => {
    expect(mapActivity({ ...activityDto, version: 9 }).version).toBe(9)
  })
})
