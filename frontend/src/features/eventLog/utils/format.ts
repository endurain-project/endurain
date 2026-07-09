/**
 * Formats a latency in milliseconds compactly (`123 ms`, `1.2 s`, `12 s`), or a
 * dash when unmeasured.
 *
 * @param ms - Latency in milliseconds, or `null`.
 * @returns A compact latency label.
 */
export function formatLatencyMs(ms: number | null): string {
  if (ms === null) {
    return '—'
  }
  if (ms < 1000) {
    return `${Math.round(ms)} ms`
  }
  const seconds = ms / 1000
  return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
}

/**
 * Formats an age in seconds as a compact duration (`3s`, `5m`, `2h 10m`,
 * `1d 4h`), or a dash when unknown.
 *
 * @param seconds - Age in seconds, or `null`.
 * @returns A compact age label.
 */
export function formatAgeSeconds(seconds: number | null): string {
  if (seconds === null) {
    return '—'
  }
  const total = Math.max(0, Math.floor(seconds))
  if (total < 60) {
    return `${total}s`
  }
  const minutes = Math.floor(total / 60)
  if (minutes < 60) {
    return `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ${minutes % 60}m`
  }
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}

/**
 * Extracts a human-readable `activity_id` from an event's correlation metadata,
 * when present.
 *
 * @param metadata - The event metadata, or `null`.
 * @returns The activity id as a string, or `null` when absent.
 */
export function activityIdFromMetadata(metadata: Record<string, unknown> | null): string | null {
  const value = metadata?.activity_id
  return typeof value === 'number' || typeof value === 'string' ? String(value) : null
}
