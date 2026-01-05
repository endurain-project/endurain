<template>
  <canvas ref="chartCanvas"></canvas>
</template>

<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { Chart, registerables } from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'
Chart.register(...registerables, zoomPlugin)

import {
  formatAverageSpeedMetric,
  formatAverageSpeedImperial,
  activityTypeIsSwimming,
  activityTypeIsRunning,
  activityTypeIsRowing,
  activityTypeIsWalking
} from '@/utils/activityUtils'
import { metersToFeet, kmToMiles } from '@/utils/unitsUtils'

export default {
  props: {
    activity: {
      type: Object,
      required: true
    },
    graphSelection: {
      type: String,
      required: true
    },
    activityStreams: {
      type: Array,
      required: true
    }
  },
  setup(props) {
    const { t } = useI18n()
    const authStore = useAuthStore()
    const serverSettingsStore = useServerSettingsStore()
    const chartCanvas = ref(null)
    const units = ref(1)
    let myChart = null

    // Function to create gradient fill for chart
    function createGradient(ctx, chartArea, graphSelection) {
      if (!chartArea) {
        const colors = getGraphColors(graphSelection)
        return colors.gradientStart
      }

      const colors = getGraphColors(graphSelection)
      const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
      gradient.addColorStop(0, colors.gradientStart) // More opaque at top
      gradient.addColorStop(1, colors.gradientEnd) // Transparent at bottom
      return gradient
    }

    // Function to format pace values as MM:SS
    function formatPaceForTooltip(value) {
      if (value === null || value === undefined) return 'N/A'
      const totalMinutes = Math.floor(value)
      let seconds = Math.round((value - totalMinutes) * 60)

      // Handle case where seconds round to 60 (should be next minute)
      let minutes = totalMinutes
      if (seconds >= 60) {
        minutes += 1
        seconds = 0
      }

      return `${minutes}:${seconds.toString().padStart(2, '0')}`
    }

    // Function to get colors based on graph type
    function getGraphColors(graphSelection) {
      const colors = {
        hr: {
          border: 'rgba(239, 68, 68, 0.8)', // Red
          gradientStart: 'rgba(239, 68, 68, 0.4)',
          gradientEnd: 'rgba(239, 68, 68, 0.0)'
        },
        power: {
          border: 'rgba(251, 191, 36, 0.8)', // Yellow/Gold
          gradientStart: 'rgba(251, 191, 36, 0.4)',
          gradientEnd: 'rgba(251, 191, 36, 0.0)'
        },
        cad: {
          border: 'rgba(168, 85, 247, 0.8)', // Purple
          gradientStart: 'rgba(168, 85, 247, 0.4)',
          gradientEnd: 'rgba(168, 85, 247, 0.0)'
        },
        ele: {
          border: 'rgba(34, 197, 94, 0.8)', // Green
          gradientStart: 'rgba(34, 197, 94, 0.4)',
          gradientEnd: 'rgba(34, 197, 94, 0.0)'
        },
        vel: {
          border: 'rgba(59, 130, 246, 0.8)', // Blue
          gradientStart: 'rgba(59, 130, 246, 0.4)',
          gradientEnd: 'rgba(59, 130, 246, 0.0)'
        },
        pace: {
          border: 'rgba(236, 72, 153, 0.8)', // Pink
          gradientStart: 'rgba(236, 72, 153, 0.4)',
          gradientEnd: 'rgba(236, 72, 153, 0.0)'
        }
      }
      return colors[graphSelection] || colors.vel // Default to blue
    }

    const computedChartData = computed(() => {
      const data = []
      let label = ''
      const cadData = []
      let cadLabel = ''
      const labels = []
      let roundValues = true

      if (authStore.isAuthenticated) {
        units.value = authStore.user.units
      } else {
        units.value = serverSettingsStore.serverSettings.units
      }

      for (const stream of props.activityStreams) {
        // Save Cadence (Stroke Rate) data for swimming rest detection
        if (stream.stream_type === 3) {
          for (const streamPoint of stream.stream_waypoints) {
            cadData.push(Number.parseInt(streamPoint.cad))
          }
          if (cadData.length > 0) {
            cadLabel = activityTypeIsSwimming(props.activity)
              ? t('generalItems.labelStrokeRateInSpm')
              : t('generalItems.labelCadenceInRpm')
          }
        }
        // Add data points
        if (stream.stream_type === 1 && props.graphSelection === 'hr') {
          for (const streamPoint of stream.stream_waypoints) {
            data.push(Number.parseInt(streamPoint.hr))
            label = t('generalItems.labelHRinBpm')
          }
        } else if (stream.stream_type === 2 && props.graphSelection === 'power') {
          for (const streamPoint of stream.stream_waypoints) {
            data.push(Number.parseInt(streamPoint.power))
            label = t('generalItems.labelPowerInWatts')
          }
        } else if (stream.stream_type === 3 && props.graphSelection === 'cad') {
          for (const streamPoint of stream.stream_waypoints) {
            let cadence = Number.parseInt(streamPoint.cad)
            // For running, double the cadence to get total steps per minute (SPM)
            if (activityTypeIsRunning(props.activity)) {
              cadence = cadence * 2
            }
            data.push(cadence)
            // Label as "Stroke Rate" over "Cadence" for swimming activities
            label = activityTypeIsSwimming(props.activity)
              ? t('generalItems.labelStrokeRateInSpm')
              : t('generalItems.labelCadenceInRpm')
          }
        } else if (stream.stream_type === 4 && props.graphSelection === 'ele') {
          for (const streamPoint of stream.stream_waypoints) {
            if (Number(units.value) === 1) {
              data.push(Number.parseFloat(streamPoint.ele))
              label = t('generalItems.labelElevationInMeters')
            } else {
              data.push(Number.parseFloat(metersToFeet(streamPoint.ele)))
              label = t('generalItems.labelElevationInFeet')
            }
          }
        } else if (stream.stream_type === 5 && props.graphSelection === 'vel') {
          if (Number(units.value) === 1) {
            data.push(
              ...stream.stream_waypoints.map((velData) =>
                Number.parseFloat(formatAverageSpeedMetric(velData.vel))
              )
            )
            label = t('generalItems.labelVelocityInKmH')
          } else {
            data.push(
              ...stream.stream_waypoints.map((velData) =>
                Number.parseFloat(formatAverageSpeedImperial(velData.vel))
              )
            )
            label = t('generalItems.labelVelocityInMph')
          }
        } else if (stream.stream_type === 6 && props.graphSelection === 'pace') {
          roundValues = false
          for (const paceData of stream.stream_waypoints) {
            if (paceData.pace === 0 || paceData.pace === null) {
              // Use null so Chart.js will gap missing/invalid pace points
              data.push(null)
            } else {
              // Compute converted pace (minutes per km or per mile for running, walking and rowing, minutes per 100m/100yd for swimming)
              let converted = null
              if (
                activityTypeIsRunning(props.activity) ||
                activityTypeIsWalking(props.activity) ||
                activityTypeIsRowing(props.activity)
              ) {
                if (Number(units.value) === 1) {
                  converted = (paceData.pace * 1000) / 60 // min/km
                } else {
                  converted = (paceData.pace * 1609.34) / 60 // min/mile
                }
                // Apply a hard cap: ignore implausible paces > 20 min/km (or equivalent in min/mile)
                const threshold = Number(units.value) === 1 ? 20 : 20 * 1.60934
                if (converted > threshold || Number.isNaN(converted)) {
                  data.push(null)
                } else {
                  data.push(converted)
                }
              } else if (activityTypeIsSwimming(props.activity)) {
                if (Number(units.value) === 1) {
                  converted = (paceData.pace * 100) / 60 // min/100m
                } else {
                  converted = (paceData.pace * 100 * 0.9144) / 60 // min/100yd
                }
                // Apply a hard cap for swimming: ignore implausible paces > 10 min/100m (or equivalent in min/100yd)
                const swimThreshold = Number(units.value) === 1 ? 10 : 10 * 1.0936
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
            if (Number(units.value) === 1) {
              label = t('generalItems.labelPaceInMinKm')
            } else {
              label = t('generalItems.labelPaceInMinMile')
            }
          } else if (activityTypeIsSwimming(props.activity)) {
            if (Number(units.value) === 1) {
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
        if (Number(units.value) === 1) {
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
      const validData = data.filter((v) => v !== null && !Number.isNaN(v))
      let avgValue = null
      let extremeValue = null
      let extremeLabel = ''

      if (validData.length > 0) {
        avgValue = validData.reduce((a, b) => a + b, 0) / validData.length

        // For pace, show minimum (best/fastest). For others, show maximum (best/highest)
        if (props.graphSelection === 'pace') {
          extremeValue = Math.min(...validData)
          extremeLabel = 'Best'
        } else {
          extremeValue = Math.max(...validData)
          extremeLabel = 'Maximum'
        }
      }

      const datasets = [
        {
          label: label,
          data: data,
          yAxisID: 'y',
          backgroundColor: function (context) {
            const chart = context.chart
            const { ctx, chartArea } = chart
            if (!chartArea) {
              const colors = getGraphColors(props.graphSelection)
              return colors.gradientStart
            }
            return createGradient(ctx, chartArea, props.graphSelection)
          },
          borderColor: getGraphColors(props.graphSelection).border,
          fill: props.graphSelection === 'pace' ? 'start' : true, // For pace, fill from line to top (outside)
          pointHoverRadius: 4,
          pointHoverBackgroundColor: getGraphColors(props.graphSelection).border
        }
      ]

      // Add average reference line if we have valid data
      if (avgValue !== null) {
        datasets.push({
          label: t('generalItems.labelAverage'),
          data: Array(data.length).fill(avgValue),
          yAxisID: 'y',
          borderColor: 'rgba(156, 163, 175, 0.6)', // Gray color
          borderWidth: 2,
          borderDash: [10, 5], // Dashed line
          fill: false,
          pointRadius: 0,
          pointHoverRadius: 0,
          tension: 0
        })
      }

      // Add extreme value reference line if we have valid data (max for most, min/best for pace)
      if (extremeValue !== null) {
        datasets.push({
          label: extremeLabel,
          data: Array(data.length).fill(extremeValue),
          yAxisID: 'y',
          borderColor: 'rgba(220, 38, 38, 0.5)', // Red color, more transparent
          borderWidth: 1.5,
          borderDash: [5, 5], // Shorter dashes
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
          // Ensure pace graphs are inverted so lower min/km/min/100m appear higher
          if (myChart.options && myChart.options.scales && myChart.options.scales.y) {
            myChart.options.scales.y.reverse = props.graphSelection === 'pace'
          }
          myChart.update()
        }
      },
      { deep: true }
    )

    // Custom crosshair plugin
    const crosshairPlugin = {
      id: 'customCrosshair',
      afterDraw: (chart) => {
        if (chart.tooltip?._active && chart.tooltip._active.length) {
          const ctx = chart.ctx
          const activePoint = chart.tooltip._active[0]
          const x = activePoint.element.x
          const topY = chart.scales.y.top
          const bottomY = chart.scales.y.bottom

          // Draw vertical line
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
      myChart = new Chart(chartCanvas.value.getContext('2d'), {
        type: 'line',
        data: computedChartData.value,
        plugins: [crosshairPlugin],
        options: {
          responsive: true,
          animation: false, // Disable animations for faster rendering with many points
          interaction: {
            mode: 'index', // Show tooltip for all datasets at the same x position
            intersect: false // Don't require hovering exactly on a point
          },
          elements: {
            point: {
              radius: 0, // Hide points by default (keeps line visible)
              hitRadius: 10, // Large invisible hover area for easier interaction
              hoverRadius: 4 // Show small point when hovering
            },
            line: {
              tension: 0.4 // Smooth curves instead of straight lines (0 = angular, 0.4 = smooth)
            }
          },
          scales: {
            y: {
              beginAtZero: false,
              position: 'left',
              // Reverse the y-axis for pace so that lower times plot higher
              reverse: props.graphSelection === 'pace',
              grid: {
                lineWidth: 1,
                drawBorder: true,
                borderWidth: 1
              }
            },
            y1: {
              beginAtZero: true,
              max: 1,
              display: false
            },
            x: {
              ticks: {
                maxTicksLimit: 10, // Limit x-axis labels to approximately 10 for better readability
                autoSkip: true
              },
              grid: {
                lineWidth: 1,
                drawBorder: true,
                borderWidth: 1
              }
            }
          },
          plugins: {
            tooltip: {
              enabled: true,
              callbacks: {
                title: function (context) {
                  // Show the distance label as the title
                  return context[0].label
                },
                label: function (context) {
                  const label = context.dataset.label || ''
                  let value = context.parsed.y

                  if (value === null || value === undefined) {
                    return `${label}: N/A`
                  }

                  // Format based on the type of data
                  if (props.graphSelection === 'pace') {
                    // Format pace as MM:SS
                    const formatted = formatPaceForTooltip(value)
                    return `${label}: ${formatted}`
                  } else if (props.graphSelection === 'hr') {
                    // Heart rate - whole number
                    return `${label}: ${Math.round(value)}`
                  } else if (props.graphSelection === 'power') {
                    // Power - whole number
                    return `${label}: ${Math.round(value)} W`
                  } else if (props.graphSelection === 'cad') {
                    // Cadence/Stroke Rate - whole number
                    return `${label}: ${Math.round(value)}`
                  } else if (props.graphSelection === 'ele') {
                    // Elevation - 1 decimal
                    return `${label}: ${value.toFixed(1)}`
                  } else if (props.graphSelection === 'vel') {
                    // Velocity - 1 decimal
                    return `${label}: ${value.toFixed(1)}`
                  }

                  return `${label}: ${value}`
                }
              }
            },
            zoom: {
              pan: {
                enabled: true,
                mode: 'x', // Only pan horizontally
                modifierKey: 'shift' // Hold shift to pan
              },
              zoom: {
                wheel: {
                  enabled: true, // Enable zoom with mouse wheel
                  speed: 0.1
                },
                pinch: {
                  enabled: true // Enable pinch zoom on touch devices
                },
                mode: 'x' // Only zoom horizontally
              },
              limits: {
                x: {
                  min: 'original', // Can't pan/zoom beyond original data
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

    return {
      chartCanvas,
      activityTypeIsSwimming
    }
  }
}
</script>
