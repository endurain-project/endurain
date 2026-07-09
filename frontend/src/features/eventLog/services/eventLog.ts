import type {
  EventLogFailure,
  EventLogFailureDto,
  EventLogPending,
  EventLogPendingDto,
  EventLogSummary,
  EventLogSummaryDto,
  EventTypeStats,
  EventTypeStatsDto,
} from '@/features/eventLog/types'

import { apiFetch } from '@/services/http'

/**
 * Maps a raw `EventTypeStats` payload to the clean model.
 *
 * @param dto - Raw per-type stats payload from the backend.
 * @returns The normalized per-type stats.
 */
function mapEventTypeStats(dto: EventTypeStatsDto): EventTypeStats {
  return {
    eventType: dto.event_type,
    total: dto.total,
    published: dto.published,
    processing: dto.processing,
    completed: dto.completed,
    failed: dto.failed,
    deadLetter: dto.dead_letter,
    avgProcessingTimeMs: dto.avg_processing_time_ms ?? null,
    maxProcessingTimeMs: dto.max_processing_time_ms ?? null,
  }
}

/**
 * Maps a raw `EventLogPending` payload to the clean model.
 *
 * @param dto - Raw pending-group payload from the backend.
 * @returns The normalized pending group.
 */
function mapPending(dto: EventLogPendingDto): EventLogPending {
  return {
    eventType: dto.event_type,
    status: dto.status,
    count: dto.count,
    oldestSeconds: dto.oldest_seconds ?? null,
  }
}

/**
 * Maps a raw `EventLogFailure` payload to the clean model.
 *
 * @param dto - Raw failure payload from the backend.
 * @returns The normalized failure.
 */
function mapFailure(dto: EventLogFailureDto): EventLogFailure {
  return {
    id: dto.id,
    eventType: dto.event_type,
    eventSource: dto.event_source,
    handlerName: dto.handler_name ?? null,
    errorMessage: dto.error_message ?? null,
    retryCount: dto.retry_count,
    eventMetadata: (dto.event_metadata as Record<string, unknown> | null) ?? null,
    createdAt: dto.created_at,
    completedAt: dto.completed_at ?? null,
  }
}

/**
 * Maps a raw `EventLogSummary` payload to the clean model — the single boundary
 * where the backend wire format (snake_case) is normalized.
 *
 * @param dto - Raw summary payload from the backend.
 * @returns The normalized summary model.
 */
export function mapEventLogSummary(dto: EventLogSummaryDto): EventLogSummary {
  return {
    windowHours: dto.window_hours,
    totalEvents: dto.total_events,
    byType: dto.by_type.map(mapEventTypeStats),
    pending: dto.pending.map(mapPending),
    recentFailures: dto.recent_failures.map(mapFailure),
  }
}

/**
 * Fetches the event-log observability summary (admin scope `server_settings:read`).
 *
 * @param hours - Look-back window in hours (1-168).
 * @param signal - Optional abort signal for cancellation.
 * @returns The aggregated summary, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchEventLogSummary(
  hours: number,
  signal?: AbortSignal,
): Promise<EventLogSummary> {
  const dto = await apiFetch<EventLogSummaryDto>(`/event_log/summary?hours=${hours}`, { signal })
  return mapEventLogSummary(dto)
}
