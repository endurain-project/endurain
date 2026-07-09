import { describe, expect, it } from 'vitest'

import type {
  EventLogFailureDto,
  EventLogPendingDto,
  EventLogSummaryDto,
  EventTypeStatsDto,
} from '@/features/eventLog/types'

import { mapEventLogSummary } from '@/features/eventLog/services/eventLog'
import {
  activityIdFromMetadata,
  formatAgeSeconds,
  formatLatencyMs,
} from '@/features/eventLog/utils/format'

const baseStats: EventTypeStatsDto = {
  event_type: 'activity.created',
  total: 2,
  published: 0,
  processing: 0,
  completed: 1,
  failed: 1,
  dead_letter: 0,
  avg_processing_time_ms: 75,
  max_processing_time_ms: 100,
}

const basePending: EventLogPendingDto = {
  event_type: 'activity.created',
  status: 'processing',
  count: 1,
  oldest_seconds: 42,
}

const baseFailure: EventLogFailureDto = {
  id: 'e2',
  event_type: 'activity.created',
  event_source: 'api:store_activity',
  handler_name: 'on_activity_created',
  error_message: 'boom',
  retry_count: 0,
  event_metadata: { activity_id: 42, request_id: 'r1' },
  created_at: '2026-07-09T00:00:00+00:00',
  completed_at: '2026-07-09T00:00:01+00:00',
}

const summaryDto: EventLogSummaryDto = {
  window_hours: 24,
  total_events: 3,
  by_type: [baseStats],
  pending: [basePending],
  recent_failures: [baseFailure],
}

describe('mapEventLogSummary', () => {
  it('maps the snake_case payload to the clean camelCase model', () => {
    const summary = mapEventLogSummary(summaryDto)

    expect(summary.windowHours).toBe(24)
    expect(summary.totalEvents).toBe(3)
    expect(summary.byType[0]).toEqual({
      eventType: 'activity.created',
      total: 2,
      published: 0,
      processing: 0,
      completed: 1,
      failed: 1,
      deadLetter: 0,
      avgProcessingTimeMs: 75,
      maxProcessingTimeMs: 100,
    })
    expect(summary.pending[0]).toEqual({
      eventType: 'activity.created',
      status: 'processing',
      count: 1,
      oldestSeconds: 42,
    })
    expect(summary.recentFailures[0]).toEqual({
      id: 'e2',
      eventType: 'activity.created',
      eventSource: 'api:store_activity',
      handlerName: 'on_activity_created',
      errorMessage: 'boom',
      retryCount: 0,
      eventMetadata: { activity_id: 42, request_id: 'r1' },
      createdAt: '2026-07-09T00:00:00+00:00',
      completedAt: '2026-07-09T00:00:01+00:00',
    })
  })

  it('normalizes missing optional fields to null', () => {
    const summary = mapEventLogSummary({
      window_hours: 24,
      total_events: 1,
      by_type: [{ ...baseStats, avg_processing_time_ms: null, max_processing_time_ms: null }],
      pending: [{ ...basePending, oldest_seconds: null }],
      recent_failures: [
        {
          ...baseFailure,
          handler_name: null,
          error_message: null,
          event_metadata: null,
          completed_at: null,
        },
      ],
    })

    expect(summary.byType[0]).toEqual({
      eventType: 'activity.created',
      total: 2,
      published: 0,
      processing: 0,
      completed: 1,
      failed: 1,
      deadLetter: 0,
      avgProcessingTimeMs: null,
      maxProcessingTimeMs: null,
    })
    expect(summary.pending[0]).toEqual({
      eventType: 'activity.created',
      status: 'processing',
      count: 1,
      oldestSeconds: null,
    })
    expect(summary.recentFailures[0]).toEqual({
      id: 'e2',
      eventType: 'activity.created',
      eventSource: 'api:store_activity',
      handlerName: null,
      errorMessage: null,
      retryCount: 0,
      eventMetadata: null,
      createdAt: '2026-07-09T00:00:00+00:00',
      completedAt: null,
    })
  })
})

describe('formatLatencyMs', () => {
  it('formats sub-second, second, and null latencies', () => {
    expect(formatLatencyMs(0)).toBe('0 ms')
    expect(formatLatencyMs(123)).toBe('123 ms')
    expect(formatLatencyMs(1500)).toBe('1.5 s')
    expect(formatLatencyMs(12000)).toBe('12 s')
    expect(formatLatencyMs(null)).toBe('—')
  })
})

describe('formatAgeSeconds', () => {
  it('formats seconds, minutes, hours, days, and null', () => {
    expect(formatAgeSeconds(5)).toBe('5s')
    expect(formatAgeSeconds(90)).toBe('1m')
    expect(formatAgeSeconds(3660)).toBe('1h 1m')
    expect(formatAgeSeconds(90000)).toBe('1d 1h')
    expect(formatAgeSeconds(null)).toBe('—')
  })
})

describe('activityIdFromMetadata', () => {
  it('extracts a numeric or string activity id, else null', () => {
    expect(activityIdFromMetadata({ activity_id: 42 })).toBe('42')
    expect(activityIdFromMetadata({ activity_id: 'a7' })).toBe('a7')
    expect(activityIdFromMetadata({ other: 1 })).toBeNull()
    expect(activityIdFromMetadata(null)).toBeNull()
  })
})
