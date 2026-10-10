import { describe, expect, it } from 'vitest'

import type { DeadLetterJobDto, JobSubscriberStatsDto, JobsSummaryDto } from '@/features/jobs/types'

import { mapJobsSummary } from '@/features/jobs/services/jobs'
import { formatAgeSeconds } from '@/features/jobs/utils/format'

const baseSubscriber: JobSubscriberStatsDto = {
  subscriber_id: 'activity_thumbnail.generate',
  event_type: 'activity.created',
  total: 3,
  pending: 1,
  claimed: 0,
  completed: 1,
  dead_letter: 1,
}

const baseDeadLetter: DeadLetterJobDto = {
  id: 'job-1',
  event_id: 'ev-1',
  event_type: 'activity.created',
  subscriber_id: 'activity_thumbnail.generate',
  source: 'api:store_activity',
  attempts: 5,
  max_attempts: 5,
  last_error: 'boom',
  created_at: '2026-07-14T12:00:00+00:00',
  updated_at: '2026-07-14T12:05:00+00:00',
  completed_at: '2026-07-14T12:05:00+00:00',
}

const summaryDto: JobsSummaryDto = {
  window_hours: 24,
  total_jobs: 3,
  pending: 1,
  claimed: 0,
  completed: 1,
  dead_letter: 1,
  oldest_pending_seconds: 90,
  by_subscriber: [baseSubscriber],
  recent_dead_letter: [baseDeadLetter],
}

describe('mapJobsSummary', () => {
  it('maps the snake_case payload to the clean camelCase model', () => {
    const summary = mapJobsSummary(summaryDto)

    expect(summary.windowHours).toBe(24)
    expect(summary.totalJobs).toBe(3)
    expect(summary.deadLetter).toBe(1)
    expect(summary.oldestPendingSeconds).toBe(90)
    expect(summary.bySubscriber[0]).toEqual({
      subscriberId: 'activity_thumbnail.generate',
      eventType: 'activity.created',
      total: 3,
      pending: 1,
      claimed: 0,
      completed: 1,
      deadLetter: 1,
    })
    expect(summary.recentDeadLetter[0]).toEqual({
      id: 'job-1',
      eventId: 'ev-1',
      eventType: 'activity.created',
      subscriberId: 'activity_thumbnail.generate',
      source: 'api:store_activity',
      attempts: 5,
      maxAttempts: 5,
      lastError: 'boom',
      createdAt: '2026-07-14T12:00:00+00:00',
      updatedAt: '2026-07-14T12:05:00+00:00',
      completedAt: '2026-07-14T12:05:00+00:00',
    })
  })

  it('normalizes missing optional fields to null', () => {
    const summary = mapJobsSummary({
      ...summaryDto,
      oldest_pending_seconds: null,
      recent_dead_letter: [{ ...baseDeadLetter, last_error: null, completed_at: null }],
    })

    expect(summary.oldestPendingSeconds).toBeNull()
    expect(summary.recentDeadLetter[0]).toEqual({
      id: 'job-1',
      eventId: 'ev-1',
      eventType: 'activity.created',
      subscriberId: 'activity_thumbnail.generate',
      source: 'api:store_activity',
      attempts: 5,
      maxAttempts: 5,
      lastError: null,
      createdAt: '2026-07-14T12:00:00+00:00',
      updatedAt: '2026-07-14T12:05:00+00:00',
      completedAt: null,
    })
  })
})

describe('formatAgeSeconds', () => {
  it('formats sub-minute, minute, hour, and day ranges', () => {
    expect(formatAgeSeconds(30)).toBe('30s')
    expect(formatAgeSeconds(90)).toBe('1m')
    expect(formatAgeSeconds(3600)).toBe('1h 0m')
    expect(formatAgeSeconds(90000)).toBe('1d 1h')
  })

  it('returns a dash when unknown', () => {
    expect(formatAgeSeconds(null)).toBe('—')
  })
})
