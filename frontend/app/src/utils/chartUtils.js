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
    barColors: zones.map((_, i) => getZoneColor(i))
  }
}
