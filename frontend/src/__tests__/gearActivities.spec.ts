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
  start_time: '2024-03-01T07:00:00',
  distance: 25_000,
  total_timer_time: 3600,
  is_hidden: false,
}

const mappedActivity: GearActivity = {
  id: 11,
  name: 'Morning Ride',
  activityType: 1,
  startTime: '2024-03-01T07:00:00',
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
      distance: 5000,
      totalTimerTime: null,
    })
  })
})

describe('fetchGearActivities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the paginated gear-activities list and count and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([activityDto]).mockResolvedValueOnce({ count: 1 })

    const result = await fetchGearActivities(5, { page: 1, numRecords: 25 })

    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/activities/gears/5?page_number=1&num_records=25',
      expect.objectContaining({ signal: undefined }),
    )
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/activities/gears/5/count',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual({ records: [mappedActivity], total: 1 })
  })

  it('treats a null list as an empty page', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null).mockResolvedValueOnce({ count: 0 })
    await expect(fetchGearActivities(5, { page: 1, numRecords: 25 })).resolves.toEqual({
      records: [],
      total: 0,
    })
  })
})
