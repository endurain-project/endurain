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
