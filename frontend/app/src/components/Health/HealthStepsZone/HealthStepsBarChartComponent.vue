<template>
  <LoadingComponent v-if="isLoading" />
  <canvas ref="chartCanvas" class="chart-canvas" v-else></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
// Import the components
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

import { Chart, registerables } from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'
Chart.register(...registerables, zoomPlugin)

const props = defineProps({
  userHealthTargets: {
    type: [Object, null],
    required: true
  },
  userHealthSteps: {
    type: Array,
    required: true
  },
  isLoading: {
    type: Boolean,
    required: true
  }
})

const { t } = useI18n()
const chartCanvas = ref(null)
let myChart = null

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

const chartData = computed(() => {
  if (!props.userHealthSteps || props.userHealthSteps.length === 0) {
    return {
      datasets: [],
      labels: []
    }
  }

  // Sort health steps by date
  const sortedSteps = [...props.userHealthSteps].sort((a, b) => {
    return new Date(a.date) - new Date(b.date)
  })

  const data = []
  const labels = []
  
  for (const healthSteps of sortedSteps) {
    data.push(healthSteps.steps)

    const createdAt = new Date(healthSteps.date)
    labels.push(
      `${createdAt.getDate()}/${createdAt.getMonth() + 1}/${createdAt.getFullYear()}`
    )
  }

  const datasets = [
    {
      label: t('generalItems.labelSteps'),
      data: data,
      backgroundColor: 'rgba(59, 130, 246, 0.4)',
      borderColor: 'rgba(59, 130, 246, 0.8)', // Blue border
      borderWidth: 0,
      borderRadius: 4
    }
  ]

  // Add target line if steps target exists
  if (props.userHealthTargets?.steps != null) {
    datasets.push({
      label: t('generalItems.labelStepsTarget'),
      data: Array(labels.length).fill(props.userHealthTargets.steps),
      type: 'line',
      borderColor: 'rgba(107, 114, 128, 0.9)',
      borderWidth: 2,
      borderDash: [5, 5],
      fill: false,
      pointRadius: 0,
      pointHoverRadius: 0
    })
  }

  return {
    datasets: datasets,
    labels: labels
  }
})

watch(
  chartData,
  (newChartData) => {
    if (myChart) {
      myChart.data = newChartData
      myChart.update()
    }
  },
  { deep: true }
)

onMounted(() => {
  myChart = new Chart(chartCanvas.value.getContext('2d'), {
    type: 'bar',
    data: chartData.value,
    plugins: [crosshairPlugin],
    options: {
      responsive: true,
      animation: false, // Disable animations for faster rendering
      interaction: {
        mode: 'index', // Show tooltip for all datasets at the same x position
        intersect: false // Don't require hovering exactly on a point
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            lineWidth: 1,
            drawBorder: true,
            borderWidth: 1
          }
        },
        x: {
          autoSkip: true,
          ticks: {
            maxTicksLimit: 10, // Limit x-axis labels for better readability
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
              // Show the date label as the title
              return context[0].label
            },
            label: function (context) {
              const label = context.dataset.label || ''
              const value = context.parsed.y

              if (value === null || value === undefined) {
                return `${label}: N/A`
              }

              // Format steps value
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
</script>

<style scoped>
.chart-canvas {
  max-height: 300px;
  width: 100%; /* Ensures the canvas stretches across the available width */
}
</style>
