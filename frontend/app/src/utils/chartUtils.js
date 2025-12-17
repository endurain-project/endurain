/**
 * Formats seconds into a human-readable duration string.
 * @param {number} seconds - The total number of seconds to format.
 * @returns {string} Formatted duration string (e.g., "2h 30m" or "45m").
 */
export function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
}

/**
 * Formats HR zone label with percentage and optional time duration.
 * @param {number} value - Percentage value
 * @param {number|null} timeSeconds - Time in seconds (0 or null means no time)
 * @returns {string} Formatted label (e.g., "25%" or "25% (15m)")
 */
export function formatHrZoneLabel(value, timeSeconds) {
  const percentage = `${Math.round(value)}%`
  if (!timeSeconds || timeSeconds === 0) {
    return percentage
  }
  const timeStr = formatDuration(timeSeconds)
  return `${percentage} (${timeStr})`
}

export function getZoneColor(index) {
  // Example colors for 5 HR zones
  const colors = [
    '#1e90ff', // Zone 1: blue
    '#28a745', // Zone 2: green
    '#ffc107', // Zone 3: yellow
    '#fd7e14', // Zone 4: orange
    '#dc3545' // Zone 5: red
  ]
  return colors[index] || '#000'
}

export function getHrBarChartData(hrZones, t) {
  const zones = Object.values(hrZones)
  return {
    labels: zones.map(
      (z, i) => `${t('activityMandAbovePillsComponent.labelGraphHRZone')} ${i + 1} (${z.hr || ''})`
    ),
    // values: zones.map(z => `${z.percent ?? 0}%`),
    values: zones.map((z) => z.percent ?? 0),
    barColors: zones.map((_, i) => getZoneColor(i)),
    timeSeconds: zones.map((z) => z.time_seconds ?? 0)
  }
}
