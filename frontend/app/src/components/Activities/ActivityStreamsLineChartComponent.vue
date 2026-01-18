<template>
  <canvas ref="chartCanvas"></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { Chart, registerables, type ChartArea } from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'
import {
  formatAverageSpeedMetric,
  formatAverageSpeedImperial,
  activityTypeIsSwimming,
  activityTypeIsRunning,
  activityTypeIsRowing,
  activityTypeIsWalking
} from '@/utils/activityUtils'
import { metersToFeet, kmToMiles } from '@/utils/unitsUtils'
import type { Activity, ActivityStream, StreamWaypoint } from '@/types'

Chart.register(...registerables, zoomPlugin)

interface GraphColors {
  border: string
  gradientStart: string
  gradientEnd: string
}

const props = defineProps<{
  activity: Activity
  graphSelection: string
  activityStreams: ActivityStream[]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const chartCanvas = ref<HTMLCanvasElement | null>(null)
const units = ref('metric')
let myChart: Chart | null = null

/**
 * Creates a gradient fill for the chart area.
 *
 * @param ctx - The canvas 2D rendering context.
 * @param chartArea - The chart area dimensions.
 * @param graphSelection - The type of graph being displayed.
 * @returns A gradient or solid color string.
 */
function createGradient(
  ctx: CanvasRenderingContext2D,
  chartArea: ChartArea | undefined,
  graphSelection: string
): CanvasGradient | string {
  if (!chartArea) {
    const colors = getGraphColors(graphSelection)
    return colors.gradientStart
  }

  const colors = getGraphColors(graphSelection)
  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
  gradient.addColorStop(0, colors.gradientStart)
  gradient.addColorStop(1, colors.gradientEnd)
  return gradient
}

/**
 * Formats pace values as MM:SS for tooltip display.
 *
 * @param value - The pace value in minutes.
 * @returns Formatted pace string.
 */
function formatPaceForTooltip(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'N/A'
  const totalMinutes = Math.floor(value)
  let seconds = Math.round((value - totalMinutes) * 60)

  let minutes = totalMinutes
  if (seconds >= 60) {
    minutes += 1
    seconds = 0
  }

  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

type GraphType = 'hr' | 'power' | 'cad' | 'ele' | 'vel' | 'pace'

const graphColors: Record<GraphType, GraphColors> = {
  hr: {
    border: 'rgba(239, 68, 68, 0.8)',
    gradientStart: 'rgba(239, 68, 68, 0.4)',
    gradientEnd: 'rgba(239, 68, 68, 0.0)'
  },
  power: {
    border: 'rgba(251, 191, 36, 0.8)',
    gradientStart: 'rgba(251, 191, 36, 0.4)',
    gradientEnd: 'rgba(251, 191, 36, 0.0)'
  },
  cad: {
    border: 'rgba(168, 85, 247, 0.8)',
    gradientStart: 'rgba(168, 85, 247, 0.4)',
    gradientEnd: 'rgba(168, 85, 247, 0.0)'
  },
  ele: {
    border: 'rgba(34, 197, 94, 0.8)',
    gradientStart: 'rgba(34, 197, 94, 0.4)',
    gradientEnd: 'rgba(34, 197, 94, 0.0)'
  },
  vel: {
    border: 'rgba(59, 130, 246, 0.8)',
    gradientStart: 'rgba(59, 130, 246, 0.4)',
    gradientEnd: 'rgba(59, 130, 246, 0.0)'
  },
  pace: {
    border: 'rgba(236, 72, 153, 0.8)',
    gradientStart: 'rgba(236, 72, 153, 0.4)',
    gradientEnd: 'rgba(236, 72, 153, 0.0)'
  }
}

/**
 * Returns color configuration based on graph type.
 *
 * @param graphSelection - The type of graph being displayed.
 * @returns Color configuration object.
 */
function getGraphColors(graphSelection: string): GraphColors {
  if (graphSelection in graphColors) {
    return graphColors[graphSelection as GraphType]
  }
  return graphColors.vel
}

const computedChartData = computed(() => {
  const data: (number | null)[] = []
  let label = ''
  const cadData: number[] = []
  const labels: string[] = []

  if (authStore.isAuthenticated && authStore.user) {
    units.value = authStore.user.units ?? 'metric'
  } else {
    units.value = serverSettingsStore.serverSettings.units ?? 'metric'
  }

  for (const stream of props.activityStreams) {
    // Save Cadence (Stroke Rate) data for swimming rest detection
    if (stream.stream_type === 3) {
      for (const streamPoint of stream.stream_waypoints) {
        cadData.push(Number.parseInt(streamPoint.cad || '0'))
      }
    }
    // Add data points
    if (stream.stream_type === 1 && props.graphSelection === 'hr') {
      for (const streamPoint of stream.stream_waypoints) {
        data.push(Number.parseInt(streamPoint.hr || '0'))
        label = t('generalItems.labelHRinBpm')
      }
    } else if (stream.stream_type === 2 && props.graphSelection === 'power') {
      for (const streamPoint of stream.stream_waypoints) {
        data.push(Number.parseInt(streamPoint.power || '0'))
        label = t('generalItems.labelPowerInWatts')
      }
    } else if (stream.stream_type === 3 && props.graphSelection === 'cad') {
      for (const streamPoint of stream.stream_waypoints) {
        let cadence = Number.parseInt(streamPoint.cad || '0')
        // For running, double the cadence to get total steps per minute (SPM)
        if (activityTypeIsRunning(props.activity)) {
          cadence = cadence * 2
        }
        data.push(cadence)
        label = activityTypeIsSwimming(props.activity)
          ? t('generalItems.labelStrokeRateInSpm')
          : t('generalItems.labelCadenceInRpm')
      }
    } else if (stream.stream_type === 4 && props.graphSelection === 'ele') {
      for (const streamPoint of stream.stream_waypoints) {
        if (units.value === 'metric') {
          data.push(Number.parseFloat(streamPoint.ele || '0'))
          label = t('generalItems.labelElevationInMeters')
        } else {
          data.push(Number.parseFloat(metersToFeet(streamPoint.ele || '0')))
          label = t('generalItems.labelElevationInFeet')
        }
      }
    } else if (stream.stream_type === 5 && props.graphSelection === 'vel') {
      if (units.value === 'metric') {
        data.push(
          ...stream.stream_waypoints.map((velData: StreamWaypoint) =>
            Number.parseFloat(formatAverageSpeedMetric(velData.vel || 0))
          )
        )
        label = t('generalItems.labelVelocityInKmH')
      } else {
        data.push(
          ...stream.stream_waypoints.map((velData: StreamWaypoint) =>
            Number.parseFloat(formatAverageSpeedImperial(velData.vel || 0))
          )
        )
        label = t('generalItems.labelVelocityInMph')
      }
    } else if (stream.stream_type === 6 && props.graphSelection === 'pace') {
      for (const paceData of stream.stream_waypoints) {
        if (paceData.pace === 0 || paceData.pace === null) {
          data.push(null)
        } else {
          let converted: number | null = null
          if (
            activityTypeIsRunning(props.activity) ||
            activityTypeIsWalking(props.activity) ||
            activityTypeIsRowing(props.activity)
          ) {
            if (units.value === 'metric') {
              converted = (paceData.pace! * 1000) / 60
            } else {
              converted = (paceData.pace! * 1609.34) / 60
            }
            const threshold = units.value === 'metric' ? 20 : 20 * 1.60934
            if (converted > threshold || Number.isNaN(converted)) {
              data.push(null)
            } else {
              data.push(converted)
            }
          } else if (activityTypeIsSwimming(props.activity)) {
            if (units.value === 'metric') {
              converted = (paceData.pace! * 100) / 60
            } else {
              converted = (paceData.pace! * 100 * 0.9144) / 60
            }
            const swimThreshold = units.value === 'metric' ? 10 : 10 * 1.0936
            if (converted > swimThreshold || Number.isNaN(converted)) {
              data.push(null)
            } else {
              data.push(converted)
            }
          }
        }
      }
      if (
        activityTypeIsRunning(props.activity) ||
        activityTypeIsWalking(props.activity) ||
        activityTypeIsRowing(props.activity)
      ) {
        if (units.value === 'metric') {
          label = t('generalItems.labelPaceInMinKm')
        } else {
          label = t('generalItems.labelPaceInMinMile')
        }
      } else if (activityTypeIsSwimming(props.activity)) {
        if (units.value === 'metric') {
          label = t('generalItems.labelPaceInMin100m')
        } else {
          label = t('generalItems.labelPaceInMin100yd')
        }
      }
    }
  }

  const totalDistance = props.activity.distance / 1000
  const numberOfDataPoints = data.length
  const distanceInterval = totalDistance / numberOfDataPoints

  for (let i = 0; i < numberOfDataPoints; i++) {
    if (units.value === 'metric') {
      if (activityTypeIsSwimming(props.activity)) {
        labels.push(`${(i * distanceInterval).toFixed(1)}km`)
      } else {
        labels.push(`${(i * distanceInterval).toFixed(0)}km`)
      }
    } else {
      if (activityTypeIsSwimming(props.activity)) {
        labels.push(`${kmToMiles(i * distanceInterval)}mi`)
      } else {
        labels.push(`${kmToMiles(i * distanceInterval)}mi`)
      }
    }
  }

  // Calculate average and max/min for reference lines (excluding null values)
  const validData = data.filter((v): v is number => v !== null && !Number.isNaN(v))
  let avgValue: number | null = null
  let extremeValue: number | null = null
  let extremeLabel = ''

  if (validData.length > 0) {
    avgValue = validData.reduce((a, b) => a + b, 0) / validData.length

    if (props.graphSelection === 'pace') {
      extremeValue = Math.min(...validData)
      extremeLabel = 'Best'
    } else {
      extremeValue = Math.max(...validData)
      extremeLabel = 'Maximum'
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const datasets: any[] = [
    {
      label: label,
      data: data,
      yAxisID: 'y',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      backgroundColor: function (context: any) {
        const chart = context.chart
        const { ctx, chartArea } = chart
        if (!chartArea) {
          const colors = getGraphColors(props.graphSelection)
          return colors.gradientStart
        }
        return createGradient(ctx, chartArea, props.graphSelection)
      },
      borderColor: getGraphColors(props.graphSelection).border,
      fill: props.graphSelection === 'pace' ? 'start' : true,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: getGraphColors(props.graphSelection).border
    }
  ]

  if (avgValue !== null) {
    datasets.push({
      label: t('generalItems.labelAverage'),
      data: Array(data.length).fill(avgValue),
      yAxisID: 'y',
      borderColor: 'rgba(156, 163, 175, 0.6)',
      borderWidth: 2,
      borderDash: [10, 5],
      fill: false,
      pointRadius: 0,
      pointHoverRadius: 0,
      tension: 0
    })
  }

  if (extremeValue !== null) {
    datasets.push({
      label: extremeLabel,
      data: Array(data.length).fill(extremeValue),
      yAxisID: 'y',
      borderColor: 'rgba(220, 38, 38, 0.5)',
      borderWidth: 1.5,
      borderDash: [5, 5],
      fill: false,
      pointRadius: 0,
      pointHoverRadius: 0,
      tension: 0
    })
  }

  // Only push laps 'background shading' if there is cadence data and indoor swimming activity
  if (cadData.length > 0 && props.activity.activity_type === 8) {
    datasets.push({
      type: 'bar',
      label: t('generalItems.labelLaps'),
      data: cadData.map((d) => (d === 0 ? 0 : 1)),
      yAxisID: 'y1',
      backgroundColor: 'rgba(0, 0, 0, 0.2)',
      fill: true,
      fillColor: 'rgba(0, 0, 0, 0.2)',
      borderWidth: 0,
      barThickness: 5
    })
  }

  return {
    datasets: datasets,
    labels: labels
  }
})

watch(
  computedChartData,
  (newChartData) => {
    if (myChart) {
      myChart.data.datasets = newChartData.datasets
      myChart.data.labels = newChartData.labels
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const scales = myChart.options?.scales as any
      if (scales?.y) {
        scales.y.reverse = props.graphSelection === 'pace'
      }
      myChart.update()
    }
  },
  { deep: true }
)

// Custom crosshair plugin
const crosshairPlugin = {
  id: 'customCrosshair',
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  afterDraw: (chart: any) => {
    if (chart.tooltip?._active && chart.tooltip._active.length) {
      const ctx = chart.ctx
      const activePoint = chart.tooltip._active[0]
      const x = activePoint.element.x
      const topY = chart.scales.y.top
      const bottomY = chart.scales.y.bottom

      ctx.save()
      ctx.beginPath()
      ctx.setLineDash([5, 5])
      ctx.moveTo(x, topY)
      ctx.lineTo(x, bottomY)
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)'
      ctx.stroke()
      ctx.restore()
    }
  }
}

onMounted(() => {
  if (!chartCanvas.value) return

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  myChart = new Chart(ctx, {
    type: 'line',
    data: computedChartData.value,
    plugins: [crosshairPlugin],
    options: {
      responsive: true,
      animation: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      elements: {
        point: {
          radius: 0,
          hitRadius: 10,
          hoverRadius: 4
        },
        line: {
          tension: 0.4
        }
      },
      scales: {
        y: {
          beginAtZero: false,
          position: 'left',
          reverse: props.graphSelection === 'pace',
          grid: {
            lineWidth: 1
          }
        },
        y1: {
          beginAtZero: true,
          max: 1,
          display: false
        },
        x: {
          ticks: {
            maxTicksLimit: 10,
            autoSkip: true
          },
          grid: {
            lineWidth: 1
          }
        }
      },
      plugins: {
        tooltip: {
          enabled: true,
          callbacks: {
            title: function (context) {
              return context[0]?.label || ''
            },
            label: function (context) {
              const label = context.dataset.label || ''
              const value = context.parsed.y

              if (value === null || value === undefined) {
                return `${label}: N/A`
              }

              if (props.graphSelection === 'pace') {
                const formatted = formatPaceForTooltip(value)
                return `${label}: ${formatted}`
              } else if (props.graphSelection === 'hr') {
                return `${label}: ${Math.round(value)}`
              } else if (props.graphSelection === 'power') {
                return `${label}: ${Math.round(value)} W`
              } else if (props.graphSelection === 'cad') {
                return `${label}: ${Math.round(value)}`
              } else if (props.graphSelection === 'ele') {
                return `${label}: ${value.toFixed(1)}`
              } else if (props.graphSelection === 'vel') {
                return `${label}: ${value.toFixed(1)}`
              }

              return `${label}: ${value}`
            }
          }
        },
        zoom: {
          pan: {
            enabled: true,
            mode: 'x',
            modifierKey: 'shift'
          },
          zoom: {
            wheel: {
              enabled: true,
              speed: 0.1
            },
            pinch: {
              enabled: true
            },
            mode: 'x'
          },
          limits: {
            x: {
              min: 'original',
              max: 'original'
            }
          }
        }
      }
    }
  })
})

onUnmounted(() => {
  if (myChart) {
    myChart.destroy()
  }
})
</script>
