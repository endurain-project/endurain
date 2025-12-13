/**
 * Formats seconds into a human-readable duration string.
 * @param {number} seconds - The total number of seconds to format.
 * @returns {string} Formatted duration string (e.g., "2h 30m" or "45m").
 */
function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
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
