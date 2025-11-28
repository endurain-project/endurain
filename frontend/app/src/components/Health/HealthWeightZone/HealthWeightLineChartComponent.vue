<template>
  <LoadingComponent v-if="isLoading" />
  <canvas ref="chartCanvas" class="chart-canvas" v-else></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { kgToLbs } from '@/utils/unitsUtils'
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
  userHealthWeight: {
    type: Array,
    required: true
  },
  isLoading: {
    type: Boolean,
    required: true
  }
})

const { t } = useI18n()
const authStore = useAuthStore()
const chartCanvas = ref(null)
let myChart = null

// Function to create gradient fill for chart
function createGradient(ctx, chartArea) {
  if (!chartArea) {
    return 'rgba(59, 130, 246, 0.4)'
  }

  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
  gradient.addColorStop(0, 'rgba(59, 130, 246, 0.4)') // Blue, more opaque at top
  gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)') // Transparent at bottom
  return gradient
}

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
  if (!props.userHealthWeight || props.userHealthWeight.length === 0) {
    return {
      datasets: [],
      labels: []
    }
  }

  // Sort health weight by date
  const sortedWeight = [...props.userHealthWeight].sort((a, b) => {
    return new Date(a.date) - new Date(b.date)
  })

  const weightData = []
  const bmiData = []
  const bodyFatData = []
  const bodyWaterData = []
  const boneMassData = []
  const muscleMassData = []
  const labels = []

  for (const HealthWeight of sortedWeight) {
    if (Number(authStore?.user?.units) === 1) {
      weightData.push(HealthWeight.weight)
    } else {
      weightData.push(kgToLbs(HealthWeight.weight))
    }

    // Add other metrics
    bmiData.push(HealthWeight.bmi || null)
    bodyFatData.push(HealthWeight.body_fat || null)
    bodyWaterData.push(HealthWeight.body_water || null)
    boneMassData.push(HealthWeight.bone_mass || null)
    muscleMassData.push(HealthWeight.muscle_mass || null)

    const createdAt = new Date(HealthWeight.date)
    labels.push(
      `${createdAt.getDate()}/${createdAt.getMonth() + 1}/${createdAt.getFullYear()}`
    )
  }

  let weightLabel = ''
  let unitsLabel = ''
  if (Number(authStore?.user?.units) === 1) {
    weightLabel = t('generalItems.labelWeightInKg')
    unitsLabel = t('generalItems.unitsKg')
  } else {
    weightLabel = t('generalItems.labelWeightInLbs')
    unitsLabel = t('generalItems.unitsLbs')
  }
  const BMILabel = t('healthWeightAddEditModalComponent.addWeightBMILabel')
  const bodyFatLabel = t('healthWeightAddEditModalComponent.addWeightBodyFatLabel')
  const bodyWaterLabel = t('healthWeightAddEditModalComponent.addWeightBodyWaterLabel')
  const boneMassLabel = t('healthWeightAddEditModalComponent.addWeightBoneMassLabel')
  const muscleMassLabel = t('healthWeightAddEditModalComponent.addWeightMuscleMassLabel')

  const datasets = [
    {
      label: weightLabel,
      data: weightData,
      backgroundColor: function (context) {
        const chart = context.chart
        const { ctx, chartArea } = chart
        if (!chartArea) {
          return 'rgba(59, 130, 246, 0.4)'
        }
        return createGradient(ctx, chartArea)
      },
      borderColor: 'rgba(59, 130, 246, 0.8)', // Blue
      fill: true,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(59, 130, 246, 0.8)',
      yAxisID: 'y'
    },
    {
      label: BMILabel,
      data: bmiData,
      borderColor: 'rgba(34, 197, 94, 0.8)', // Green
      backgroundColor: 'rgba(34, 197, 94, 0.1)',
      fill: false,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(34, 197, 94, 0.8)',
      yAxisID: 'y1'
    },
    {
      label: bodyFatLabel + ' (%)',
      data: bodyFatData,
      borderColor: 'rgba(251, 146, 60, 0.8)', // Orange
      backgroundColor: 'rgba(251, 146, 60, 0.1)',
      fill: false,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(251, 146, 60, 0.8)',
      yAxisID: 'y1'
    },
    {
      label: bodyWaterLabel + ' (%)',
      data: bodyWaterData,
      borderColor: 'rgba(14, 165, 233, 0.8)', // Cyan
      backgroundColor: 'rgba(14, 165, 233, 0.1)',
      fill: false,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(14, 165, 233, 0.8)',
      yAxisID: 'y1'
    },
    {
      label: boneMassLabel + ' (' + unitsLabel + ')',
      data: boneMassData,
      borderColor: 'rgba(168, 85, 247, 0.8)', // Purple
      backgroundColor: 'rgba(168, 85, 247, 0.1)',
      fill: false,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(168, 85, 247, 0.8)',
      yAxisID: 'y'
    },
    {
      label: muscleMassLabel + ' (' + unitsLabel + ')',
      data: muscleMassData,
      borderColor: 'rgba(236, 72, 153, 0.8)', // Pink
      backgroundColor: 'rgba(236, 72, 153, 0.1)',
      fill: false,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: 'rgba(236, 72, 153, 0.8)',
      yAxisID: 'y'
    }
  ]

  // Add target line if weight target exists
  if (props.userHealthTargets?.weight != null) {
    const targetWeight =
      Number(authStore?.user?.units) === 1
        ? props.userHealthTargets.weight
        : kgToLbs(props.userHealthTargets.weight)

    const targetLabel =
      Number(authStore?.user?.units) === 1
        ? t('generalItems.labelWeightTargetInKg')
        : t('generalItems.labelWeightTargetInLbs')

    datasets.push({
      label: targetLabel,
      data: Array(labels.length).fill(targetWeight),
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
    type: 'line',
    data: chartData.value,
    plugins: [crosshairPlugin],
    options: {
      responsive: true,
      animation: false, // Disable animations for faster rendering
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
          type: 'linear',
          display: true,
          position: 'left',
          beginAtZero: false,
          grid: {
            lineWidth: 1,
            drawBorder: true,
            borderWidth: 1
          },
          title: {
            display: true,
            text: 'Weight / Mass'
          }
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          beginAtZero: false,
          grid: {
            drawOnChartArea: false
          },
          title: {
            display: true,
            text: 'Percentage (%)'
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

              // Format values with appropriate decimal places
              if (label.includes('%')) {
                return `${label}: ${value.toFixed(1)}%`
              }
              return `${label}: ${value.toFixed(2)}`
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
  width: 100%;
  /* Ensures the canvas stretches across the available width */
}
</style>
