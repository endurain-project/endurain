import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GearActivity, GearActivityDto } from '@/features/gears/types'

import { apiFetch } from '@/services/http'
import { fetchGearActivities, mapGearActivity } from '@/features/gears/services/gearActivities'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const activityDto: GearActivityDto = {
  id: 11,
  name: 'Morning Ride',
  activity_type: 1,
  start_time: '2024-03-01T07:00:00Z',
  timezone: 'Europe/Lisbon',
  distance: 25_000,
  total_timer_time: 3600,
  is_hidden: false,
}

const mappedActivity: GearActivity = {
  id: 11,
  name: 'Morning Ride',
  activityType: 1,
  startTime: '2024-03-01T07:00:00Z',
  timezone: 'Europe/Lisbon',
  distance: 25_000,
  totalTimerTime: 3600,
}

describe('mapGearActivity', () => {
  it('maps the snake-cased DTO to the trimmed model', () => {
    expect(mapGearActivity(activityDto)).toEqual(mappedActivity)
  })

  it('defaults an absent id to zero and absent optionals to null', () => {
    expect(
      mapGearActivity({ name: 'Run', activity_type: 2, distance: 5000, is_hidden: false }),
    ).toEqual({
      id: 0,
      name: 'Run',
      activityType: 2,
      startTime: null,
      timezone: null,
      distance: 5000,
      totalTimerTime: null,
    })
  })
})

describe('fetchGearActivities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the paginated gear-activities page and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [activityDto],
      total: 1,
      page: 1,
      num_records: 25,
      next: null,
    })

    const result = await fetchGearActivities(5, { page: 1, numRecords: 25 })

    // One request: the total arrives with the page.
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/gears/5?page_number=1&num_records=25',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual({ records: [mappedActivity], total: 1 })
  })

  it('treats an empty page as no records', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      num_records: 25,
      next: null,
    })
    await expect(fetchGearActivities(5, { page: 1, numRecords: 25 })).resolves.toEqual({
      records: [],
      total: 0,
    })
  })
})
