import type {
  DeadLetterJob,
  DeadLetterJobDto,
  JobsSummary,
  JobsSummaryDto,
  JobSubscriberStats,
  JobSubscriberStatsDto,
} from '@/features/jobs/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/**
 * Maps a raw `JobSubscriberStats` payload to the clean model.
 *
 * @param dto - Raw per-subscriber stats payload from the backend.
 * @returns The normalized per-subscriber stats.
 */
function mapSubscriberStats(dto: JobSubscriberStatsDto): JobSubscriberStats {
  return {
    subscriberId: dto.subscriber_id,
    eventType: dto.event_type,
    total: dto.total,
    pending: dto.pending,
    claimed: dto.claimed,
    completed: dto.completed,
    deadLetter: dto.dead_letter,
  }
}

/**
 * Maps a raw `DeadLetterJob` payload to the clean model.
 *
 * @param dto - Raw dead-letter job payload from the backend.
 * @returns The normalized dead-letter job.
 */
function mapDeadLetterJob(dto: DeadLetterJobDto): DeadLetterJob {
  return {
    id: dto.id,
    eventId: dto.event_id,
    eventType: dto.event_type,
    subscriberId: dto.subscriber_id,
    source: dto.source,
    attempts: dto.attempts,
    maxAttempts: dto.max_attempts,
    lastError: dto.last_error ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at ?? null,
  }
}

/**
 * Maps a raw `JobsSummary` payload to the clean model — the single boundary
 * where the backend wire format (snake_case) is normalized.
 *
 * @param dto - Raw summary payload from the backend.
 * @returns The normalized summary model.
 */
export function mapJobsSummary(dto: JobsSummaryDto): JobsSummary {
  return {
    windowHours: dto.window_hours,
    totalJobs: dto.total_jobs,
    pending: dto.pending,
    claimed: dto.claimed,
    completed: dto.completed,
    deadLetter: dto.dead_letter,
    oldestPendingSeconds: dto.oldest_pending_seconds ?? null,
    bySubscriber: dto.by_subscriber.map(mapSubscriberStats),
    recentDeadLetter: dto.recent_dead_letter.map(mapDeadLetterJob),
  }
}

/**
 * Fetches the durable-jobs processing summary (admin scope `server_settings:read`).
 *
 * @param hours - Look-back window in hours (1-168).
 * @param signal - Optional abort signal for cancellation.
 * @returns The aggregated summary, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchJobsSummary(hours: number, signal?: AbortSignal): Promise<JobsSummary> {
  const dto = await apiFetch<JobsSummaryDto>(`/jobs/summary?hours=${hours}`, { signal })
  return mapJobsSummary(dto)
}

/**
 * Replays a dead-lettered job (admin scope `server_settings:write`).
 *
 * @param jobId - The dead-letter job to requeue.
 * @returns True when the job was requeued for a fresh run.
 * @throws {HttpError} When the request fails (e.g. 404 when no such dead-letter job).
 */
export async function replayJob(jobId: string): Promise<boolean> {
  const dto = await apiFetch<Schemas['JobReplayResult']>(
    `/jobs/${encodeURIComponent(jobId)}/replay`,
    { method: 'POST' },
  )
  return dto.replayed
}
